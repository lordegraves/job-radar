"""Suggest adjacent roles from demonstrated work rather than title synonyms.

The service uses two bounded evidence sources: packaged O*NET occupation
descriptions and job descriptions already collected for the selected profile.
Suggestions never become approved mappings until the user records feedback.
"""

from dataclasses import dataclass
import json
import re
import sqlite3
from functools import lru_cache
from importlib.resources import files
from pathlib import Path

from job_radar.config import ConfigError
from job_radar.database import connect_database
from job_radar.profile_context import managed_profile_to_candidate_profile
from job_radar.profile_storage import get_profile
from job_radar.resume_loader import load_resume_text
from job_radar.storage import initialize_database


FEEDBACK_STATES = {
    "pending",
    "relevant",
    "not_relevant",
    "different_discipline",
}
MAX_CATALOG_SUGGESTIONS = 8
MAX_OBSERVED_SUGGESTIONS = 8
STOP_WORDS = {
    "about",
    "after",
    "also",
    "and",
    "are",
    "been",
    "being",
    "can",
    "for",
    "from",
    "have",
    "into",
    "job",
    "may",
    "more",
    "other",
    "role",
    "such",
    "that",
    "the",
    "their",
    "these",
    "they",
    "this",
    "through",
    "using",
    "with",
    "work",
}
GENERIC_ROLE_TERMS = {
    "administrator",
    "analyst",
    "associate",
    "coordinator",
    "engineer",
    "manager",
    "operator",
    "specialist",
    "system",
    "systems",
    "technician",
}
GENERIC_EVIDENCE_TERMS = {
    "computer",
    "computers",
    "equipment",
    "information",
    "operating",
}
DISCIPLINE_GATES = {
    "rtl": {"rtl", "verilog", "systemverilog", "uvm"},
    "asic": {"asic", "soc", "silicon", "verilog", "systemverilog"},
    "fpga": {"fpga", "vhdl", "verilog", "systemverilog"},
    "design verification": {
        "design verification",
        "formal verification",
        "rtl",
        "uvm",
        "verilog",
        "systemverilog",
    },
    "software": {
        "software",
        "programming",
        "developer",
        "development",
        "python",
        "java",
        "c++",
    },
    "application": {
        "software",
        "application",
        "programming",
        "developer",
        "development",
    },
    "artificial intelligence": {
        "artificial intelligence",
        "machine learning",
        "ai",
        "ml",
    },
    "manager": {
        "managed",
        "management",
        "supervised",
        "leadership",
        "led",
    },
}


@dataclass(frozen=True)
class RoleSuggestion:
    """Present one explained, profile-owned title suggestion."""

    suggestion_id: int
    profile_id: str
    suggested_title: str
    occupation_code: str | None
    employer_context: str | None
    source_type: str
    explanation: str
    evidence: tuple[str, ...]
    feedback_state: str


