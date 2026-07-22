"""Tests GUI profile operations with synthetic databases and resume files only."""

from pathlib import Path

import pytest

from job_radar.config import ConfigError
from job_radar.profile_management import (
    MAX_MANAGED_PROFILES,
    archive_managed_profile,
    build_profile_management_view,
    create_managed_profile,
    delete_managed_profile,
    save_managed_profile_resume,
    select_managed_profile,
    update_managed_profile_from_form,
    update_managed_search_preferences,
)
from job_radar.tracker.tracker_models import ApplicationRecord
from job_radar.tracker.tracker_storage import upsert_application


def write_settings(root: Path) -> Path:
    settings_path = root / "config" / "settings.yaml"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(
        """
database_path: data/job_radar.sqlite3
reports_path: reports
logs_path: logs
""",
        encoding="utf-8",
    )
    return settings_path


def test_create_edit_select_archive_and_restore_profile(tmp_path: Path) -> None:
    settings_path = write_settings(tmp_path)
    first = create_managed_profile(
        str(settings_path), "First Search", base_directory=tmp_path
    )
    second = create_managed_profile(
        str(settings_path), "Second Search", base_directory=tmp_path
    )

    view = build_profile_management_view(
        str(settings_path), base_directory=tmp_path
    )
    assert view.active_profile_id == second.profile_id
    assert [profile.display_name for profile in view.profiles] == [
        "First Search",
        "Second Search",
    ]

    updated = update_managed_profile_from_form(
        str(settings_path),
        first.profile_id,
        {
            "display_name": "Infrastructure Search",
            "target_roles": "Platform Engineer\nSRE",
            "core_strengths": "Linux\nHPC",
            "exclusions": "Commission sales",
            "compensation_floor_usd": "$150,000",
            "compensation_target_usd": "180000",
            "travel_tolerance": "Limited",
        },
        base_directory=tmp_path,
    )
    assert updated.preferences.target_roles == ("Platform Engineer", "SRE")
    assert updated.preferences.core_strengths == ("Linux", "HPC")
    assert updated.preferences.compensation_floor_usd == 150000

    select_managed_profile(
        str(settings_path), first.profile_id, base_directory=tmp_path
    )
    assert build_profile_management_view(
        str(settings_path), base_directory=tmp_path
    ).active_profile_id == first.profile_id

    archive_managed_profile(
        str(settings_path), first.profile_id, archived=True, base_directory=tmp_path
    )
    assert build_profile_management_view(
        str(settings_path), base_directory=tmp_path
    ).active_profile_id is None

    archive_managed_profile(
        str(settings_path), first.profile_id, archived=False, base_directory=tmp_path
    )
    restored = build_profile_management_view(
        str(settings_path), base_directory=tmp_path
    ).profiles[0]
    assert restored.archived is False


def test_search_preferences_preserve_resume_owned_profile_fields(
    tmp_path: Path,
) -> None:
    settings_path = write_settings(tmp_path)
    profile = create_managed_profile(
        str(settings_path), "Infrastructure Search", base_directory=tmp_path
    )
    update_managed_profile_from_form(
        str(settings_path),
        profile.profile_id,
        {
            "display_name": "Infrastructure Search",
            "core_strengths": "Linux\nHPC",
            "credible_adjacent": "Platform engineering",
            "compensation_target_usd": "185000",
        },
        base_directory=tmp_path,
    )

    updated = update_managed_search_preferences(
        str(settings_path),
        occupation_selections_json=(
            '[{"value":"15-1252.00","label":"Platform Engineers"}]'
        ),
        location_selections_json=(
            '[{"value":"place:0827425","label":"Fort Collins, Colorado",'
            '"latitude":40.5853,"longitude":-105.0844,"radius":25}]'
        ),
        seniority_levels=["Mid-level", "Senior"],
        employment_types=["Full-time", "Contract"],
        work_arrangements=["Remote", "Hybrid"],
        schedule_preference="Any schedule",
        compensation_floor_usd="160000",
        travel_percentage="15",
        base_directory=tmp_path,
    )

    assert updated.preferences.target_roles == ("Platform Engineers",)
    assert updated.preferences.core_strengths == ("Linux", "HPC")
    assert updated.preferences.credible_adjacent == ("Platform engineering",)
    assert updated.preferences.compensation_target_usd == 185000
    assert updated.preferences.compensation_floor_usd == 160000
    assert updated.preferences.travel_tolerance == "15"


