"""Tests GUI profile display and safe resume uploads using temporary user files."""

from pathlib import Path

import pytest

from job_radar.config import ConfigError
from job_radar.profile_service import (
    build_candidate_profile_view,
    save_uploaded_resume,
)


def write_settings_file(settings_file: Path, profile_file: Path) -> None:
    settings_file.write_text(
        f"""
database_path: {settings_file.parent / "job_radar.sqlite3"}
reports_path: {settings_file.parent / "reports"}
logs_path: {settings_file.parent / "logs"}
candidate_profile_path: {profile_file}

""",
        encoding="utf-8",
    )


def write_profile_file(
    profile_file: Path,
    resume_file: Path,
    normalized_resume_file: Path,
) -> None:
    profile_file.write_text(
        f"""
candidate:
  name: Example Candidate
  resume:
    source_path: {resume_file}
    normalized_text_path: {normalized_resume_file}
  core_strengths:
    - Linux infrastructure
  credible_adjacent: []
  learning_or_gap: []
  avoid: []
""",
        encoding="utf-8",
    )


def test_build_candidate_profile_view_shows_resume_file_name_and_formatted_preview(
    tmp_path: Path,
) -> None:
    settings_file = tmp_path / "settings.yaml"
    profile_file = tmp_path / "profile.yaml"
    resume_file = tmp_path / "resume.md"
    normalized_resume_file = tmp_path / "resume.normalized.txt"

    write_settings_file(settings_file, profile_file)
    write_profile_file(profile_file, resume_file, normalized_resume_file)
    resume_file.write_text(
        "# Example Candidate\n\n## Professional Summary Linux infrastructure and HPC operations.",
        encoding="utf-8",
    )

    profile_view = build_candidate_profile_view(str(settings_file))

    assert profile_view.resume_source_file_name == "resume.md"
    assert profile_view.resume_preview == (
        "# Example Candidate\n\n"
        "## Professional Summary Linux infrastructure and HPC operations."
    )


