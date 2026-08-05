"""Verify useful operational diagnostics stay structured and privacy-safe."""

import json
from pathlib import Path

from job_radar.database import connect_database
from job_radar.operational_event_log import (
    operational_log_name,
    record_operational_event,
)


def test_operational_log_has_timestamped_purpose_name_and_safe_fields(
    tmp_path: Path,
) -> None:
    assert record_operational_event(
        tmp_path,
        kind="user_actions",
        subsystem="web",
        event="user_action_completed",
        fields={
            "request_id": "request-1",
            "endpoint": "save_profile",
            "items": ["one", "two"],
            "unsafe_mapping": {"password": "secret"},
        },
    )

    name = operational_log_name("user_actions")
    payload = json.loads((tmp_path / name).read_text(encoding="utf-8"))

    assert name.startswith("junior-user-actions-")
    assert name.endswith("Z.log")
    assert payload["timestamp"]
    assert payload["request_id"] == "request-1"
    assert payload["items"] == ["one", "two"]
    assert "unsafe_mapping" not in payload
    assert "secret" not in json.dumps(payload)


def test_database_connection_records_operation_duration_and_rows(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "data" / "junior.sqlite3"
    database_path.parent.mkdir()
    with connect_database(database_path) as connection:
        connection.execute("CREATE TABLE example (value TEXT)")
        connection.execute("INSERT INTO example VALUES (?)", ("private",))

    log_path = tmp_path / "logs" / operational_log_name("database")
    payload = json.loads(log_path.read_text(encoding="utf-8"))

    assert payload["event"] == "transaction_completed"
    assert payload["operation"].endswith(
        ".test_database_connection_records_operation_duration_and_rows"
    )
    assert payload["rows_changed"] == 1
    assert payload["elapsed_seconds"] >= 0
    assert "private" not in log_path.read_text(encoding="utf-8")
