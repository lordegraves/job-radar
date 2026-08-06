"""Verify that release packages are complete, private-data-free, and runnable.

These tests build temporary wheel and source archives, inspect their contents,
install outside the repository, exercise CLI and desktop entry points, bootstrap
synthetic user data, and render the installed web application.
"""

import os
import shutil
import subprocess
import sys
import tarfile
import tomllib
import zipfile
from importlib.metadata import version
from pathlib import Path

from job_radar import __build__, __display_version__, __version__
from job_radar.build_info import BUILD_SLUG


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _copy_license_material(source_directory: Path) -> None:
    shutil.copy2(PROJECT_ROOT / "LICENSE", source_directory)
    shutil.copy2(PROJECT_ROOT / "PRIVACY.md", source_directory)
    shutil.copy2(PROJECT_ROOT / "SECURITY.md", source_directory)
    shutil.copy2(PROJECT_ROOT / "THIRD_PARTY_LICENSES.md", source_directory)
    shutil.copy2(PROJECT_ROOT / "dependency-license-report.json", source_directory)
    shutil.copytree(PROJECT_ROOT / "third_party", source_directory / "third_party")


def test_project_declares_complete_gpl_v3_only_license() -> None:
    license_text = (PROJECT_ROOT / "LICENSE").read_text(encoding="utf-8")
    project_metadata = tomllib.loads(
        (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]

    assert "GNU GENERAL PUBLIC LICENSE" in license_text
    assert "Version 3, 29 June 2007" in license_text
    assert "END OF TERMS AND CONDITIONS" in license_text
    assert project_metadata["license"] == "GPL-3.0-only"
    assert project_metadata["license-files"] == [
        "LICENSE",
        "PRIVACY.md",
        "SECURITY.md",
        "THIRD_PARTY_LICENSES.md",
        "dependency-license-report.json",
        "third_party/*.txt",
    ]


def test_package_exposes_installed_version() -> None:
    assert __version__ == version("job-radar")
    assert __build__ == "RC6 Build 1.15"
    assert __display_version__ == f"{__version__} — RC6 Build 1.15"


def test_windows_packaging_uses_the_shared_field_test_build() -> None:
    installer = (
        PROJECT_ROOT / "packaging" / "windows" / "junior-installer.iss"
    ).read_text(encoding="utf-8")
    version_info = (
        PROJECT_ROOT / "packaging" / "windows" / "junior-version-info.txt"
    ).read_text(encoding="utf-8")
    build_script = (
        PROJECT_ROOT / "scripts" / "build_windows_installer.ps1"
    ).read_text(encoding="utf-8")

    assert f'#define BuildLabel "{__build__}"' in installer
    assert f'#define BuildSlug "{BUILD_SLUG}"' in installer
    assert f'ProductVersion", "0.2.0 - {__build__}"' in version_info
    assert f"Junior-Setup-0.2.0-{BUILD_SLUG}.exe" in build_script
    assert "WizardImageFile=..\\..\\job_radar\\static\\junior_wizard.png" in installer
    assert "WizardSmallImageFile=..\\..\\job_radar\\static\\junior_icon_v2.png" in installer
    assert "function DetectSetupMode(): Integer;" in installer
    assert "SetupModeInstall" in installer
    assert "SetupModeUpdate" in installer
    assert "SetupModeRepair" in installer
    assert "procedure ApplyJuniorTheme();" in installer
    assert "WizardForm.WelcomePage.Color := $0010100F" in installer
    assert "WizardForm.PageNameLabel.Font.Color := $00F3F3F3" in installer
    assert "WizardForm.Components[Index] is TNewStaticText" in installer
    assert "WizardForm.Components[Index] is TNewCheckListBox" in installer


def test_built_wheel_contains_runtime_packages_and_entry_points(
    tmp_path: Path,
) -> None:
    source_directory = tmp_path / "source"
    wheel_directory = tmp_path / "wheelhouse"

    # Build from a temporary source copy so packaging tools cannot leave
    # build directories or generated metadata in the working repository.
    shutil.copytree(PROJECT_ROOT / "job_radar", source_directory / "job_radar")
    shutil.copy2(PROJECT_ROOT / "pyproject.toml", source_directory)
    shutil.copy2(PROJECT_ROOT / "README.md", source_directory)
    _copy_license_material(source_directory)

    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            ".",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(wheel_directory),
        ],
        cwd=source_directory,
        check=True,
        capture_output=True,
        text=True,
    )

    wheel_files = tuple(wheel_directory.glob("job_radar-*.whl"))
    assert len(wheel_files) == 1

    with zipfile.ZipFile(wheel_files[0]) as wheel_archive:
        archive_names = set(wheel_archive.namelist())

        required_files = {
            "job_radar/__init__.py",
            "job_radar/__main__.py",
            "job_radar/bootstrap_defaults/settings.yaml",
            "job_radar/bootstrap_defaults/target-companies.yaml",
            "job_radar/bootstrap_defaults/scoring.yaml",
            "job_radar/cli.py",
            "job_radar/collectors/__init__.py",
            "job_radar/desktop_launcher.py",
            "job_radar/static/junior_icon_v2.png",
            "job_radar/static/junior_logo.png",
            "job_radar/tracker/__init__.py",
            "job_radar/web_routes/__init__.py",
            "job_radar/templates/administration/index.html",
            "job_radar/templates/administration/employer_detail.html",
            "job_radar/templates/administration/recommendations.html",
            "job_radar/templates/administration/recovery.html",
            "job_radar/templates/administration/employer_form.html",
            "job_radar/templates/administration/employer_review_detail.html",
            "job_radar/templates/administration/employer_reviews.html",
            "job_radar/templates/administration/employers.html",
            "job_radar/templates/administration/unlock.html",
            "job_radar/templates/base.html",
            "job_radar/templates/company_recommendations.html",
            "job_radar/templates/setup_welcome.html",
            "job_radar/templates/setup_resume.html",
            "job_radar/templates/setup_companies.html",
            "job_radar/templates/setup_review.html",
            "job_radar/templates/shutdown.html",
            "job_radar/templates/role_discovery.html",
            "job_radar/templates/mutation_error.html",
        }
        assert required_files <= archive_names

        entry_points_path = next(
            name
            for name in archive_names
            if name.endswith(".dist-info/entry_points.txt")
        )
        entry_points = wheel_archive.read(entry_points_path).decode("utf-8")
        metadata_path = next(
            name for name in archive_names if name.endswith(".dist-info/METADATA")
        )
        metadata = wheel_archive.read(metadata_path).decode("utf-8")
        license_path = next(
            name
            for name in archive_names
            if name.endswith(".dist-info/licenses/LICENSE")
        )
        packaged_license = wheel_archive.read(license_path).decode("utf-8")
        assert any(
            name.endswith(".dist-info/licenses/THIRD_PARTY_LICENSES.md")
            for name in archive_names
        )
        assert any(
            name.endswith(".dist-info/licenses/PRIVACY.md")
            for name in archive_names
        )
        assert any(
            name.endswith(".dist-info/licenses/SECURITY.md")
            for name in archive_names
        )
        assert any(
            name.endswith(".dist-info/licenses/dependency-license-report.json")
            for name in archive_names
        )
        assert any(
            name.endswith(
                ".dist-info/licenses/third_party/proxy_tools_LICENSE.txt"
            )
            for name in archive_names
        )

    assert "junior = job_radar.cli:main" in entry_points
    assert "junior-web = job_radar.web_app:main" in entry_points
    assert "job-radar = job_radar.cli:main" in entry_points
    assert (
        "junior-desktop = job_radar.desktop_launcher:main"
        in entry_points
    )
    assert "job-radar-desktop = job_radar.desktop_launcher:main" in entry_points
    assert "License-Expression: GPL-3.0-only" in metadata
    assert "GNU GENERAL PUBLIC LICENSE" in packaged_license
    assert "Version 3, 29 June 2007" in packaged_license

    private_runtime_prefixes = (
        "config/",
        "data/",
        "logs/",
        "profiles/",
        "reports/",
    )
    assert not any(
        archive_name.startswith(private_runtime_prefixes)
        for archive_name in archive_names
    )


