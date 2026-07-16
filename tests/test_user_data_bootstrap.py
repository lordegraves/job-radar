from pathlib import Path

import pytest

from job_radar.runtime_paths import UserDataPaths
from job_radar.user_data_bootstrap import (
    UserDataBootstrapError,
    copy_bootstrap_file,
    copy_bootstrap_tree,
    create_user_data_directories,
)


def test_create_user_data_directories_creates_standard_layout(
    tmp_path: Path,
) -> None:
    user_data_paths = UserDataPaths.from_root(tmp_path / "JobRadar")

    create_user_data_directories(user_data_paths)

    assert user_data_paths.root.is_dir()
    assert user_data_paths.config.is_dir()
    assert user_data_paths.data.is_dir()
    assert user_data_paths.logs.is_dir()
    assert user_data_paths.profiles.is_dir()
    assert user_data_paths.reports.is_dir()


def test_copy_bootstrap_file_copies_missing_destination(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source" / "settings.yaml"
    destination = tmp_path / "destination" / "config" / "settings.yaml"
    source.parent.mkdir(parents=True)
    source.write_text("database_path: data/job_radar.sqlite3\n", encoding="utf-8")

    result = copy_bootstrap_file(source, destination)

    assert result.source == source.resolve()
    assert result.destination == destination.resolve()
    assert result.copied is True
    assert destination.read_text(encoding="utf-8") == (
        "database_path: data/job_radar.sqlite3\n"
    )


def test_copy_bootstrap_file_preserves_existing_destination(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.yaml"
    destination = tmp_path / "destination.yaml"
    source.write_text("source content\n", encoding="utf-8")
    destination.write_text("existing content\n", encoding="utf-8")

    result = copy_bootstrap_file(source, destination)

    assert result.copied is False
    assert destination.read_text(encoding="utf-8") == "existing content\n"


def test_copy_bootstrap_tree_preserves_relative_file_layout(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source-profiles"
    destination_root = tmp_path / "destination-profiles"
    profile_directory = source_root / "clayton"
    profile_directory.mkdir(parents=True)
    (profile_directory / "profile.yaml").write_text(
        "candidate:\n  name: Clayton\n",
        encoding="utf-8",
    )
    (profile_directory / "resume.md").write_text(
        "# Resume\n",
        encoding="utf-8",
    )

    results = copy_bootstrap_tree(source_root, destination_root)

    assert len(results) == 2
    assert all(result.copied for result in results)
    assert (
        destination_root / "clayton" / "profile.yaml"
    ).read_text(encoding="utf-8") == "candidate:\n  name: Clayton\n"
    assert (
        destination_root / "clayton" / "resume.md"
    ).read_text(encoding="utf-8") == "# Resume\n"


def test_copy_bootstrap_tree_preserves_existing_destination_files(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source-profiles"
    destination_root = tmp_path / "destination-profiles"
    source_profile = source_root / "clayton" / "profile.yaml"
    destination_profile = destination_root / "clayton" / "profile.yaml"
    source_profile.parent.mkdir(parents=True)
    destination_profile.parent.mkdir(parents=True)
    source_profile.write_text("source profile\n", encoding="utf-8")
    destination_profile.write_text("existing profile\n", encoding="utf-8")

    results = copy_bootstrap_tree(source_root, destination_root)

    assert len(results) == 1
    assert results[0].copied is False
    assert destination_profile.read_text(encoding="utf-8") == (
        "existing profile\n"
    )


def test_copy_bootstrap_tree_rejects_missing_source_directory(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "missing-profiles"
    destination_root = tmp_path / "destination-profiles"

    with pytest.raises(
        UserDataBootstrapError,
        match="Bootstrap source directory does not exist",
    ):
        copy_bootstrap_tree(source_root, destination_root)


def test_copy_bootstrap_tree_rejects_file_destination(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source-profiles"
    destination_root = tmp_path / "destination-profiles"
    source_root.mkdir()
    destination_root.write_text("not a directory\n", encoding="utf-8")

    with pytest.raises(
        UserDataBootstrapError,
        match="Bootstrap destination is not a directory",
    ):
        copy_bootstrap_tree(source_root, destination_root)


def test_copy_bootstrap_file_rejects_missing_source(
    tmp_path: Path,
) -> None:
    source = tmp_path / "missing.yaml"
    destination = tmp_path / "destination.yaml"

    with pytest.raises(
        UserDataBootstrapError,
        match="Bootstrap source file does not exist",
    ):
        copy_bootstrap_file(source, destination)


def test_copy_bootstrap_file_rejects_directory_destination(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.yaml"
    destination = tmp_path / "destination"
    source.write_text("source content\n", encoding="utf-8")
    destination.mkdir()

    with pytest.raises(
        UserDataBootstrapError,
        match="Bootstrap destination is not a file",
    ):
        copy_bootstrap_file(source, destination)
