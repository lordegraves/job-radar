"""Verify normal users see only safe, profile-aware catalog choices."""

from pathlib import Path

import pytest

from job_radar.company_catalog_query_service import (
    ALREADY_ADDED,
    AVAILABLE,
    NEEDS_SETUP,
    UNAVAILABLE,
    build_company_catalog_view,
    evaluate_employer_availability,
)
from job_radar.employer_models import EmployerSource
from job_radar.employer_storage import upsert_employer_source
from job_radar.profile_models import ManagedProfile
from job_radar.profile_storage import create_profile, set_active_profile


def add_employer(
    database_path: Path,
    *,
    employer_id: str,
    name: str,
    enabled: bool = True,
    source_config: dict | None = None,
) -> None:
    upsert_employer_source(
        database_path,
        EmployerSource(
            employer_id=employer_id,
            name=name,
            source_type="html",
            enabled=enabled,
            source_config=source_config or {},
            notes="Technical catalog note that normal users must not see.",
        ),
    )


def test_catalog_states_are_profile_specific_and_searchable(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    add_employer(
        database_path,
        employer_id="assigned_bakery",
        name="Assigned Bakery",
        source_config={"source_url": "https://assigned.invalid/jobs"},
    )
    add_employer(
        database_path,
        employer_id="available_cafe",
        name="Available Cafe",
        source_config={"source_url": "https://available.invalid/jobs"},
    )
    add_employer(
        database_path,
        employer_id="incomplete_market",
        name="Incomplete Market",
    )
    add_employer(
        database_path,
        employer_id="disabled_shop",
        name="Disabled Shop",
        enabled=False,
        source_config={"source_url": "https://disabled.invalid/jobs"},
    )
    profile = ManagedProfile(
        profile_id="profile_aaaaaaaa",
        display_name="Test User",
        company_ids=("assigned_bakery",),
    )
    create_profile(database_path, profile)
    set_active_profile(database_path, profile.profile_id)

    catalog = build_company_catalog_view(database_path)

    assert [(item.name, item.state) for item in catalog.companies] == [
        ("Assigned Bakery", ALREADY_ADDED),
        ("Available Cafe", AVAILABLE),
        ("Disabled Shop", UNAVAILABLE),
        ("Incomplete Market", NEEDS_SETUP),
    ]
    available = next(
        item for item in catalog.companies if item.name == "Available Cafe"
    )
    assert available.can_assign is True
    assert available.careers_url == "https://available.invalid/jobs"

    filtered = build_company_catalog_view(
        database_path,
        search_query="  cafe  ",
    )
    assert [item.name for item in filtered.companies] == ["Available Cafe"]
    assert filtered.search_query == "cafe"


def test_catalog_is_empty_without_active_profile(tmp_path: Path) -> None:
    catalog = build_company_catalog_view(tmp_path / "junior.sqlite3")

    assert catalog.active_profile is None
    assert catalog.companies == ()


@pytest.mark.parametrize(
    ("source_type", "source_config"),
    [
        ("greenhouse", {"source_slug": "example"}),
        ("workday", {"source_url": "https://example.invalid/jobs"}),
        (
            "activate",
            {
                "source_url": "https://example.invalid/api",
                "source_base_url": "https://example.invalid/jobs",
            },
        ),
        (
            "adp",
            {
                "source_url": (
                    "https://example.invalid/jobs?cid=example&ccId=example"
                )
            },
        ),
        ("schoolspring", {"domain_name": "example"}),
        ("usajobs", {"query_params": {"Organization": "EXAMPLE"}}),
    ],
)
def test_supported_source_families_require_complete_configuration(
    source_type: str,
    source_config: dict,
) -> None:
    ready = EmployerSource(
        employer_id="example_employer",
        name="Example Employer",
        source_type=source_type,
        source_config=source_config,
    )
    incomplete = EmployerSource(
        employer_id="incomplete_employer",
        name="Incomplete Employer",
        source_type=source_type,
        source_config={},
    )

    assert evaluate_employer_availability(ready).state == AVAILABLE
    assert evaluate_employer_availability(incomplete).state == NEEDS_SETUP
