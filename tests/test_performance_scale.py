"""Verify the long-term scale gate uses fictional, isolated data."""

from scripts.validate_performance_scale import run_validation


def test_scale_validator_runs_with_small_fictional_dataset() -> None:
    timings = run_validation(
        companies=5,
        jobs=100,
        profiles=2,
        history=20,
        tracker=10,
        query_limit_seconds=3.0,
    )

    assert set(timings) == {
        "population",
        "job_lookup",
        "company_jobs",
        "profile_history",
        "profile_tracker",
        "tracker_page",
        "history_page",
    }
