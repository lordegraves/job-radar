import shutil
import subprocess
import sys
import zipfile
from importlib.metadata import version
from pathlib import Path

from job_radar import __version__


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_package_exposes_installed_version() -> None:
    assert __version__ == version("job-radar")


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

    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            ".",
            "--no-deps",
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
            "job_radar/cli.py",
            "job_radar/collectors/__init__.py",
            "job_radar/tracker/__init__.py",
            "job_radar/web_routes/__init__.py",
            "job_radar/templates/base.html",
        }
        assert required_files <= archive_names

        entry_points_path = next(
            name
            for name in archive_names
            if name.endswith(".dist-info/entry_points.txt")
        )
        entry_points = wheel_archive.read(entry_points_path).decode("utf-8")

    assert "job-radar = job_radar.cli:main" in entry_points
    assert "job-radar-web = job_radar.web_app:main" in entry_points

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