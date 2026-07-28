"""Verify scan diagnostics are useful and limited to explicitly safe fields."""

import json
from pathlib import Path

from job_radar.scan_diagnostic_log import (
    DIAGNOSTIC_LOG_NAME,
    LAST_SCAN_LOG_NAME,
    record_scan_diagnostic,
    start_scan_diagnostics,
)


def test_last_scan_log_is_replaced_and_private_fields_are_dropped(
    tmp_path: Path,
) -> None:
    start_scan_diagnostics(
        tmp_path,
        scan_run_id=7,
        trigger="manual",
        companies_requested=2,
    )
    record_scan_diagnostic(
        tmp_path,
        event="company_collection_completed",
        scan_run_id=7,
        company_number=1,
        company_id="example-employer",
        source_type="eightfold",
        jobs_found=12,
        failure_reason="The public source temporarily limited requests.",
        company_name="Private Employer",
        job_title="Private Job",
        source_url="https://example.invalid/private",
        profile_name="Private Profile",
    )

    lines = (tmp_path / LAST_SCAN_LOG_NAME).read_text(
        encoding="utf-8"
    ).splitlines()
    payload = json.loads(lines[-1])
    assert payload["schema_version"] == 1
    assert payload["application_version"]
    assert payload["application_build"]
    assert payload["subsystem"] == "scan"
    assert payload["severity"] == "info"
    assert payload["source_type"] == "eightfold"
    assert payload["company_id"] == "example-employer"
    assert payload["jobs_found"] == 12
    assert payload["failure_reason"] == (
        "The public source temporarily limited requests."
    )
    assert "company_name" not in payload
    assert "job_title" not in payload
    assert "source_url" not in payload
    assert "profile_name" not in payload

    start_scan_diagnostics(
        tmp_path,
        scan_run_id=8,
        trigger="scheduled",
        companies_requested=1,
    )
    replacement = (tmp_path / LAST_SCAN_LOG_NAME).read_text(encoding="utf-8")
    history = (tmp_path / DIAGNOSTIC_LOG_NAME).read_text(encoding="utf-8")
    assert '"scan_run_id": 7' not in replacement
    assert '"scan_run_id": 8' in replacement
    assert '"scan_run_id": 7' in history
    assert '"scan_run_id": 8' in history
