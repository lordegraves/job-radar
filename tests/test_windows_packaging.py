"""Verify the reproducible Windows executable recipe stays safe and complete."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_windows_spec_uses_desktop_entry_and_packaged_resources() -> None:
    spec_text = (
        PROJECT_ROOT / "packaging" / "windows" / "junior.spec"
    ).read_text(encoding="utf-8")

    assert '"desktop_launcher.py"' in spec_text
    assert 'collect_data_files("job_radar")' in spec_text
    assert 'collect_all("webview")' in spec_text
    assert 'collect_submodules("keyring.backends")' in spec_text
    assert 'name="Junior"' in spec_text
    assert "console=False" in spec_text
    assert '"junior.ico"' in spec_text
    assert '(str(project_root / "LICENSE"), ".")' in spec_text


def test_windows_build_script_uses_only_repository_build_outputs() -> None:
    script_text = (
        PROJECT_ROOT / "scripts" / "build_windows.ps1"
    ).read_text(encoding="utf-8")

    assert ".venv\\Scripts\\python.exe" in script_text
    assert "packaging\\windows\\junior.spec" in script_text
    assert "build\\pyinstaller" in script_text
    assert "artifacts\\windows" in script_text
    assert "Junior\\Junior.exe" in script_text
    assert "JOB_RADAR_DATA_DIR" not in script_text