def refresh_role_suggestions(
    database_path: str | Path,
    *,
    profile_id: str,
    base_directory: str | Path,
) -> tuple[RoleSuggestion, ...]:
    """Rebuild bounded suggestions without changing prior user feedback."""

    db_path = initialize_database(database_path)
    profile = get_profile(db_path, profile_id)
    if profile is None or profile.archived:
        raise ConfigError("The selected profile is not available.")
    if profile.resume is None:
        raise ConfigError(
            "Upload a résumé before asking junior to suggest related roles."
        )

    candidate = managed_profile_to_candidate_profile(
        profile,
        base_directory=Path(base_directory),
    )
    if candidate.resume is None:
        raise ConfigError(
            "Upload a résumé before asking junior to suggest related roles."
        )
    resume_text = load_resume_text(candidate.resume.source_path)
    resume_terms = _tokens(resume_text)
    if len(resume_terms) < 3:
        raise ConfigError(
            "The résumé does not contain enough readable work evidence "
            "for responsible role suggestions."
        )

    generated = [
        *_catalog_suggestions(profile, resume_text, resume_terms),
        *_observed_suggestions(db_path, profile_id, profile.preferences.target_roles, resume_terms),
    ]
    with connect_database(db_path) as connection:
        for suggestion in generated:
            connection.execute(
                """
                INSERT INTO role_discovery_suggestions (
                    profile_id,
                    suggested_title,
                    normalized_title,
                    occupation_code,
                    employer_context,
                    context_key,
                    source_type,
                    explanation,
                    evidence_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(profile_id, normalized_title, context_key)
                DO UPDATE SET
                    suggested_title = excluded.suggested_title,
                    occupation_code = excluded.occupation_code,
                    employer_context = excluded.employer_context,
                    source_type = excluded.source_type,
                    explanation = excluded.explanation,
                    evidence_json = excluded.evidence_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    profile_id,
                    suggestion["title"],
                    _normalize_title(suggestion["title"]),
                    suggestion["occupation_code"],
                    suggestion["employer_context"],
                    suggestion["context_key"],
                    suggestion["source_type"],
                    suggestion["explanation"],
                    json.dumps(suggestion["evidence"]),
                ),
            )
    return list_role_suggestions(db_path, profile_id=profile_id)


def list_role_suggestions(
    database_path: str | Path,
    *,
    profile_id: str,
) -> tuple[RoleSuggestion, ...]:
    """List one profile's suggestions without leaking another profile's feedback."""

    db_path = initialize_database(database_path)
    with connect_database(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT *
            FROM role_discovery_suggestions
            WHERE profile_id = ?
            ORDER BY
                CASE feedback_state
                    WHEN 'pending' THEN 0
                    WHEN 'relevant' THEN 1
                    ELSE 2
                END,
                suggested_title COLLATE NOCASE,
                context_key
            """,
            (profile_id,),
        ).fetchall()
    return tuple(_row_to_suggestion(row) for row in rows)


def record_role_feedback(
    database_path: str | Path,
    *,
    profile_id: str,
    suggestion_id: int,
    feedback_state: str,
) -> RoleSuggestion:
    """Store an explicit decision without inferring approval from page views."""

    if feedback_state not in FEEDBACK_STATES - {"pending"}:
        raise ConfigError("Choose Relevant, Not relevant, or Different discipline.")
    db_path = initialize_database(database_path)
    with connect_database(db_path) as connection:
        connection.row_factory = sqlite3.Row
        cursor = connection.execute(
            """
            UPDATE role_discovery_suggestions
            SET feedback_state = ?,
                reviewed_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND profile_id = ?
            """,
            (feedback_state, suggestion_id, profile_id),
        )
        if cursor.rowcount != 1:
            raise ConfigError("The selected role suggestion is no longer available.")
        row = connection.execute(
            "SELECT * FROM role_discovery_suggestions WHERE id = ?",
            (suggestion_id,),
        ).fetchone()
    if row is None:
        raise ConfigError("The selected role suggestion is no longer available.")
    return _row_to_suggestion(row)


def approved_role_mappings(
    database_path: str | Path,
    *,
    profile_id: str,
    employer_context: str | None = None,
) -> tuple[str, ...]:
    """Return only user-approved mappings applicable to the requested context."""

    db_path = initialize_database(database_path)
    context_key = (
        f"employer:{employer_context.casefold()}"
        if employer_context
        else "occupation_catalog"
    )
    with connect_database(db_path) as connection:
        rows = connection.execute(
            """
            SELECT suggested_title
            FROM role_discovery_suggestions
            WHERE profile_id = ?
              AND feedback_state = 'relevant'
              AND context_key IN ('occupation_catalog', ?)
            ORDER BY suggested_title COLLATE NOCASE
            """,
            (profile_id, context_key),
        ).fetchall()
    return tuple(dict.fromkeys(row[0] for row in rows))


