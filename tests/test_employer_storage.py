"""Verify app-owned employer source persistence."""

from pathlib import Path

from job_radar.employer_models import EmployerSource
from job_radar.employer_storage import (
    delete_employer_source,
    get_employer_source,
    list_employer_sources,
    upsert_employer_source,
)


def make_employer(
    *,
    employer_id: str = "example_bakery",
    name: str = "Example Bakery",
    enabled: bool = True,
) -> EmployerSource:
    return EmployerSource(
        employer_id=employer_id,
        name=name,
        source_type="greenhouse",
        enabled=enabled,
        source_config={
            "source_slug": employer_id,
            "query_params": {
                "location": "Carrollton",
            },
            "page_size": 50,
        },
        notes="Synthetic employer used only for tests.",
    )


def test_employer_source_round_trip_preserves_complete_config(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    employer = make_employer()

    upsert_employer_source(database_path, employer)

    assert get_employer_source(database_path, employer.employer_id) == employer


def test_upsert_employer_source_replaces_editable_values(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    original = make_employer()
    updated = EmployerSource(
        employer_id=original.employer_id,
        name="Updated Bakery",
        source_type="html",
        enabled=False,
        source_config={
            "source_url": "https://example.invalid/careers",
        },
        notes="Updated synthetic employer.",
    )

    upsert_employer_source(database_path, original)
    upsert_employer_source(database_path, updated)

    assert get_employer_source(database_path, original.employer_id) == updated


def test_list_employer_sources_filters_enabled_and_orders_by_name(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    disabled = make_employer(
        employer_id="disabled_law",
        name="Zeta Law",
        enabled=False,
    )
    enabled = make_employer(
        employer_id="enabled_bakery",
        name="Alpha Bakery",
    )

    upsert_employer_source(database_path, disabled)
    upsert_employer_source(database_path, enabled)

    assert list_employer_sources(database_path) == [enabled, disabled]
    assert list_employer_sources(database_path, enabled_only=True) == [enabled]


def test_delete_employer_source_returns_whether_record_existed(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    employer = make_employer()
    upsert_employer_source(database_path, employer)

    assert delete_employer_source(database_path, employer.employer_id) is True
    assert delete_employer_source(database_path, employer.employer_id) is False
    assert get_employer_source(database_path, employer.employer_id) is None
