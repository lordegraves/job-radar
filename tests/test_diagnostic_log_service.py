"""Verify log access stays bounded to sanitized Junior-owned files."""

from pathlib import Path

import pytest

from job_radar.application_info_service import ApplicationInfo
from job_radar.diagnostic_log_service import (
    MAX_LOG_VIEW_BYTES,
    DiagnosticLogError,
    build_support_summary,
    get_diagnostic_log_download,
    list_diagnostic_logs,
    read_diagnostic_log,
)
from job_radar.diagnostic_service import DiagnosticsView, HealthCard
from job_radar.decision_event_log import record_decision_event


def test_lists_only_recognized_junior_logs(tmp_path: Path) -> None:
    (tmp_path / "startup-errors.log").write_text("safe", encoding="utf-8")
    (tmp_path / "junior-actions.log").write_text(
        '{"event":"job_decision","status":"success"}',
        encoding="utf-8",
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
        "startup-errors.log",
        "junior-20260723T120000000000Z.log",
    }


def test_rejects_arbitrary_and_nested_log_paths(tmp_path: Path) -> None:
    (tmp_path / "personal.log").write_text("private", encoding="utf-8")

    with pytest.raises(DiagnosticLogError, match="not available"):
        read_diagnostic_log(tmp_path, "personal.log")
    with pytest.raises(DiagnosticLogError, match="not available"):
        read_diagnostic_log(tmp_path, "../startup-errors.log")


def test_download_resolves_only_a_recognized_owned_log(tmp_path: Path) -> None:
    owned = tmp_path / "junior-actions.log"
    owned.write_text('{"status":"completed"}\n', encoding="utf-8")
    (tmp_path / "personal.log").write_text("private", encoding="utf-8")

    assert get_diagnostic_log_download(tmp_path, owned.name) == owned.resolve()
    with pytest.raises(DiagnosticLogError, match="not available"):
        get_diagnostic_log_download(tmp_path, "personal.log")


def test_large_log_view_reads_only_bounded_tail(tmp_path: Path) -> None:
    path = tmp_path / "startup-errors.log"
    path.write_text(
        "old private-looking fixture\n"
        + ("x" * MAX_LOG_VIEW_BYTES)
        + "\nnew safe entry",
        encoding="utf-8",
    )

    view = read_diagnostic_log(tmp_path, path.name)

    assert view.truncated
    assert "Earlier log entries are hidden" in view.content
    assert "old private-looking fixture" not in view.content
    assert "new safe entry" in view.content


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