def effective_target_roles(
    database_path: str | Path,
    *,
    profile,
    employer_context: str | None = None,
) -> tuple[str, ...]:
    """Combine user-entered roles with only explicitly approved mappings."""

    approved = approved_role_mappings(
        database_path,
        profile_id=profile.profile_id,
        employer_context=employer_context,
    )
    return tuple(
        dict.fromkeys(
            value.strip()
            for value in (
                *profile.preferences.target_roles,
                *(
                    item.label
                    for item in profile.preferences.occupation_selections
                ),
                *approved,
            )
            if value.strip()
        )
    )


def _catalog_suggestions(profile, resume_text: str, resume_terms: set[str]) -> list[dict]:
    occupations, titles_by_code, title_codes = _occupation_reference()
    selected_codes: set[str] = set()
    selected_titles = {
        _normalize_title(value)
        for value in (
            *profile.preferences.target_roles,
            *(item.label for item in profile.preferences.occupation_selections),
        )
    }
    for selection in profile.preferences.occupation_selections:
        if selection.value in occupations:
            selected_codes.add(selection.value)
    for title in selected_titles:
        selected_codes.update(title_codes.get(title, ()))

    candidates: list[tuple[int, str, str, tuple[str, ...]]] = []
    for code in selected_codes:
        occupation = occupations.get(code)
        if occupation is None:
            continue
        evidence = tuple(
            sorted(
                resume_terms
                & _tokens(occupation["description"])
                - GENERIC_ROLE_TERMS
                - GENERIC_EVIDENCE_TERMS
            )[:6]
        )
        if len(evidence) < 2:
            continue
        for title in titles_by_code.get(code, ()):
            normalized = _normalize_title(title)
            if normalized in selected_titles or not _title_is_safe(title, resume_text):
                continue
            informative_title_terms = (
                _tokens(title)
                - GENERIC_ROLE_TERMS
                - GENERIC_EVIDENCE_TERMS
            )
            title_evidence = informative_title_terms & resume_terms
            if not title_evidence:
                continue
            combined_evidence = tuple(
                sorted(
                    title_evidence
                    | (
                        resume_terms
                        & _tokens(occupation["description"])
                        - GENERIC_ROLE_TERMS
                        - GENERIC_EVIDENCE_TERMS
                    )
                )[:6]
            )
            candidates.append(
                (-len(title_evidence), title, code, combined_evidence)
            )

    candidates.sort(key=lambda item: (item[0], len(item[1]), item[1].casefold()))
    results: list[dict] = []
    seen: set[str] = set()
    for _, title, code, evidence in candidates:
        normalized = _normalize_title(title)
        if normalized in seen:
            continue
        seen.add(normalized)
        occupation_title = occupations[code]["title"]
        results.append(
            {
                "title": title,
                "occupation_code": code,
                "employer_context": None,
                "context_key": "occupation_catalog",
                "source_type": "occupation_catalog",
                "evidence": evidence,
                "explanation": (
                    f"O*NET groups this title with {occupation_title}. "
                    f"Your résumé contains related work evidence: "
                    f"{', '.join(evidence)}. Junior is not assuming the titles "
                    "are synonyms; review the discipline before approving it."
                ),
            }
        )
        if len(results) >= MAX_CATALOG_SUGGESTIONS:
            break
    return results


