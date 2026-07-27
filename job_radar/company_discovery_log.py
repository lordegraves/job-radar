"""Write bounded, privacy-safe diagnostics for interactive company discovery."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Mapping


LOG_NAME = "junior-company-discovery.log"
MAX_LOG_BYTES = 1_000_000
_SAFE_FIELDS = {
    "candidate_host",
    "candidate_number",
    "external_lookup_enabled",
    "job_count",
    "outcome",
    "source_type",
    "stage",
}


def record_company_discovery_event(
    logs_path: str | Path,
    stage: str,
    fields: Mapping[str, object],
) -> None:
    """Append one allowlisted event without URLs, user data, or exceptions."""

    directory = Path(logs_path)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / LOG_NAME
    if path.exists() and path.stat().st_size >= MAX_LOG_BYTES:
        path.replace(directory / f"{LOG_NAME}.previous")
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": "company_discovery",
        "stage": stage,
    }
    payload.update(
        {
            key: value
            for key, value in fields.items()
            if key in _SAFE_FIELDS and isinstance(value, (bool, int, str))
        }
    )
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(payload, sort_keys=True) + "\n")