def test_profile_service_resolves_active_user_paths(
    tmp_path: Path,
    monkeypatch,
) -> None:
    user_data_root = tmp_path / "user-data"
    settings_file = user_data_root / "config" / "settings.yaml"
    profile_file = user_data_root / "profiles" / "example" / "profile.yaml"
    resume_file = user_data_root / "profiles" / "example" / "resume.md"
    normalized_resume_file = (
        user_data_root
        / "profiles"
        / "example"
        / "resume.normalized.txt"
    )

    settings_file.parent.mkdir(parents=True)
    profile_file.parent.mkdir(parents=True)
    settings_file.write_text(
        """
database_path: data/job_radar.sqlite3
reports_path: reports
logs_path: logs
candidate_profile_path: profiles/example/profile.yaml

""",
        encoding="utf-8",
    )
    profile_file.write_text(
        """
candidate:
  name: Example Candidate
  resume:
    source_path: profiles/example/resume.md
    normalized_text_path: profiles/example/resume.normalized.txt
  core_strengths:
    - Linux infrastructure
  credible_adjacent: []
  learning_or_gap: []
  avoid: []
""",
        encoding="utf-8",
    )
    resume_file.write_text(
        "# Example Candidate\n\nLinux infrastructure",
        encoding="utf-8",
    )
    normalized_resume_file.write_text(
        "# Example Candidate Linux infrastructure\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("JOB_RADAR_DATA_DIR", str(user_data_root))

    profile_view = build_candidate_profile_view(None)

    assert profile_view.settings_path == str(settings_file.resolve())
    assert profile_view.candidate_profile_path == str(profile_file.resolve())
    assert profile_view.resume_source_path == str(resume_file.resolve())
    assert profile_view.normalized_text_path == str(
        normalized_resume_file.resolve()
    )
    assert profile_view.resume_preview == (
        "# Example Candidate\n"
        "Linux infrastructure"
    )


def test_save_uploaded_resume_replaces_existing_markdown_resume(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    profile_file = tmp_path / "profile.yaml"
    resume_file = tmp_path / "resume.md"
    normalized_resume_file = tmp_path / "resume.normalized.txt"

    write_settings_file(settings_file, profile_file)
    write_profile_file(profile_file, resume_file, normalized_resume_file)
    resume_file.write_text("Old resume", encoding="utf-8")

    result = save_uploaded_resume(
        str(settings_file),
        "updated-resume.md",
        b"# Updated Resume\n\nLinux infrastructure and HPC operations",
    )

    assert result.resume_source_path == str(resume_file)
    assert result.normalized_text_path == str(normalized_resume_file)
    assert resume_file.read_text(encoding="utf-8") == (
        "# Updated Resume\n\nLinux infrastructure and HPC operations"
    )
    assert normalized_resume_file.read_text(encoding="utf-8") == (
        "# Updated Resume\nLinux infrastructure and HPC operations\n"
    )

    profile_view = build_candidate_profile_view(str(settings_file))

    assert profile_view.resume_source_path == str(resume_file)
    assert profile_view.resume_source_file_name == "resume.md"
    assert profile_view.normalized_text_path == str(normalized_resume_file)
    assert profile_view.resume_preview == (
        "# Updated Resume\n"
        "Linux infrastructure and HPC operations"
    )


def test_save_uploaded_resume_uses_active_user_paths(
    tmp_path: Path,
    monkeypatch,
) -> None:
    user_data_root = tmp_path / "user-data"
    settings_file = user_data_root / "config" / "settings.yaml"
    profile_file = user_data_root / "profiles" / "example" / "profile.yaml"
    resume_file = user_data_root / "profiles" / "example" / "resume.md"
    normalized_resume_file = (
        user_data_root
        / "profiles"
        / "example"
        / "resume.normalized.txt"
    )

    settings_file.parent.mkdir(parents=True)
    profile_file.parent.mkdir(parents=True)
    settings_file.write_text(
        """
database_path: data/job_radar.sqlite3
reports_path: reports
logs_path: logs
candidate_profile_path: profiles/example/profile.yaml

""",
        encoding="utf-8",
    )
    profile_file.write_text(
        """
candidate:
  name: Example Candidate
  resume:
    source_path: profiles/example/resume.md
    normalized_text_path: profiles/example/resume.normalized.txt
  core_strengths: []
  credible_adjacent: []
  learning_or_gap: []
  avoid: []
""",
        encoding="utf-8",
    )
    resume_file.write_text("Old resume", encoding="utf-8")
    monkeypatch.setenv("JOB_RADAR_DATA_DIR", str(user_data_root))

    result = save_uploaded_resume(
        None,
        "updated-resume.md",
        b"# Updated Resume\n\nLinux infrastructure",
    )

    assert result.resume_source_path == str(resume_file.resolve())
    assert result.normalized_text_path == str(
        normalized_resume_file.resolve()
    )
    assert resume_file.read_text(encoding="utf-8") == (
        "# Updated Resume\n\nLinux infrastructure"
    )
    assert normalized_resume_file.read_text(encoding="utf-8") == (
        "# Updated Resume\nLinux infrastructure\n"
    )


def test_save_uploaded_resume_updates_source_extension_for_docx_upload(
    tmp_path: Path,
) -> None:
    settings_file = tmp_path / "settings.yaml"
    profile_file = tmp_path / "profile.yaml"
    resume_file = tmp_path / "resume.md"
    normalized_resume_file = tmp_path / "resume.normalized.txt"

    write_settings_file(settings_file, profile_file)
    write_profile_file(profile_file, resume_file, normalized_resume_file)
    resume_file.write_text("Old resume", encoding="utf-8")

    with pytest.raises(ConfigError, match="Could not read DOCX resume file"):
        save_uploaded_resume(
            str(settings_file),
            "updated-resume.docx",
            b"not a real docx",
        )

    assert resume_file.read_text(encoding="utf-8") == "Old resume"
    assert not (tmp_path / "resume.docx").exists()


def test_save_uploaded_resume_rejects_unsupported_upload_type(
    tmp_path: Path,
) -> None:
    settings_file = tmp_path / "settings.yaml"
    profile_file = tmp_path / "profile.yaml"
    resume_file = tmp_path / "resume.md"
    normalized_resume_file = tmp_path / "resume.normalized.txt"

    write_settings_file(settings_file, profile_file)
    write_profile_file(profile_file, resume_file, normalized_resume_file)

    with pytest.raises(ConfigError, match="Unsupported resume format: .csv"):
        save_uploaded_resume(
            str(settings_file),
            "resume.csv",
            b"name,experience",
        )
