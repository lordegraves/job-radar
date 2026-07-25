"""Verify repeatable dependency-license reports and distribution notices."""

import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_dependency_license_audit_is_current() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "audit_dependency_licenses.py"),
            "--check",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_dependency_report_contains_required_compliance_fields() -> None:
    report = json.loads(
        (PROJECT_ROOT / "dependency-license-report.json").read_text(
            encoding="utf-8"
        )
    )
    required = {
        "name",
        "version",
        "direct_or_transitive",
        "where_used",
        "license_spdx",
        "authoritative_license_source",
        "bundled_into",
        "required_attribution_or_notices",
        "source_offer_requirement",
        "gpl_3_only_compatibility",
        "status",
        "notes",
    }

    assert report["summary"]["blocker_count"] == 0
    assert report["summary"]["package_count"] >= 31
    audited_items = (
        report["packages"]
        + report["reference_data"]
        + report["bundled_platform_components"]
    )
    assert all(required <= item.keys() for item in audited_items)
    assert all(
        package["gpl_3_only_compatibility"] == "compatible"
        for package in report["packages"]
    )


def test_third_party_notices_cover_dependencies_and_reference_data() -> None:
    notices = (PROJECT_ROOT / "THIRD_PARTY_LICENSES.md").read_text(
        encoding="utf-8"
    )

    assert "proxy_tools" in notices
    assert "O*NET 30.3 Database" in notices
    assert "U.S. Census Bureau Gazetteer Files" in notices
    assert "Microsoft Edge WebView2" in notices
    assert "OpenSSL runtime libraries" in notices
    assert "SQLite" in notices
    assert (PROJECT_ROOT / "third_party" / "proxy_tools_LICENSE.txt").is_file()