def test_managed_resume_upload_uses_app_owned_names(tmp_path: Path) -> None:
    settings_path = write_settings(tmp_path)
    profile = create_managed_profile(
        str(settings_path), "Resume Search", base_directory=tmp_path
    )

    save_managed_profile_resume(
        str(settings_path),
        "My Resume Final Version.md",
        b"# Example Candidate\n\nLinux and platform operations",
        base_directory=tmp_path,
    )

    resume_directory = tmp_path / "resumes" / profile.profile_id
    assert (resume_directory / "resume.md").read_bytes() == (
        b"# Example Candidate\n\nLinux and platform operations"
    )
    assert (resume_directory / "resume.normalized.txt").read_text(
        encoding="utf-8"
    ) == "# Example Candidate Linux and platform operations\n"
    assert not (resume_directory / "My Resume Final Version.md").exists()


def test_invalid_managed_resume_does_not_replace_working_resume(
    tmp_path: Path,
) -> None:
    settings_path = write_settings(tmp_path)
    profile = create_managed_profile(
        str(settings_path), "Resume Search", base_directory=tmp_path
    )
    save_managed_profile_resume(
        str(settings_path),
        "original.md",
        b"Working resume",
        base_directory=tmp_path,
    )
    resume_path = tmp_path / "resumes" / profile.profile_id / "resume.md"

    with pytest.raises(ConfigError, match="Could not read PDF resume file"):
        save_managed_profile_resume(
            str(settings_path),
            "broken.pdf",
            b"not a PDF",
            base_directory=tmp_path,
        )

    assert resume_path.read_bytes() == b"Working resume"


def test_database_failure_rolls_back_managed_resume_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings_path = write_settings(tmp_path)
    profile = create_managed_profile(
        str(settings_path), "Resume Search", base_directory=tmp_path
    )
    save_managed_profile_resume(
        str(settings_path),
        "original.md",
        b"Working resume",
        base_directory=tmp_path,
    )
    resume_directory = tmp_path / "resumes" / profile.profile_id
    resume_path = resume_directory / "resume.md"
    normalized_path = resume_directory / "resume.normalized.txt"
    original_normalized = normalized_path.read_bytes()
    monkeypatch.setattr(
        "job_radar.profile_management.update_profile",
        lambda *_args, **_kwargs: False,
    )

    with pytest.raises(ConfigError, match="no longer exists"):
        save_managed_profile_resume(
            str(settings_path),
            "replacement.md",
            b"Replacement resume",
            base_directory=tmp_path,
        )

    assert resume_path.read_bytes() == b"Working resume"
    assert normalized_path.read_bytes() == original_normalized
    assert not list(resume_directory.glob(".*-backup*"))


def test_delete_profile_removes_only_its_database_data_and_resume(
    tmp_path: Path,
) -> None:
    settings_path = write_settings(tmp_path)
    first = create_managed_profile(
        str(settings_path), "First Search", base_directory=tmp_path
    )
    save_managed_profile_resume(
        str(settings_path),
        "first.md",
        b"First resume",
        base_directory=tmp_path,
    )
    second = create_managed_profile(
        str(settings_path), "Second Search", base_directory=tmp_path
    )
    save_managed_profile_resume(
        str(settings_path),
        "second.md",
        b"Second resume",
        base_directory=tmp_path,
    )

    delete_managed_profile(
        str(settings_path), second.profile_id, base_directory=tmp_path
    )

    view = build_profile_management_view(str(settings_path), base_directory=tmp_path)
    assert [profile.profile_id for profile in view.profiles] == [first.profile_id]
    assert view.active_profile_id == first.profile_id
    assert not (tmp_path / "resumes" / second.profile_id).exists()
    assert (tmp_path / "resumes" / first.profile_id / "resume.md").exists()


def test_delete_profile_preserves_owned_tracker_activity(tmp_path: Path) -> None:
    settings_path = write_settings(tmp_path)
    profile = create_managed_profile(
        str(settings_path), "Protected Search", base_directory=tmp_path
    )
    database_path = tmp_path / "data" / "job_radar.sqlite3"
    upsert_application(
        database_path,
        ApplicationRecord(
            job_radar_id="jr-protected-12345678",
            company_name="Synthetic Company",
            role_title="Synthetic Role",
        ),
        profile_id=profile.profile_id,
    )

    with pytest.raises(ConfigError, match="cannot be deleted"):
        delete_managed_profile(
            str(settings_path), profile.profile_id, base_directory=tmp_path
        )

    view = build_profile_management_view(str(settings_path), base_directory=tmp_path)
    assert [item.profile_id for item in view.profiles] == [profile.profile_id]


def test_profile_limit_requires_deleting_before_creating_another(
    tmp_path: Path,
) -> None:
    settings_path = write_settings(tmp_path)
    for number in range(MAX_MANAGED_PROFILES):
        create_managed_profile(
            str(settings_path), f"Profile {number}", base_directory=tmp_path
        )

    with pytest.raises(ConfigError, match="up to 5 profiles"):
        create_managed_profile(
            str(settings_path), "One Too Many", base_directory=tmp_path
        )
