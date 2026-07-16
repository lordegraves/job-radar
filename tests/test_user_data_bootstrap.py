import sqlite3
from pathlib import Path

import pytest

from job_radar.runtime_paths import UserDataPaths
from job_radar.user_data_bootstrap import (
    UserDataBootstrapError,
    bootstrap_user_configuration,
    copy_bootstrap_database,
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


def test_bootstrap_user_configuration_copies_settings_and_profiles(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    source_settings = source_root / "config" / "settings.yaml"
    source_company_config = source_root / "config" / "target-companies.yaml"
    source_scoring_config = source_root / "config" / "scoring.yaml"
    source_profile = source_root / "profiles" / "clayton" / "profile.yaml"
    source_resume = source_root / "profiles" / "clayton" / "resume.md"
    source_settings.parent.mkdir(parents=True)
    source_profile.parent.mkdir(parents=True)
    source_settings.write_text(
        "database_path: data/job_radar.sqlite3\n",
        encoding="utf-8",
    )
    source_company_config.write_text(
        "companies: []\n",
        encoding="utf-8",
    )
    source_scoring_config.write_text(
        "positive_keywords: {}\n",
        encoding="utf-8",
    )
    source_profile.write_text(
        "candidate:\n  name: Clayton\n",
        encoding="utf-8",
    )
    source_resume.write_text("# Resume\n", encoding="utf-8")
    user_data_paths = UserDataPaths.from_root(tmp_path / "user-data")

    result = bootstrap_user_configuration(
        source_settings_path=source_settings,
        source_company_config_path=source_company_config,
        source_scoring_config_path=source_scoring_config,
        source_profiles_path=source_root / "profiles",
        user_data_paths=user_data_paths,
    )

    assert result.user_data_paths == user_data_paths
    assert result.settings_result.copied is True
    assert result.company_config_result.copied is True
    assert result.scoring_config_result.copied is True
    assert len(result.profile_results) == 2
    assert result.database_result is None
    assert len(result.all_results) == 5
    assert len(result.copied_files) == 5
    assert result.preserved_files == ()
    assert (
        user_data_paths.config / "settings.yaml"
    ).read_text(encoding="utf-8") == (
        "database_path: data/job_radar.sqlite3\n"
    )
    assert (
        user_data_paths.config / "target-companies.yaml"
    ).read_text(encoding="utf-8") == "companies: []\n"
    assert (
        user_data_paths.config / "scoring.yaml"
    ).read_text(encoding="utf-8") == "positive_keywords: {}\n"
    assert (
        user_data_paths.profiles / "clayton" / "profile.yaml"
    ).read_text(encoding="utf-8") == "candidate:\n  name: Clayton\n"
    assert (
        user_data_paths.profiles / "clayton" / "resume.md"
    ).read_text(encoding="utf-8") == "# Resume\n"


def test_bootstrap_user_configuration_preserves_existing_user_files(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    source_settings = source_root / "config" / "settings.yaml"
    source_company_config = source_root / "config" / "target-companies.yaml"
    source_scoring_config = source_root / "config" / "scoring.yaml"
    source_profile = source_root / "profiles" / "clayton" / "profile.yaml"
    source_settings.parent.mkdir(parents=True)
    source_profile.parent.mkdir(parents=True)
    source_settings.write_text("source settings\n", encoding="utf-8")
    source_company_config.write_text("source companies\n", encoding="utf-8")
    source_scoring_config.write_text("source scoring\n", encoding="utf-8")
    source_profile.write_text("source profile\n", encoding="utf-8")
    user_data_paths = UserDataPaths.from_root(tmp_path / "user-data")
    existing_settings = user_data_paths.config / "settings.yaml"
    existing_company_config = (
        user_data_paths.config / "target-companies.yaml"
    )
    existing_scoring_config = user_data_paths.config / "scoring.yaml"
    existing_profile = user_data_paths.profiles / "clayton" / "profile.yaml"
    existing_settings.parent.mkdir(parents=True)
    existing_profile.parent.mkdir(parents=True)
    existing_settings.write_text("existing settings\n", encoding="utf-8")
    existing_company_config.write_text(
        "existing companies\n",
        encoding="utf-8",
    )
    existing_scoring_config.write_text(
        "existing scoring\n",
        encoding="utf-8",
    )
    existing_profile.write_text("existing profile\n", encoding="utf-8")

    result = bootstrap_user_configuration(
        source_settings_path=source_settings,
        source_company_config_path=source_company_config,
        source_scoring_config_path=source_scoring_config,
        source_profiles_path=source_root / "profiles",
        user_data_paths=user_data_paths,
    )

    assert result.copied_files == ()
    assert len(result.preserved_files) == 4
    assert existing_settings.read_text(encoding="utf-8") == (
        "existing settings\n"
    )
    assert existing_company_config.read_text(encoding="utf-8") == (
        "existing companies\n"
    )
    assert existing_scoring_config.read_text(encoding="utf-8") == (
        "existing scoring\n"
    )
    assert existing_profile.read_text(encoding="utf-8") == (
        "existing profile\n"
    )


def test_bootstrap_user_configuration_copies_optional_database(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    source_settings = source_root / "config" / "settings.yaml"
    source_company_config = source_root / "config" / "target-companies.yaml"
    source_scoring_config = source_root / "config" / "scoring.yaml"
    source_profiles = source_root / "profiles"
    source_profile = source_profiles / "clayton" / "profile.yaml"
    source_database = source_root / "data" / "job_radar.sqlite3"
    source_settings.parent.mkdir(parents=True)
    source_profile.parent.mkdir(parents=True)
    source_database.parent.mkdir(parents=True)
    source_settings.write_text(
        "database_path: data/job_radar.sqlite3\n",
        encoding="utf-8",
    )
    source_company_config.write_text("companies: []\n", encoding="utf-8")
    source_scoring_config.write_text(
        "positive_keywords: {}\n",
        encoding="utf-8",
    )
    source_profile.write_text(
        "candidate:\n  name: Clayton\n",
        encoding="utf-8",
    )

    with sqlite3.connect(source_database) as connection:
        connection.execute(
            "CREATE TABLE bootstrap_marker (value TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO bootstrap_marker (value) VALUES (?)",
            ("database copied",),
        )

    user_data_paths = UserDataPaths.from_root(tmp_path / "user-data")

    result = bootstrap_user_configuration(
        source_settings_path=source_settings,
        source_company_config_path=source_company_config,
        source_scoring_config_path=source_scoring_config,
        source_profiles_path=source_profiles,
        source_database_path=source_database,
        user_data_paths=user_data_paths,
    )

    assert result.database_result is not None
    assert result.database_result.copied is True
    assert len(result.all_results) == 5
    assert len(result.copied_files) == 5
    assert result.preserved_files == ()

    with sqlite3.connect(
        user_data_paths.data / "job_radar.sqlite3"
    ) as connection:
        marker_value = connection.execute(
            "SELECT value FROM bootstrap_marker"
        ).fetchone()[0]

    assert marker_value == "database copied"


def test_bootstrap_user_configuration_preserves_existing_database(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    source_settings = source_root / "config" / "settings.yaml"
    source_company_config = source_root / "config" / "target-companies.yaml"
    source_scoring_config = source_root / "config" / "scoring.yaml"
    source_profiles = source_root / "profiles"
    source_profile = source_profiles / "clayton" / "profile.yaml"
    source_database = source_root / "data" / "job_radar.sqlite3"
    source_settings.parent.mkdir(parents=True)
    source_profile.parent.mkdir(parents=True)
    source_database.parent.mkdir(parents=True)
    source_settings.write_text("source settings\n", encoding="utf-8")
    source_company_config.write_text("companies: []\n", encoding="utf-8")
    source_scoring_config.write_text(
        "positive_keywords: {}\n",
        encoding="utf-8",
    )
    source_profile.write_text("source profile\n", encoding="utf-8")

    with sqlite3.connect(source_database) as connection:
        connection.execute(
            "CREATE TABLE source_marker (value TEXT NOT NULL)"
        )

    user_data_paths = UserDataPaths.from_root(tmp_path / "user-data")
    destination_database = user_data_paths.data / "job_radar.sqlite3"
    destination_database.parent.mkdir(parents=True)

    with sqlite3.connect(destination_database) as connection:
        connection.execute(
            "CREATE TABLE destination_marker (value TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO destination_marker (value) VALUES (?)",
            ("existing database",),
        )

    result = bootstrap_user_configuration(
        source_settings_path=source_settings,
        source_company_config_path=source_company_config,
        source_scoring_config_path=source_scoring_config,
        source_profiles_path=source_profiles,
        source_database_path=source_database,
        user_data_paths=user_data_paths,
    )

    assert result.database_result is not None
    assert result.database_result.copied is False
    assert result.database_result in result.preserved_files

    with sqlite3.connect(destination_database) as connection:
        marker_value = connection.execute(
            "SELECT value FROM destination_marker"
        ).fetchone()[0]
        source_table = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            AND name = 'source_marker'
            """
        ).fetchone()

    assert marker_value == "existing database"
    assert source_table is None


def test_copy_bootstrap_database_creates_valid_sqlite_backup(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source" / "job_radar.sqlite3"
    destination = tmp_path / "destination" / "job_radar.sqlite3"
    source.parent.mkdir(parents=True)

    with sqlite3.connect(source) as connection:
        connection.execute(
            """
            CREATE TABLE migration_marker (
                value TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO migration_marker (value)
            VALUES (?)
            """,
            ("copied safely",),
        )

    result = copy_bootstrap_database(source, destination)

    assert result.source == source.resolve()
    assert result.destination == destination.resolve()
    assert result.copied is True

    with sqlite3.connect(destination) as connection:
        marker_value = connection.execute(
            "SELECT value FROM migration_marker"
        ).fetchone()[0]

    assert marker_value == "copied safely"


def test_copy_bootstrap_database_preserves_existing_destination(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.sqlite3"
    destination = tmp_path / "destination.sqlite3"

    with sqlite3.connect(source) as connection:
        connection.execute(
            "CREATE TABLE source_marker (value TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO source_marker (value) VALUES (?)",
            ("source",),
        )

    with sqlite3.connect(destination) as connection:
        connection.execute(
            "CREATE TABLE destination_marker (value TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO destination_marker (value) VALUES (?)",
            ("existing",),
        )

    result = copy_bootstrap_database(source, destination)

    assert result.copied is False

    with sqlite3.connect(destination) as connection:
        marker_value = connection.execute(
            "SELECT value FROM destination_marker"
        ).fetchone()[0]
        source_table = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            AND name = 'source_marker'
            """
        ).fetchone()

    assert marker_value == "existing"
    assert source_table is None


def test_copy_bootstrap_database_rejects_missing_source(
    tmp_path: Path,
) -> None:
    source = tmp_path / "missing.sqlite3"
    destination = tmp_path / "destination.sqlite3"

    with pytest.raises(
        UserDataBootstrapError,
        match="Bootstrap source database does not exist",
    ):
        copy_bootstrap_database(source, destination)


def test_copy_bootstrap_database_rejects_directory_destination(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.sqlite3"
    destination = tmp_path / "destination"

    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE marker (value TEXT)")

    destination.mkdir()

    with pytest.raises(
        UserDataBootstrapError,
        match="Bootstrap database destination is not a file",
    ):
        copy_bootstrap_database(source, destination)


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


def test_bootstrap_user_configuration_allows_missing_profiles_directory(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    source_settings = source_root / "config" / "settings.yaml"
    source_company_config = source_root / "config" / "target-companies.yaml"
    source_scoring_config = source_root / "config" / "scoring.yaml"
    missing_profiles = source_root / "profiles"
    source_settings.parent.mkdir(parents=True)
    source_settings.write_text(
        "database_path: data/job_radar.sqlite3\n",
        encoding="utf-8",
    )
    source_company_config.write_text(
        "companies: []\n",
        encoding="utf-8",
    )
    source_scoring_config.write_text(
        "positive_keywords: {}\n",
        encoding="utf-8",
    )
    user_data_paths = UserDataPaths.from_root(tmp_path / "user-data")

    result = bootstrap_user_configuration(
        source_settings_path=source_settings,
        source_company_config_path=source_company_config,
        source_scoring_config_path=source_scoring_config,
        source_profiles_path=missing_profiles,
        user_data_paths=user_data_paths,
    )

    assert result.profile_results == ()
    assert len(result.all_results) == 3
    assert len(result.copied_files) == 3
    assert result.preserved_files == ()
    assert user_data_paths.profiles.is_dir()


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
