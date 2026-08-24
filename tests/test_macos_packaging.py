"""Protect Junior's native macOS application and DMG recipe."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_macos_spec_uses_shared_desktop_entry_resources_and_bundle() -> None:
    text = (PROJECT_ROOT / "packaging/macos/junior.spec").read_text()

    assert '"desktop_launcher.py"' in text
    assert 'collect_data_files("job_radar")' in text
    assert 'collect_all("webview")' in text
    assert 'collect_submodules("keyring.backends")' in text
    assert 'name="Junior.app"' in text
    assert 'icon=str(icon_path)' in text
    assert 'bundle_identifier="com.claytongraves.junior"' in text
    assert '"CFBundleShortVersionString": "0.2.0"' in text
    assert '"CFBundleVersion": "1.25"' in text
    assert '(str(project_root / "LICENSE"), ".")' in text
    assert '(str(project_root / "PRIVACY.md"), ".")' in text
    assert '(str(project_root / "SECURITY.md"), ".")' in text


def test_macos_build_creates_icon_app_and_drag_install_dmg() -> None:
    text = (PROJECT_ROOT / "scripts/build_macos_dmg.sh").read_text()

    assert '"$(uname -s)" != "Darwin"' in text
    assert ".venv/bin/python" in text
    assert "iconutil -c icns" in text
    assert "packaging/macos/junior.spec" in text
    assert "codesign --verify --deep --strict" in text
    assert "ln -s /Applications" in text
    assert "hdiutil create" in text
    assert "RC6-build-1.25-macos-$architecture.dmg" in text


def test_macos_clean_validation_uses_isolated_user_data() -> None:
    text = (
        PROJECT_ROOT / "scripts/validate_clean_macos_package.sh"
    ).read_text()

    assert "JOB_RADAR_DATA_DIR" in text
    assert "junior-macos-data" in text
    assert "--no-browser --port 5051" in text
    assert "http://127.0.0.1:5051/" in text
    assert "RC6 Build 1.25" in text
    assert "job_radar.sqlite3" in text
