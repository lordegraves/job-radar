"""Verify log access stays bounded to sanitized Junior-owned files."""

import json
from pathlib import Path

import pytest

from job_radar.application_info_service import ApplicationInfo
from job_radar.company_discovery_log import record_company_discovery_event
from job_radar.decision_event_log import record_decision_event
from job_radar.diagnostic_log_service import (
    MAX_LOG_VIEW_BYTES,
    DiagnosticLogError,
    build_diagnostic_log_download,
    build_support_summary,
    diagnostic_download_name,
    list_diagnostic_logs,
    read_diagnostic_log,
)
from job_radar.diagnostic_service import DiagnosticsView, HealthCard
from job_radar.email_event_log import record_email_event


def test_lists_only_recognized_junior_logs(tmp_path: Path) -> None:
    (tmp_path / "startup-errors.log").write_text("safe", encoding="utf-8")
    (tmp_path / "junior-actions.log").write_text(
        '{"event":"job_decision","status":"success"}',
        encoding="utf-8",
    )
    (tmp_path / "junior-last-scan.log").write_text(
        '{"event":"scan_completed"}',
        encoding="utf-8",
    )
    (tmp_path / "junior-update.log").write_text(
        '{"event":"update_installer_finished","status":"success",'
        '"detail":"Installer exit code 0."}',
        encoding="utf-8",
    )
    record_email_event(
        tmp_path,
        event="email_connection_test",
        outcome="successful",
        provider="gmail",
        reason_code="connected",
    )
    (tmp_path / "junior-company-discovery.log.previous").write_text(
        '{"event":"company_discovery","outcome":"not_found"}',
        encoding="utf-8",
    )
    record_company_discovery_event(
        tmp_path,
        "candidate_test",
        {
            "candidate_host": "careers.example.test",
            "source_type": "talentbrew",
            "outcome": "verified",
            "job_count": 3,
            "unsafe_url": "https://private.example.test/query",
        },
    )
    (tmp_path / "junior-20260723T120000000000Z.log").write_text(
        "safe dated",
        encoding="utf-8",
    )
    (tmp_path / "personal.log").write_text("private", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("private", encoding="utf-8")

    logs = list_diagnostic_logs(tmp_path)

    assert {log.name for log in logs} == {
        "junior-actions.log",
        "junior-last-scan.log",
        "junior-company-discovery.log",
        "junior-company-discovery.log.previous",
        "junior-update.log",
        "junior-email.log",
        "startup-errors.log",
        "junior-20260723T120000000000Z.log",
    }
    titles = {log.name: log.title for log in logs}
    assert titles["junior-actions.log"] == "User action history"
    assert titles["junior-last-scan.log"] == "Latest scan activity"
    assert titles["junior-company-discovery.log"] == (
        "Company discovery activity"
    )
    assert titles["junior-company-discovery.log.previous"] == (
        "Previous company discovery activity"
    )
    assert titles["junior-update.log"] == "Update activity"
    assert titles["junior-email.log"] == "Email activity"
    assert all(log.description for log in logs)

    content = (tmp_path / "junior-company-discovery.log").read_text(
        encoding="utf-8"
    )
    assert "careers.example.test" in content
    assert "talentbrew" in content
    assert "unsafe_url" not in content

    email_content = (tmp_path / "junior-email.log").read_text(
        encoding="utf-8"
    )
    assert "email_connection_test" in email_content
    assert "gmail" in email_content
    assert "password" not in email_content
    assert "@" not in email_content

    record_email_event(
        tmp_path,
        event="email_connection_test",
        outcome="failed",
        provider="private@example.test",
        reason_code="invalid_provider",
    )
    email_content = (tmp_path / "junior-email.log").read_text(
        encoding="utf-8"
    )
    assert "private@example.test" not in email_content
    assert "not_configured" in email_content


def test_rejects_arbitrary_and_nested_log_paths(tmp_path: Path) -> None:
    (tmp_path / "personal.log").write_text("private", encoding="utf-8")

    with pytest.raises(DiagnosticLogError, match="not available"):
        read_diagnostic_log(tmp_path, "personal.log")
    with pytest.raises(DiagnosticLogError, match="not available"):
        read_diagnostic_log(tmp_path, "../startup-errors.log")


def test_download_builds_text_only_for_a_recognized_owned_log(
    tmp_path: Path,
) -> None:
    owned = tmp_path / "junior-actions.log"
    owned.write_text('{"status":"completed"}\n', encoding="utf-8")
    (tmp_path / "personal.log").write_text("private", encoding="utf-8")

    download = build_diagnostic_log_download(tmp_path, owned.name)
    assert "time-not-recorded | INFO | junior | diagnostic_event" in download
    assert "status=completed" in download
    with pytest.raises(DiagnosticLogError, match="not available"):
        build_diagnostic_log_download(tmp_path, "personal.log")


def test_large_log_view_reads_only_bounded_tail(tmp_path: Path) -> None:
    path = tmp_path / "startup-errors.log"
    path.write_text(
        "old private-looking fixture\n"
        + ("x" * MAX_LOG_VIEW_BYTES)
        + "\nnew safe entry",
        encoding="utf-8",
    )

    view = read_diagnostic_log(tmp_path, path.name)

    assert view.title == "Startup problem details"
    assert view.description
    assert view.truncated
    assert "Earlier log entries are hidden" in view.content
    assert "old private-looking fixture" not in view.content
    assert "new safe entry" in view.content


def test_json_scan_log_is_presented_as_structured_records(
    tmp_path: Path,
) -> None:
    path = tmp_path / "junior-last-scan.log"
    path.write_text(
        '{"event":"company_collection_completed","timestamp":'
        '"2026-07-27T18:14:03+00:00","company_id":"nasa_usajobs",'
        '"jobs_found":14}\n',
        encoding="utf-8",
    )

    view = read_diagnostic_log(tmp_path, path.name)
    assert (
        "2026-07-27T18:14:03+00:00 | INFO | junior | "
        "company_collection_completed"
    ) in view.developer_content
    assert "company_id=nasa_usajobs" in view.developer_content
    assert "jobs_found=14" in view.developer_content
    assert diagnostic_download_name(view).startswith("junior-last-scan-")
    assert diagnostic_download_name(view).endswith(".log")
    download = build_diagnostic_log_download(tmp_path, path.name)
    assert download == view.developer_content
    assert '{"event":' not in download


def test_update_log_is_presented_without_paths_or_raw_errors(
    tmp_path: Path,
) -> None:
    path = tmp_path / "junior-update.log"
    path.write_text(
        '{"event":"update_installer_finished","status":"success",'
        '"detail":"Installer exit code 0.","timestamp":'
        '"2026-07-28T12:00:00+00:00"}\n',
        encoding="utf-8",
    )

    view = read_diagnostic_log(tmp_path, path.name)
    assert view.title == "Update activity"
    assert (
        "2026-07-28T12:00:00+00:00 | INFO | junior | "
        "update_installer_finished"
    ) in view.developer_content
    assert 'detail="Installer exit code 0."' in view.developer_content
    assert "C:\\" not in view.developer_content


def test_support_summary_contains_only_bounded_health_facts() -> None:
    summary = build_support_summary(
        ApplicationInfo(
            version="0.2.0",
            release_channel="Development or pre-release",
            user_data_location="C:/Example/Junior",
            database_schema_version="24",
            profile_schema_version="2",
        ),
        DiagnosticsView(
            cards=(
                HealthCard(
                    title="Latest scan",
                    state="Healthy",
                    tone="success",
                    category="Scan",
                    summary="private summary must not be copied",
                    next_step="private next step must not be copied",
                ),
            )
        ),
    )

    assert "Version: 0.2.0" in summary
    assert "Latest scan: Healthy (Scan)" in summary
    assert "private summary" not in summary
    assert "private next step" not in summary


def test_decision_log_failure_never_blocks_the_user_action(
    tmp_path: Path,
) -> None:
    unusable_logs_path = tmp_path / "not-a-directory"
    unusable_logs_path.write_text("occupied", encoding="utf-8")

    written = record_decision_event(
        unusable_logs_path,
        event="job_decision",
        status="completed",
        job_radar_id="jr-example-12345678",
        source_view="saved_and_reviewed_jobs",
        target_state="passed",
    )

    assert written is False


def test_decision_log_records_developer_metadata(tmp_path: Path) -> None:
    written = record_decision_event(
        tmp_path,
        event="job_decision",
        status="completed",
        job_radar_id="jr-example-12345678",
        source_view="review_jobs",
        target_state="saved",
    )

    assert written is True
    payload = json.loads(
        (tmp_path / "junior-actions.log").read_text(encoding="utf-8")
    )
    assert payload["schema_version"] == 1
    assert payload["application_version"]
    assert payload["application_build"]
    assert payload["subsystem"] == "job_decision"
    assert payload["severity"] == "info"


def test_timestamped_troubleshooting_logs_have_clear_titles(
    tmp_path: Path,
) -> None:
    names = {
        "junior-database-20260805T120000Z.log": "Database operations",
        "junior-errors-20260805T120000Z.log": "Application errors",
        "junior-user-actions-20260805T120000Z.log": "User activity",
        "junior-scan-run-42-20260805T120000Z.log": "Scan execution trace",
        "junior-evaluation-run-42-20260805T120000Z.log": "Job evaluation trace",
    }
    for name in names:
        (tmp_path / name).write_text(
            '{"timestamp":"2026-08-05T12:00:00+00:00","event":"test"}\n',
            encoding="utf-8",
        )

    logs = list_diagnostic_logs(tmp_path)

    assert {item.name: item.title for item in logs} == names
