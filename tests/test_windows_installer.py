"""Verify the Windows installer preserves user data and expected shortcuts."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_inno_installer_is_per_user_and_preserves_user_data() -> None:
    script_text = (
        PROJECT_ROOT / "packaging" / "windows" / "junior-installer.iss"
    ).read_text(encoding="utf-8")

    assert "DefaultDirName={localappdata}\\Programs\\Junior" in script_text
    assert "PrivilegesRequired=lowest" in script_text
    assert "SetupIconFile=..\\..\\job_radar\\static\\junior.ico" in script_text
    assert 'Name: "{group}\\Junior"' in script_text
    assert 'Name: "{autodesktop}\\Junior"' in script_text
    assert "Flags: unchecked" in script_text
    assert "LocalAppData\\JobRadar" in script_text
    assert "[UninstallDelete]" not in script_text
    assert "{localappdata}\\JobRadar" not in script_text


def test_installer_build_script_requires_verified_bundle_first() -> None:
    script_text = (
        PROJECT_ROOT / "scripts" / "build_windows_installer.ps1"
    ).read_text(encoding="utf-8")

    assert "scripts\\build_windows.ps1" in script_text
    assert "packaging\\windows\\junior-installer.iss" in script_text
    assert "ISCC.exe" in script_text
    assert "artifacts\\installer\\Junior-Setup-0.2.0.exe" in script_text
    validation_text = (
        PROJECT_ROOT / "scripts" / "validate_windows_upgrade.ps1"
    ).read_text(encoding="utf-8")
    assert 'Join-Path $installRoot "LICENSE"' in validation_text


def test_installer_receives_license_from_complete_windows_bundle() -> None:
    installer_text = (
        PROJECT_ROOT / "packaging" / "windows" / "junior-installer.iss"
    ).read_text(encoding="utf-8")
    spec_text = (
        PROJECT_ROOT / "packaging" / "windows" / "junior.spec"
    ).read_text(encoding="utf-8")

    assert 'artifacts\\windows\\Junior\\*"; DestDir: "{app}"' in installer_text
    assert "recursesubdirs createallsubdirs" in installer_text
    assert 'Source: "..\\..\\LICENSE"; DestDir: "{app}"' in installer_text
    assert '(str(project_root / "LICENSE"), ".")' in spec_text


def test_windows_bundle_embeds_product_version_details() -> None:
    spec_text = (
        PROJECT_ROOT / "packaging" / "windows" / "junior.spec"
    ).read_text(encoding="utf-8")
    version_text = (
        PROJECT_ROOT / "packaging" / "windows" / "junior-version-info.txt"
    ).read_text(encoding="utf-8")

    assert "junior-version-info.txt" in spec_text
    assert 'StringStruct("ProductName", "junior")' in version_text
    assert 'StringStruct("ProductVersion", "0.2.0")' in version_text
    assert 'StringStruct("FileVersion", "0.2.0")' in version_text
