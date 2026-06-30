from dataclasses import dataclass

from job_radar.candidate_profile import CandidateProfile
from job_radar.models import JobPosting
from job_radar.normalize import clean_text


@dataclass(frozen=True)
class ResumeMatchResult:
    label: str
    evidence: list[str]
    gaps: list[str]


def match_resume_to_posting(
    posting: JobPosting,
    candidate_profile: CandidateProfile | None,
    resume_text: str | None,
) -> ResumeMatchResult:
    if candidate_profile is None or not resume_text:
        return ResumeMatchResult(label="Unknown", evidence=[], gaps=[])

    normalized_resume_text = clean_text(resume_text).lower()
    posting_text = _build_posting_text(posting)

    evidence = _find_resume_evidence(
        candidate_profile=candidate_profile,
        resume_text=normalized_resume_text,
        posting_text=posting_text,
    )
    gaps = _find_resume_gaps(
        candidate_profile=candidate_profile,
        posting_text=posting_text,
    )

    return ResumeMatchResult(
        label=_classify_resume_match(evidence=evidence, gaps=gaps),
        evidence=evidence,
        gaps=gaps,
    )


def _find_resume_evidence(
    candidate_profile: CandidateProfile,
    resume_text: str,
    posting_text: str,
) -> list[str]:
    evidence: list[str] = []

    for strength in candidate_profile.core_strengths + candidate_profile.credible_adjacent:
        normalized_strength = clean_text(strength).lower()

        if not normalized_strength:
            continue

        if _term_matches(normalized_strength, resume_text) and _term_matches(
            normalized_strength,
            posting_text,
        ):
            evidence.append(strength)

    return _dedupe_preserving_order(evidence)


def _find_resume_gaps(
    candidate_profile: CandidateProfile,
    posting_text: str,
) -> list[str]:
    gaps: list[str] = []

    for gap in candidate_profile.learning_or_gap:
        normalized_gap = clean_text(gap).lower()

        if not normalized_gap:
            continue

        if _term_matches(normalized_gap, posting_text):
            gaps.append(gap)

    return _dedupe_preserving_order(gaps)


def _classify_resume_match(evidence: list[str], gaps: list[str]) -> str:
    evidence_count = len(evidence)
    gap_count = len(gaps)

    if evidence_count >= 4 and gap_count == 0:
        return "Very Strong"

    if evidence_count >= 3 and gap_count <= 1:
        return "Strong"

    if evidence_count >= 1:
        return "Medium"

    return "Weak"


def _term_matches(term: str, text: str) -> bool:
    if term in text:
        return True

    term_words = [word for word in term.split() if len(word) >= 3]

    if not term_words:
        return False

    return all(word in text for word in term_words)


def _build_posting_text(posting: JobPosting) -> str:
    parts = [
        posting.title,
        posting.location,
        posting.remote_status,
        posting.salary_text,
        posting.description,
    ]

    return clean_text(" ".join(part for part in parts if part)).lower()


def _dedupe_preserving_order(values: list[str]) -> list[str]:
    deduped_values: list[str] = []

    for value in values:
        if value not in deduped_values:
            deduped_values.append(value)

    return deduped_values