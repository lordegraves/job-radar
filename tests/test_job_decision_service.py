"""Tests profile-owned saved and passed jobs without creating applications."""

from pathlib import Path

import pytest

from job_radar.job_decision_service import (
    DECISION_PASSED,
    DECISION_SAVED,
    JobDecisionError,
    delete_job_decision,
    get_decided_job_ids,
    list_job_decisions,
    save_job_decision,
)
from job_radar.profile_models import ManagedProfile
from job_radar.profile_storage import create_profile


def create_test_profile(database_path: Path, profile_id: str) -> None:
    create_profile(
        database_path,
        ManagedProfile(
            profile_id=profile_id,
            display_name=f"Synthetic {profile_id}",
        ),
    )


def test_job_decisions_are_profile_owned_and_reversible(tmp_path: Path) -> None:
    database_path = tmp_path / "junior.sqlite3"
    create_test_profile(database_path, "profile_11111111")
    create_test_profile(database_path, "profile_22222222")

    result = save_job_decision(
        database_path,
        profile_id="profile_11111111",
        job_radar_id="jr-example-12345678",
        decision=DECISION_SAVED,
        company="Example Company",
        title="Example Role",
        source_url="https://example.invalid/jobs/1",
        location="Remote",
    )

    assert result == "new"
    assert get_decided_job_ids(
        database_path,
        profile_id="profile_11111111",
    ) == {"jr-example-12345678"}
    assert get_decided_job_ids(
        database_path,
        profile_id="profile_22222222",
    ) == set()

    result = save_job_decision(
        database_path,
        profile_id="profile_11111111",
        job_radar_id="jr-example-12345678",
        decision=DECISION_PASSED,
        company="Example Company",
        title="Example Role",
        source_url="https://example.invalid/jobs/1",
        location="Remote",
        notes="Synthetic note",
    )

    assert result == "updated"
    passed = list_job_decisions(
        database_path,
        profile_id="profile_11111111",
        decision=DECISION_PASSED,
    )
    assert len(passed) == 1
    assert passed[0].notes == "Synthetic note"
    assert delete_job_decision(
        database_path,
        profile_id="profile_11111111",
        job_radar_id="jr-example-12345678",
    )
    assert get_decided_job_ids(
        database_path,
        profile_id="profile_11111111",
    ) == set()


def test_job_decision_rejects_unknown_choice(tmp_path: Path) -> None:
    database_path = tmp_path / "junior.sqlite3"
    create_test_profile(database_path, "profile_11111111")

    with pytest.raises(JobDecisionError, match="Save for later or Pass"):
        save_job_decision(
            database_path,
            profile_id="profile_11111111",
            job_radar_id="jr-example-12345678",
            decision="ignore",
            company="Example Company",
            title="Example Role",
            source_url=None,
            location=None,
        )
