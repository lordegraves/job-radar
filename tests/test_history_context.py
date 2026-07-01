from job_radar.history_context import build_history_context
from job_radar.history_summary import HistorySummary


def test_build_history_context_returns_empty_list_without_history() -> None:
    summary = HistorySummary(
        total_records=0,
        history_type_counts={},
        outcome_category_counts={},
        primary_blocker_counts={},
        technical_match_outcome_counts={},
    )

    assert build_history_context(summary) == []


def test_build_history_context_summarizes_prior_outcomes_and_blockers() -> None:
    summary = HistorySummary(
        total_records=70,
        history_type_counts={
            "Pipeline": 55,
            "Reviewed": 15,
        },
        outcome_category_counts={
            "No Interview": 11,
            "Interview Rejection": 1,
            "Skipped / Avoid": 15,
        },
        primary_blocker_counts={
            "Unknown": 55,
            "Compensation": 3,
            "Production Kubernetes": 2,
            "Travel": 1,
        },
        technical_match_outcome_counts={
            "Very Strong / No Interview": 3,
            "Strong / No Interview": 6,
        },
    )

    context = build_history_context(summary)

    assert context == [
        "Imported history: 70 records (55 pipeline, 15 reviewed)",
        (
            "Prior applications show technical match alone has not guaranteed "
            "interviews (11 no-interview outcomes)"
        ),
        "Prior interview rejections recorded: 1",
        "Prior reviewed roles skipped or avoided: 15",
        (
            "Strong technical matches with no interview: "
            "Very Strong / No Interview: 3, Strong / No Interview: 6"
        ),
        "Common prior blockers: Compensation: 3, Production Kubernetes: 2, Travel: 1",
    ]