def test_built_source_distribution_excludes_private_runtime_data(
    tmp_path: Path,
) -> None:
    source_directory = tmp_path / "source"
    distribution_directory = tmp_path / "dist"

    shutil.copytree(PROJECT_ROOT / "job_radar", source_directory / "job_radar")
    shutil.copytree(PROJECT_ROOT / "tests", source_directory / "tests")
    shutil.copy2(PROJECT_ROOT / "pyproject.toml", source_directory)
    shutil.copy2(PROJECT_ROOT / "README.md", source_directory)
    _copy_license_material(source_directory)

    synthetic_private_files = {
        "config/local-private-settings.yaml": "smtp_password: private-value\n",
        "data/private.sqlite3": "private database sentinel\n",
        "logs/private.log": "private log sentinel\n",
        "profiles/private/profile.yaml": "candidate: private\n",
        "profiles/private/resume.md": "private resume sentinel\n",
        "reports/private-report.html": "private report sentinel\n",
        "job-radar-foundation-6-private-audit.txt": "private audit sentinel\n",
    }

    for relative_path, content in synthetic_private_files.items():
        private_file = source_directory / relative_path
        private_file.parent.mkdir(parents=True, exist_ok=True)
        private_file.write_text(content, encoding="utf-8")

    subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            "--sdist",
            "--no-isolation",
            "--outdir",
            str(distribution_directory),
        ],
        cwd=source_directory,
        check=True,
        capture_output=True,
        text=True,
    )

    source_distributions = tuple(
        distribution_directory.glob("job_radar-*.tar.gz")
    )
    assert len(source_distributions) == 1

    with tarfile.open(source_distributions[0], mode="r:gz") as archive:
        archive_names = {
            member.name.replace("\\", "/")
            for member in archive.getmembers()
        }

    normalized_names = {
        archive_name.split("/", maxsplit=1)[1]
        for archive_name in archive_names
        if "/" in archive_name
    }

    required_files = {
        "LICENSE",
        "PRIVACY.md",
        "SECURITY.md",
        "THIRD_PARTY_LICENSES.md",
        "dependency-license-report.json",
        "third_party/proxy_tools_LICENSE.txt",
        "README.md",
        "pyproject.toml",
        "job_radar/__init__.py",
        "job_radar/bootstrap_defaults/settings.yaml",
        "job_radar/bootstrap_defaults/target-companies.yaml",
        "job_radar/bootstrap_defaults/scoring.yaml",
        "job_radar/cli.py",
        "job_radar/templates/administration/index.html",
        "job_radar/templates/administration/employer_detail.html",
        "job_radar/templates/administration/recommendations.html",
        "job_radar/templates/administration/recovery.html",
        "job_radar/templates/administration/employer_form.html",
        "job_radar/templates/administration/employer_review_detail.html",
        "job_radar/templates/administration/employer_reviews.html",
        "job_radar/templates/administration/employers.html",
        "job_radar/templates/administration/unlock.html",
        "job_radar/templates/base.html",
        "job_radar/templates/company_recommendations.html",
        "job_radar/templates/setup_welcome.html",
        "job_radar/templates/setup_resume.html",
        "job_radar/templates/setup_companies.html",
        "job_radar/templates/setup_review.html",
        "job_radar/templates/shutdown.html",
        "job_radar/templates/role_discovery.html",
        "job_radar/templates/mutation_error.html",
        "tests/test_packaging.py",
    }
    assert required_files <= normalized_names

    forbidden_prefixes = (
        "config/",
        "data/",
        "logs/",
        "profiles/",
        "reports/",
    )
    assert not any(
        archive_name.startswith(forbidden_prefixes)
        for archive_name in normalized_names
    )
    assert not any(
        "job-radar-foundation-6-" in archive_name
        for archive_name in normalized_names
    )
    assert not any(
        archive_name.endswith(
            (
                ".sqlite3",
                ".db",
                ".log",
                ".env",
                ".xlsx",
                ".xls",
                ".pdf",
                ".docx",
            )
        )
        for archive_name in normalized_names
    )


