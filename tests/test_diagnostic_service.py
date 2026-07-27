"""Verify safe health categories never preserve private exception text."""

from pathlib import Path

import pytest
import requests

from job_radar.collectors.greenhouse import CollectorError
from job_radar.diagnostic_service import (
    build_diagnostics_view,
    classify_collector_failure,
    classify_scan_failure,
)
from job_radar.storage import (
    fail_scan_run,
    initialize_database,
    record_scan_error,
    start_scan_run,
)


def write_settings(path: Path, database_path: Path) -> None:
    path.write_text(
        f"""
database_path: {database_path}
reports_path: {path.parent / "reports"}
logs_path: {path.parent / "logs"}
email:
  enabled: false
""",
        encoding="utf-8",
    )


def test_collector_failure_distinguishes_network_without_raw_text() -> None:
    try:
        raise requests.ConnectionError("private host and token")
    except requests.ConnectionError as cause:
        error = CollectorError("private collector response")
        error.__cause__ = cause

    outcome = classify_collector_failure(error)

    assert outcome.category == "network"
    assert outcome.category_label == "Network"
    assert "could not reach" in outcome.message
    assert "private" not in outcome.message
    assert "token" not in outcome.message


@pytest.mark.parametrize(
    ("status_code", "category", "message_fragment"),
    (
        (403, "collector", "denied"),
        (404, "collector", "not found"),
        (429, "network", "limited"),
        (503, "network", "temporary problem"),
    ),
)
def test_collector_failure_explains_safe_http_categories(
    status_code: int,
    category: str,
    message_fragment: str,
) -> None:
    response = requests.Response()
    response.status_code = status_code
    cause = requests.HTTPError(
        "private response body and token",
        response=response,
    )
    error = CollectorError("private collector response")
    error.__cause__ = cause

    outcome = classify_collector_failure(error)

    assert outcome.category == category
    assert message_fragment in outcome.message
    assert "private" not in outcome.message
    assert "token" not in outcome.message


def test_scan_failure_distinguishes_owned_stages() -> None:
    assert classify_scan_failure("configuration").category == "configuration"
    assert classify_scan_failure("collection").category == "collector"
    assert classify_scan_failure("email_delivery").category == "email"
    assert classify_scan_failure("report_generation").category == "application"


def test_diagnostics_view_uses_sanitized_stored_scan_failure(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    settings_path = tmp_path / "settings.yaml"
    write_settings(settings_path, database_path)
    initialize_database(database_path)
    scan_run_id = start_scan_run(
        database_path,
        requested_at="2026-07-23T12:00:00+00:00",
        companies_requested=1,
        companies_enabled=1,
        current_stage="configuration",
    )
    record_scan_error(
        database_path,
        scan_run_id=scan_run_id,
        error_type="configuration_failure",
        error_message="Safe configuration guidance.",
    )
    fail_scan_run(
        database_path,
        scan_run_id=scan_run_id,
        finished_at="2026-07-23T12:01:00+00:00",
        failed_stage="configuration",
        failure_summary="Safe configuration guidance.",
    )

    view = build_diagnostics_view(database_path, settings_path)
    scan_card = next(card for card in view.cards if card.title == "Latest scan")

    assert scan_card.state == "Needs attention"
    assert scan_card.category == "Configuration"
    assert scan_card.summary == "Safe configuration guidance."
    assert {card.title for card in view.cards} == {
        "Application configuration",
        "Latest scan",
        "Company sources",
        "Email delivery",
    }
