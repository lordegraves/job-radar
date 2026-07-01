import re
from dataclasses import dataclass

from job_radar.job_history import JobHistoryRecord
from job_radar.models import JobPosting


_GENERIC_ROLE_TOKENS = {
    "senior",
    "sr",
    "staff",
    "principal",
    "lead",
    "engineer",
    "engineering",
    "system",
    "systems",
    "software",
    "developer",
    "role",
}

_MEANINGFUL_ROLE_TOKENS = {
    "ai",
    "cluster",
    "compute",
    "datacenter",
    "gpu",
    "hardware",
    "hpc",
    "infrastructure",
    "kubernetes",
    "linux",
    "platform",
    "reliability",
    "security",
    "site",
    "sre",
    "storage",
}


@dataclass(frozen=True)
class HistoryMatch:
    record: JobHistoryRecord
    matched_tokens: tuple[str, ...]
    risk_level: str
    risk_reasons: tuple[str, ...]


def build_posting_history_context(
    posting: JobPosting,
    history_records: list[JobHistoryRecord],
    limit: int = 3,
) -> list[str]:
    matches = find_history_matches(
        posting=posting,
        history_records=history_records,
        limit=limit,
    )

    return format_history_matches(matches)


def format_history_matches(matches: list[HistoryMatch]) -> list[str]:
    return [_format_history_match(match) for match in matches]


def summarize_history_risk(
    matches: list[HistoryMatch],
) -> tuple[str | None, list[str]]:
    if not matches:
        return None, []

    risk_priority = {
        "blocker_review": 3,
        "caution": 2,
        "neutral": 1,
    }

    risk_level = max(
        (match.risk_level for match in matches),
        key=lambda item: risk_priority.get(item, 0),
    )

    risk_reasons: list[str] = []

    for match in matches:
        for reason in match.risk_reasons:
            if reason not in risk_reasons:
                risk_reasons.append(reason)

    return risk_level, risk_reasons


def find_history_matches(
    posting: JobPosting,
    history_records: list[JobHistoryRecord],
    limit: int = 3,
) -> list[HistoryMatch]:
    posting_company = _normalize_text(posting.company_name)
    posting_tokens = _meaningful_role_tokens(posting.title)

    if not posting_company or not posting_tokens:
        return []

    matches: list[HistoryMatch] = []

    for record in history_records:
        if not record.include_in_job_radar:
            continue

        if _normalize_text(record.company) != posting_company:
            continue

        record_tokens = _meaningful_role_tokens(record.role)
        matched_tokens = tuple(sorted(posting_tokens & record_tokens))

        if not matched_tokens:
            continue

        risk_level, risk_reasons = _classify_history_risk(record)

        matches.append(
            HistoryMatch(
                record=record,
                matched_tokens=matched_tokens,
                risk_level=risk_level,
                risk_reasons=risk_reasons,
            )
        )

    return matches[:limit]


def _classify_history_risk(record: JobHistoryRecord) -> tuple[str, tuple[str, ...]]:
    outcome = _clean_label(record.outcome_category)
    technical_match = _clean_label(record.technical_match)
    blocker = _clean_label(record.primary_blocker)

    reasons: list[str] = []

    if outcome == "No Interview":
        if technical_match in {"Strong", "Very Strong"}:
            reasons.append("prior_no_interview_despite_strong_match")
        else:
            reasons.append("prior_no_interview")

        return "caution", tuple(reasons)

    if outcome == "Skipped / Avoid":
        if blocker != "Unknown":
            reasons.append(f"prior_blocker:{_risk_token(blocker)}")
        else:
            reasons.append("prior_skipped_similar_role")

        return "blocker_review", tuple(reasons)

    if blocker != "Unknown":
        reasons.append(f"prior_blocker:{_risk_token(blocker)}")
        return "caution", tuple(reasons)

    return "neutral", ("prior_similar_role",)


def _format_history_match(match: HistoryMatch) -> str:
    record = match.record
    outcome = _clean_label(record.outcome_category)
    technical_match = _clean_label(record.technical_match)
    blocker = _clean_label(record.primary_blocker)

    if outcome == "No Interview":
        if technical_match != "Unknown":
            return (
                f"Prior similar application at {record.company} ended "
                f"No Interview despite {technical_match} technical match"
            )

        return f"Prior similar application at {record.company} ended No Interview"

    if outcome == "Skipped / Avoid":
        if blocker != "Unknown":
            return (
                f"Previously reviewed and skipped similar role at {record.company}; "
                f"prior blocker: {blocker}"
            )

        return f"Previously reviewed and skipped similar role at {record.company}"

    if blocker != "Unknown":
        return (
            f"Prior similar role at {record.company}; outcome: {outcome}; "
            f"prior blocker: {blocker}"
        )

    return f"Prior similar role at {record.company}; outcome: {outcome}"


def _meaningful_role_tokens(value: str | None) -> set[str]:
    tokens = {
        token
        for token in _tokenize(value)
        if token not in _GENERIC_ROLE_TOKENS
    }

    meaningful_tokens = tokens & _MEANINGFUL_ROLE_TOKENS

    return meaningful_tokens or tokens


def _tokenize(value: str | None) -> set[str]:
    if not value:
        return set()

    return set(re.findall(r"[a-z0-9]+", value.lower()))


def _normalize_text(value: str | None) -> str:
    if not value:
        return ""

    return " ".join(_tokenize(value))


def _risk_token(value: str) -> str:
    return "_".join(sorted(_tokenize(value)))


def _clean_label(value: str | None) -> str:
    if value is None or value.strip() == "":
        return "Unknown"

    return value.strip()