def test_installed_wheel_runs_outside_source_checkout(
    tmp_path: Path,
) -> None:
    source_directory = tmp_path / "source"
    wheel_directory = tmp_path / "wheelhouse"
    install_directory = tmp_path / "installed"
    execution_directory = tmp_path / "outside-source"

    # Build and install entirely under pytest temporary storage so this test
    # exercises the distributable package without modifying the repository.
    shutil.copytree(PROJECT_ROOT / "job_radar", source_directory / "job_radar")
    shutil.copy2(PROJECT_ROOT / "pyproject.toml", source_directory)
    shutil.copy2(PROJECT_ROOT / "README.md", source_directory)
    _copy_license_material(source_directory)
    execution_directory.mkdir()

    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            ".",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(wheel_directory),
        ],
        cwd=source_directory,
        check=True,
        capture_output=True,
        text=True,
    )

    wheel_files = tuple(wheel_directory.glob("job_radar-*.whl"))
    assert len(wheel_files) == 1

    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--target",
            str(install_directory),
            str(wheel_files[0]),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(install_directory)
    environment["JOB_RADAR_TEST_INSTALL"] = str(install_directory)

    installed_import = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import os; "
                "from importlib.resources import files; "
                "from pathlib import Path; "
                "import job_radar; "
                "install_root = "
                "Path(os.environ['JOB_RADAR_TEST_INSTALL']).resolve(); "
                "package_file = Path(job_radar.__file__).resolve(); "
                "assert install_root in package_file.parents, package_file; "
                "assert files('job_radar').joinpath("
                "'templates/base.html').is_file(); "
                "print(job_radar.__version__)"
            ),
        ],
        cwd=execution_directory,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    assert installed_import.stdout.strip() == __version__

    cli_version = subprocess.run(
        [
            sys.executable,
            "-m",
            "job_radar",
            "--version",
        ],
        cwd=execution_directory,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    assert cli_version.stdout.strip() == f"junior {__version__}"

    web_help = subprocess.run(
        [
            sys.executable,
            "-m",
            "job_radar.web_app",
            "--help",
        ],
        cwd=execution_directory,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "Local junior web interface" in web_help.stdout
    assert "--settings" in web_help.stdout
    assert "--host" in web_help.stdout
    assert "--port" in web_help.stdout

    desktop_help = subprocess.run(
        [
            sys.executable,
            "-m",
            "job_radar.desktop_launcher",
            "--help",
        ],
        cwd=execution_directory,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "Launch the junior desktop interface" in desktop_help.stdout
    assert "--host" in desktop_help.stdout
    assert "--port" in desktop_help.stdout
    assert "--no-browser" in desktop_help.stdout

    user_data_directory = tmp_path / "bootstrapped-user-data"

    bootstrap_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "job_radar",
            "bootstrap-user-data",
            "--destination",
            str(user_data_directory),
        ],
        cwd=execution_directory,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "User data bootstrap complete" in bootstrap_result.stdout
    assert "Files copied: 3" in bootstrap_result.stdout
    assert "Existing files preserved: 0" in bootstrap_result.stdout

    settings_path = user_data_directory / "config" / "settings.yaml"
    company_config_path = (
        user_data_directory / "config" / "target-companies.yaml"
    )
    scoring_config_path = user_data_directory / "config" / "scoring.yaml"

    assert settings_path.is_file()
    assert company_config_path.is_file()
    assert scoring_config_path.is_file()
    assert tuple((user_data_directory / "profiles").iterdir()) == ()
    assert tuple((user_data_directory / "data").iterdir()) == ()

    settings_text = settings_path.read_text(encoding="utf-8")
    company_config_text = company_config_path.read_text(encoding="utf-8")

    assert "smtp_password:" not in settings_text
    assert "report_policy: keep_last_n" in settings_text
    assert "report_count: 10" in settings_text
    assert "companies: []" in company_config_text
    assert "example_ai" not in company_config_text
    assert "examplecloud" not in company_config_text


def test_installed_wheel_renders_home_page_with_user_owned_data(
    tmp_path: Path,
) -> None:
    source_directory = tmp_path / "source"
    wheel_directory = tmp_path / "wheelhouse"
    install_directory = tmp_path / "installed"
    execution_directory = tmp_path / "outside-source"
    user_data_directory = tmp_path / "user-data"
    settings_file = user_data_directory / "config" / "settings.yaml"
    database_file = user_data_directory / "data" / "job_radar.sqlite3"
    reports_directory = user_data_directory / "reports"
    logs_directory = user_data_directory / "logs"

    shutil.copytree(PROJECT_ROOT / "job_radar", source_directory / "job_radar")
    shutil.copy2(PROJECT_ROOT / "pyproject.toml", source_directory)
    shutil.copy2(PROJECT_ROOT / "README.md", source_directory)
    shutil.copy2(PROJECT_ROOT / "LICENSE", source_directory)

    execution_directory.mkdir()
    settings_file.parent.mkdir(parents=True)
    database_file.parent.mkdir(parents=True)
    reports_directory.mkdir(parents=True)
    logs_directory.mkdir(parents=True)

    settings_file.write_text(
        f"""
database_path: {database_file}
reports_path: {reports_directory}
logs_path: {logs_directory}
""",
        encoding="utf-8",
    )

    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            ".",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(wheel_directory),
        ],
        cwd=source_directory,
        check=True,
        capture_output=True,
        text=True,
    )

    wheel_files = tuple(wheel_directory.glob("job_radar-*.whl"))
    assert len(wheel_files) == 1

    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--target",
            str(install_directory),
            str(wheel_files[0]),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(install_directory)
    environment["JOB_RADAR_TEST_INSTALL"] = str(install_directory)
    environment["JOB_RADAR_TEST_SETTINGS"] = str(settings_file)
    environment["JOB_RADAR_TEST_DATABASE"] = str(database_file)

    rendered_page = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import os; "
                "from pathlib import Path; "
                "import job_radar.web_app as web_app; "
                "install_root = "
                "Path(os.environ['JOB_RADAR_TEST_INSTALL']).resolve(); "
                "module_file = Path(web_app.__file__).resolve(); "
                "assert install_root in module_file.parents, module_file; "
                "settings_path = os.environ['JOB_RADAR_TEST_SETTINGS']; "
                "database_path = "
                "Path(os.environ['JOB_RADAR_TEST_DATABASE']); "
                "app = web_app.create_app(settings_path=settings_path); "
                    "client = app.test_client(); "
                    "response = client.get('/'); "
                    "assert response.status_code == 302; "
                    "assert response.headers['Location'] == '/setup'; "
                    "setup_response = client.get('/setup'); "
                    "assert setup_response.status_code == 200; "
                    "assert 'Welcome to junior' in "
                    "setup_response.get_data(as_text=True); "
                "unlock_response = client.get('/administration/unlock'); "
                "assert unlock_response.status_code == 200; "
                "assert 'Unlock Administration' in "
                "unlock_response.get_data(as_text=True); "
                "assert database_path.is_file(); "
                "print('installed web render passed')"
            ),
        ],
        cwd=execution_directory,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )

    assert rendered_page.stdout.strip() == "installed web render passed"