def _observed_suggestions(
    database_path: Path,
    profile_id: str,
    target_roles: tuple[str, ...],
    resume_terms: set[str],
) -> list[dict]:
    selected_titles = {_normalize_title(title) for title in target_roles}
    with connect_database(database_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT DISTINCT
                jobs.title,
                jobs.description,
                jobs.company_key,
                COALESCE(employers.name, companies.name, jobs.company_key)
                    AS employer_name
            FROM job_postings AS jobs
            JOIN job_seen_events AS events
              ON events.job_posting_id = jobs.id
            JOIN scan_runs AS runs
              ON runs.id = events.scan_run_id
            LEFT JOIN employer_sources AS employers
              ON employers.employer_id = jobs.company_key
            LEFT JOIN companies
              ON companies.company_key = jobs.company_key
            WHERE runs.profile_id = ?
              AND jobs.description IS NOT NULL
              AND jobs.description != ''
              AND jobs.last_seen_at >= datetime('now', '-90 days')
            ORDER BY jobs.last_seen_at DESC
            LIMIT 500
            """,
            (profile_id,),
        ).fetchall()

    ranked: list[tuple[int, dict]] = []
    for row in rows:
        title = row["title"].strip()
        if not title or _normalize_title(title) in selected_titles:
            continue
        evidence = tuple(
            sorted(resume_terms & _tokens(row["description"]))[:8]
        )
        if len(evidence) < 4:
            continue
        employer = row["employer_name"]
        ranked.append(
            (
                -len(evidence),
                {
                    "title": title,
                    "occupation_code": None,
                    "employer_context": employer,
                    "context_key": f"employer:{row['company_key'].casefold()}",
                    "source_type": "observed_posting",
                    "evidence": evidence,
                    "explanation": (
                        f"Junior saw this title at {employer}. The job description "
                        f"and your résumé share concrete evidence: "
                        f"{', '.join(evidence)}. This mapping applies to that "
                        "company context unless you approve broader use later."
                    ),
                },
            )
        )
    ranked.sort(key=lambda item: (item[0], item[1]["title"].casefold()))
    return [item[1] for item in ranked[:MAX_OBSERVED_SUGGESTIONS]]


def _title_is_safe(title: str, resume_text: str) -> bool:
    normalized_title = _normalize_title(title)
    normalized_resume = _normalize_title(resume_text)
    for marker, required_evidence in DISCIPLINE_GATES.items():
        if marker in normalized_title and not any(
            evidence in normalized_resume for evidence in required_evidence
        ):
            return False
    return True


def _tokens(value: str) -> set[str]:
    return {
        _canonical_token(token)
        for token in re.findall(r"[a-z0-9+#.]+", value.casefold())
        if len(token) >= 3 and token not in STOP_WORDS
    }


def _canonical_token(token: str) -> str:
    """Normalize only simple grammatical endings, not occupational meaning."""

    if token.endswith("ies") and len(token) > 4:
        return f"{token[:-3]}y"
    if token.endswith("ed") and len(token) > 4:
        return token[:-1] if token.endswith(("ated", "ured", "ized")) else token[:-2]
    if token.endswith("s") and not token.endswith("ss") and len(token) > 3:
        return token[:-1]
    return token


def _normalize_title(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


@lru_cache(maxsize=1)
def _occupation_reference():
    occupations_payload = json.loads(
        files("job_radar.reference_data")
        .joinpath("occupations.json")
        .read_text(encoding="utf-8")
    )
    titles_payload = json.loads(
        files("job_radar.reference_data")
        .joinpath("job_titles.json")
        .read_text(encoding="utf-8")
    )
    occupations = {
        item["code"]: item for item in occupations_payload["occupations"]
    }
    titles_by_code: dict[str, list[str]] = {}
    title_codes: dict[str, set[str]] = {}
    for item in titles_payload["job_titles"]:
        titles_by_code.setdefault(item["code"], []).append(item["job_title"])
        title_codes.setdefault(_normalize_title(item["job_title"]), set()).add(
            item["code"]
        )
    for occupation in occupations.values():
        title_codes.setdefault(
            _normalize_title(occupation["title"]), set()
        ).add(occupation["code"])
    return occupations, titles_by_code, title_codes


def _row_to_suggestion(row: sqlite3.Row) -> RoleSuggestion:
    raw_evidence = json.loads(row["evidence_json"])
    return RoleSuggestion(
        suggestion_id=row["id"],
        profile_id=row["profile_id"],
        suggested_title=row["suggested_title"],
        occupation_code=row["occupation_code"],
        employer_context=row["employer_context"],
        source_type=row["source_type"],
        explanation=row["explanation"],
        evidence=tuple(str(value) for value in raw_evidence),
        feedback_state=row["feedback_state"],
    )
