"""Verify the user-facing company workspace follows profile assignments."""

from pathlib import Path

import job_radar.company_workspace_service as workspace_service
from job_radar.company_workspace_service import build_company_workspace
from job_radar.employer_models import EmployerSource
from job_radar.employer_storage import (
    set_profile_employer_enabled,
    upsert_employer_source,
)
from job_radar.profile_models import ManagedProfile
from job_radar.profile_storage import create_profile, set_active_profile


def test_workspace_is_empty_without_active_profile(tmp_path: Path) -> None:
    workspace = build_company_workspace(tmp_path / "junior.sqlite3")

    assert workspace.active_profile is None
    assert workspace.companies == ()
    assert workspace.total_companies == 0
    assert workspace.scanning_companies == 0
    assert workspace.paused_companies == 0


def test_workspace_is_empty_when_profile_has_no_companies(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    profile = ManagedProfile(
        profile_id="profile_aaaaaaaa",
        display_name="Test User",
    )
    create_profile(database_path, profile)
    set_active_profile(database_path, profile.profile_id)

    workspace = build_company_workspace(database_path)

    assert workspace.active_profile == profile
    assert workspace.companies == ()
    assert workspace.total_companies == 0


def test_workspace_uses_assignment_state_and_sorts_companies(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    profile = ManagedProfile(
        profile_id="profile_aaaaaaaa",
        display_name="Test User",
        company_ids=("zeta_cafe", "alpha_bakery"),
    )
    create_profile(database_path, profile)
    set_active_profile(database_path, profile.profile_id)

    upsert_employer_source(
        database_path,
        EmployerSource(
            employer_id="zeta_cafe",
            name="Zeta Cafe",
            source_type="html",
            enabled=False,
            source_config={"source_url": "https://zeta.invalid/jobs"},
        ),
    )
    upsert_employer_source(
        database_path,
        EmployerSource(
            employer_id="alpha_bakery",
            name="Alpha Bakery",
            source_type="html",
            source_config={"source_url": "https://alpha.invalid/jobs"},
        ),
    )
    upsert_employer_source(
        database_path,
        EmployerSource(
            employer_id="unassigned_market",
            name="Unassigned Market",
            source_type="html",
            source_config={"source_url": "https://market.invalid/jobs"},
        ),
    )
    set_profile_employer_enabled(
        database_path,
        profile.profile_id,
        "alpha_bakery",
        enabled=False,
    )

    workspace = build_company_workspace(database_path)

    assert [(item.name, item.scanning) for item in workspace.companies] == [
        ("Alpha Bakery", False),
        ("Zeta Cafe", True),
    ]
    assert workspace.total_companies == 2
    assert workspace.scanning_companies == 1
    assert workspace.paused_companies == 1


def test_workspace_skips_missing_employer_record(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    profile = ManagedProfile(
        profile_id="profile_aaaaaaaa",
        display_name="Test User",
        company_ids=("example_company",),
    )
    create_profile(database_path, profile)
    set_active_profile(database_path, profile.profile_id)
    upsert_employer_source(
        database_path,
        EmployerSource(
            employer_id="example_company",
            name="Example Company",
            source_type="html",
            source_config={"source_url": "https://example.invalid/jobs"},
        ),
    )
    monkeypatch.setattr(
        workspace_service,
        "get_employer_source",
        lambda *_args: None,
    )

    workspace = build_company_workspace(database_path)

    assert workspace.companies == ()
    assert workspace.total_companies == 0
