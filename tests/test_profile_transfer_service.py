"""Verify profile configuration transfer excludes résumé and active selection."""

import json
from pathlib import Path

import pytest

from job_radar.config import ConfigError
from job_radar.employer_models import EmployerSource
from job_radar.employer_storage import (
    is_profile_employer_enabled,
    set_profile_employer_enabled,
    upsert_employer_source,
)
from job_radar.profile_models import FitSignal, ManagedProfile, ProfilePreferences, build_managed_resume
from job_radar.profile_scoring import build_neutral_scoring_config
from job_radar.profile_storage import create_profile, get_active_profile, list_profiles, set_active_profile
from job_radar.profile_transfer_service import export_profile, import_profile


def test_profile_transfer_creates_new_inactive_profile_without_resume(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite3"
    destination = tmp_path / "destination.sqlite3"
    employer = EmployerSource(
        employer_id="example_company",
        name="Example Company",
        source_type="greenhouse",
        source_config={"source_slug": "example-company"},
    )
    upsert_employer_source(source, employer)
    upsert_employer_source(destination, employer)
    exported = ManagedProfile(
        profile_id="profile_11111111",
        display_name="Tester Profile",
        preferences=ProfilePreferences(
            target_roles=("Infrastructure Specialist",),
            core_strengths=("Linux operations",),
            exclusions=("Commission sales",),
            work_arrangements=("Remote",),
        ),
        resume=build_managed_resume(".pdf"),
        company_ids=("example_company",),
        fit_signals=(
            FitSignal(
                term="Linux operations",
                category="strong",
                explanation="Private résumé wording",
                evidence_source="resume",
            ),
        ),
        scoring_config=build_neutral_scoring_config(),
    )
    current = ManagedProfile(
        profile_id="profile_22222222",
        display_name="Current Profile",
    )
    create_profile(source, exported)
    set_profile_employer_enabled(
        source,
        exported.profile_id,
        "example_company",
        enabled=False,
    )
    create_profile(destination, current)
    set_active_profile(destination, current.profile_id)

    _, content = export_profile(source, exported.profile_id)
    result = import_profile(destination, content)

    assert result.profile.profile_id not in {exported.profile_id, current.profile_id}
    assert result.profile.display_name == "Tester Profile"
    assert result.profile.resume is None
    assert result.profile.preferences == exported.preferences
    assert result.profile.company_ids == ("example_company",)
    assert not is_profile_employer_enabled(
        destination,
        result.profile.profile_id,
        "example_company",
    )
    assert result.profile.fit_signals[0].explanation == "Imported profile preference"
    assert get_active_profile(destination) == current
    assert len(list_profiles(destination)) == 2
    text = content.decode("utf-8")
    assert "Private résumé wording" not in text
    assert "resume.pdf" not in text
    assert exported.profile_id not in text


def test_profile_export_normalizes_legacy_missing_review_signals(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.sqlite3"
    scoring = build_neutral_scoring_config()
    del scoring["top_matches"]["review_signals"]
    profile = ManagedProfile(
        profile_id="profile_11111111",
        display_name="Legacy Profile",
        scoring_config=scoring,
    )
    create_profile(source, profile)

    _, content = export_profile(source, profile.profile_id)

    payload = json.loads(content)
    assert payload["profile"]["scoring_config"]["top_matches"][
        "review_signals"
    ] == []


def test_profile_import_rejects_unknown_fields(tmp_path: Path) -> None:
    payload = {
        "format": "junior-profile-configuration",
        "transfer_schema_version": 1,
        "profile_schema_version": 1,
        "profile": {},
        "excluded": [],
        "unexpected": "not allowed",
    }

    with pytest.raises(ConfigError, match="missing or unsupported"):
        import_profile(tmp_path / "destination.sqlite3", json.dumps(payload).encode())
