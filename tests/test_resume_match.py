from job_radar.candidate_profile import CandidateProfile, CandidateResumeConfig
from job_radar.models import JobPosting
from job_radar.resume_match import match_resume_to_posting


def make_profile() -> CandidateProfile:
    return CandidateProfile(
        name="Clayton Graves",
        compensation_floor_usd=160000,
        preferred_base_usd=185000,
        resume=CandidateResumeConfig(source_path="resume.md"),
        core_strengths=[
            "Linux infrastructure",
            "HPC operations",
            "cluster systems",
            "datacenter operations",
        ],
        credible_adjacent=["SRE", "GPU infrastructure"],
        learning_or_gap=[
            "production Kubernetes ownership",
            "security engineering",
            "heavy software engineering",
        ],
        avoid=["frontend"],
    )


def make_posting(title: str, description: str) -> JobPosting:
    return JobPosting(
        company_key="test",
        company_name="Test Company",
        source_type="greenhouse",
        source_url="https://example.com/job",
        title=title,
        location="Remote",
        description=description,
    )


def test_match_resume_to_posting_returns_strong_evidence() -> None:
    posting = make_posting(
        title="Senior Linux Infrastructure Engineer",
        description=(
            "Operate Linux infrastructure, HPC operations, cluster systems, "
            "and datacenter operations."
        ),
    )
    resume_text = (
        "Senior infrastructure engineer with Linux infrastructure, HPC operations, "
        "cluster systems, and datacenter operations experience."
    )

    result = match_resume_to_posting(posting, make_profile(), resume_text)

    assert result.label == "Very Strong"
    assert result.evidence == [
        "Linux infrastructure",
        "HPC operations",
        "cluster systems",
        "datacenter operations",
    ]
    assert result.gaps == []


def test_match_resume_to_posting_reports_gap() -> None:
    posting = make_posting(
        title="Senior SRE",
        description="Own Linux infrastructure and production Kubernetes ownership.",
    )
    resume_text = "Linux infrastructure and SRE experience."

    result = match_resume_to_posting(posting, make_profile(), resume_text)

    assert result.label == "Medium"
    assert result.evidence == ["Linux infrastructure", "SRE"]
    assert result.gaps == ["production Kubernetes ownership"]


def test_match_resume_to_posting_does_not_report_security_gap_for_adjacent_role() -> None:
    posting = make_posting(
        title="Senior Platform Engineer",
        description=(
            "Operate Linux infrastructure and partner with security engineering "
            "teams on infrastructure security improvements."
        ),
    )
    resume_text = "Linux infrastructure and platform operations experience."

    result = match_resume_to_posting(posting, make_profile(), resume_text)

    assert result.label == "Medium"
    assert result.evidence == ["Linux infrastructure"]
    assert result.gaps == []


def test_match_resume_to_posting_reports_security_gap_for_security_focused_role() -> None:
    posting = make_posting(
        title="Infrastructure Security Engineer",
        description="Own Linux infrastructure and security engineering programs.",
    )
    resume_text = "Linux infrastructure and platform operations experience."

    result = match_resume_to_posting(posting, make_profile(), resume_text)

    assert result.label == "Medium"
    assert result.evidence == ["Linux infrastructure"]
    assert result.gaps == ["security engineering"]


def test_match_resume_to_posting_returns_unknown_without_profile() -> None:
    posting = make_posting(
        title="Senior SRE",
        description="Linux infrastructure role.",
    )

    result = match_resume_to_posting(posting, None, None)

    assert result.label == "Unknown"
    assert result.evidence == []
    assert result.gaps == []