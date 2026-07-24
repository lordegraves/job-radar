"""Verify Windows upgrade validation covers every user-owned data category."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_windows_upgrade_validation_covers_preservation_boundaries() -> None:
    script_text = (
        PROJECT_ROOT / "scripts" / "validate_windows_upgrade.ps1"
    ).read_text(encoding="utf-8")

    required_sentinels = (
        "settings.yaml",
        "target-companies.yaml",
        "profile.yaml",
        "resume.md",
        "job_radar.sqlite3",
        "latest.html",
        "before-upgrade.zip",
        "schedule.json",
        "credential-reference.txt",
    )
    for sentinel in required_sentinels:
        assert sentinel in script_text

    assert script_text.count("Invoke-Setup") == 3
    assert 'Stage "Repair or upgrade"' in script_text
    assert 'Stage "Uninstall"' in script_text
    assert "Get-FileHash" in script_text
    assert "Remove-Item -LiteralPath $validationRoot" in script_text
