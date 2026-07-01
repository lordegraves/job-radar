from job_radar.history_match import (
    build_posting_history_context,
    find_history_matches,
    summarize_history_risk,
)
from job_radar.job_history import JobHistoryRecord
from job_radar.models import JobPosting


def make_posting(
    company_name: str = "Example AI",
    title: str = "Senior Infrastructure Engineer",
) -> JobPosting:
    return JobPosting(
        company_key="example_ai",
        company_name=company_name,
        source_type="greenhouse",
        source_job_id="123",
        source_url="https://boards.greenhouse.io/exampleai/jobs/123",
        title=title,
        location="Remote",
        description="Build Linux infrastructure.",
        canonical_key="example-ai:senior-infrastructure-engineer:remote",
        content_hash="hash",
    )


def make_history_record(
    company: str = "Example AI",
    role: str = "Senior Infrastructure Engineer",
    history_type: str = "Pipeline",
    outcome_category: str = "No Interview",
    technical_match: str = "Strong",
    primary_blocker: str | None = None,
    include_in_job_radar: bool = True,
    import_key: str = "pipeline:example-ai:senior-infrastructure-engineer",
) -> JobHistoryRecord:
    return JobHistoryRecord(
        history_type=history_type,
        company=company,
        role=role,
        source="LinkedIn",
        ats_platform="Greenhouse",
        work_arrangement="Remote",
        location="Remote",
        comp_range="$160k-$200k",
        event_date="2026-06-01",
        status="Rejected - No Interview",
        outcome_category=outcome_category,
        recruiter_contact="Unknown",
        technical_match=technical_match,
        hiring_probability="Low",
        skills_signals="Linux, HPC, Infrastructure",
        primary_blocker=primary_blocker,
        secondary_blocker=None,
        revisit="No",
        include_in_job_radar=include_in_job_radar,
        import_key=import_key,
        notes="Form rejection.",
    )


def test_find_history_matches_exact_company_and_meaningful_title_overlap() -> None:
    posting = make_posting()
    record = make_history_record()

    matches = find_history_matches(posting, [record])

    assert len(matches) == 1
    assert matches[0].record == record
    assert matches[0].matched_tokens == ("infrastructure",)
    assert matches[0].risk_level == "caution"
    assert matches[0].risk_reasons == ("prior_no_interview_despite_strong_match",)


def test_find_history_matches_ignores_same_company_with_weak_role_overlap() -> None:
    posting = make_posting(title="Senior Infrastructure Engineer")
    record = make_history_record(role="Frontend Engineer")

    assert find_history_matches(posting, [record]) == []


def test_find_history_matches_ignores_different_company_for_first_pass() -> None:
    posting = make_posting(company_name="Example AI")
    record = make_history_record(company="Other AI")

    assert find_history_matches(posting, [record]) == []


def test_find_history_matches_ignores_excluded_history_records() -> None:
    posting = make_posting()
    record = make_history_record(include_in_job_radar=False)

    assert find_history_matches(posting, [record]) == []


def test_build_posting_history_context_formats_no_interview_context() -> None:
    posting = make_posting()
    record = make_history_record(
        outcome_category="No Interview",
        technical_match="Strong",
    )

    context = build_posting_history_context(posting, [record])

    assert context == [
        (
            "Prior similar application at Example AI ended "
            "No Interview despite Strong technical match"
        )
    ]


def test_build_posting_history_context_formats_skipped_blocker_context() -> None:
    posting = make_posting()
    record = make_history_record(
        history_type="Reviewed",
        outcome_category="Skipped / Avoid",
        technical_match="Very Strong",
        primary_blocker="Production Kubernetes",
    )

    context = build_posting_history_context(posting, [record])

    assert context == [
        (
            "Previously reviewed and skipped similar role at Example AI; "
            "prior blocker: Production Kubernetes"
        )
    ]


def test_build_posting_history_context_returns_empty_list_without_match() -> None:
    posting = make_posting(title="Senior Infrastructure Engineer")
    record = make_history_record(role="Frontend Engineer")

    assert build_posting_history_context(posting, [record]) == []


def test_find_history_matches_marks_skipped_blocker_for_review() -> None:
    posting = make_posting()
    record = make_history_record(
        history_type="Reviewed",
        outcome_category="Skipped / Avoid",
        technical_match="Very Strong",
        primary_blocker="Production Kubernetes",
    )

    matches = find_history_matches(posting, [record])

    assert len(matches) == 1
    assert matches[0].risk_level == "blocker_review"
    assert matches[0].risk_reasons == ("prior_blocker:kubernetes_production",)


def test_find_history_matches_marks_prior_similar_role_as_neutral() -> None:
    posting = make_posting()
    record = make_history_record(
        outcome_category="Reviewed",
        technical_match="Unknown",
        primary_blocker=None,
    )

    matches = find_history_matches(posting, [record])

    assert len(matches) == 1
    assert matches[0].risk_level == "neutral"
    assert matches[0].risk_reasons == ("prior_similar_role",)


def test_summarize_history_risk_returns_highest_risk_and_unique_reasons() -> None:
    posting = make_posting()
    caution_record = make_history_record(
        outcome_category="No Interview",
        technical_match="Strong",
    )
    blocker_record = make_history_record(
        history_type="Reviewed",
        outcome_category="Skipped / Avoid",
        technical_match="Very Strong",
        primary_blocker="Production Kubernetes",
        import_key="reviewed:example-ai:senior-infrastructure-engineer",
    )

    matches = find_history_matches(posting, [caution_record, blocker_record])

    risk_level, risk_reasons = summarize_history_risk(matches)

    assert risk_level == "blocker_review"
    assert risk_reasons == [
        "prior_no_interview_despite_strong_match",
        "prior_blocker:kubernetes_production",
    ]
