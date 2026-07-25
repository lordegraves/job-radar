"""Verify clean-package checks exclude source and protect disposable user data."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read(script_name: str) -> str:
    return (PROJECT_ROOT / "scripts" / script_name).read_text(encoding="utf-8")


def test_windows_clean_package_uses_installed_executable_and_isolated_data() -> None:
    script = _read("validate_clean_windows_package.ps1")

    assert "Junior.exe" in script
    assert 'Join-Path $installRoot "LICENSE"' in script
    assert "--no-browser" in script
    assert "JOB_RADAR_DATA_DIR = $dataRoot" in script
    assert "Welcome to junior" in script
    assert "job_radar.sqlite3" in script
    assert "unins000.exe" in script
    assert "clean-package-sentinel.txt" in script
    assert "Remove-Item -LiteralPath $validationRoot" in script
    assert ".venv" not in script


def test_linux_clean_package_requires_python_free_release_only_image() -> None:
    script = _read("validate_clean_linux_package.sh")
    wrapper = _read("validate_clean_packages.ps1")

    assert "command -v python" in script
    assert "Junior-linux-x86_64.tar.gz" in script
    assert '"$installed_root/junior" --help' in script
    assert "clean-package-sentinel.txt" in script
    assert "Junior/uninstall.sh" in script
    assert "debian:bookworm-slim" in wrapper
    assert "docker run --rm" in wrapper
    assert "scripts\\build_windows_installer.ps1" in wrapper
    assert "scripts\\build_linux_tarball.ps1" in wrapper
    assert "C:\\dev\\job-radar" not in script
