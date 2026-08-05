"""Verify the automated release gate covers the complete protected lifecycle."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_release_gate_runs_full_validation_and_installer_lifecycle() -> None:
    script = (
        PROJECT_ROOT / "scripts" / "validate_release.ps1"
    ).read_text(encoding="utf-8")

    assert r".venv\Scripts\python.exe" in script
    assert "-m pytest -q --basetemp $pytestBaseTemp tests" in script
    assert "-m ruff check ." in script
    assert "git diff --check" in script
    assert "scripts\\build_windows_installer.ps1" in script
    assert "scripts\\validate_windows_upgrade.ps1" in script
    assert "-InstallerPath $resolvedInstaller" in script
    assert "Junior automated release validation passed." in script


def test_release_gate_does_not_reference_live_user_data() -> None:
    script = (
        PROJECT_ROOT / "scripts" / "validate_release.ps1"
    ).read_text(encoding="utf-8")

    assert "LOCALAPPDATA" not in script
    assert "JOB_RADAR_DATA_DIR" not in script
    assert "config\\settings.yaml" not in script
