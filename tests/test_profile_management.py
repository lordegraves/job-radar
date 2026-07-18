"""Tests GUI profile operations with synthetic databases and resume files only."""

from pathlib import Path

import pytest

from job_radar.config import ConfigError
from job_radar.profile_management import (
    archive_managed_profile,
    build_profile_management_view,
    create_managed_profile,
    save_managed_profile_resume,
    select_managed_profile,
    update_managed_profile_from_form,
)


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
