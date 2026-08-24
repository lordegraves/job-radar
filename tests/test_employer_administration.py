"""Verify global employer administration is guarded, reversible, and audited."""

import json
import sqlite3
from pathlib import Path

import pytest

from job_radar.domain_errors import EmployerInUseError
from job_radar.employer_admin_service import (
    EmployerAdminError,
    create_employer,
    get_admin_employer,
    list_admin_employers,
    list_employer_audit,
    list_employer_profile_assignments,
    permanently_delete_employer,
    set_employer_lifecycle,
    set_employer_profile_assignment,
    update_employer,
    update_employer_links,
    validate_employer,
    validate_source_configuration,
)
from job_radar.employer_connection_service import (
    test_employer_connection as run_employer_connection_test,
)
from job_radar.employer_models import EmployerSource
from job_radar.employer_storage import (
    assign_employer_to_profile,
    delete_employer_source,
    list_profile_employer_assignments,
)
from job_radar.profile_models import ManagedProfile
from job_radar.profile_storage import create_profile
from job_radar.web_app import create_app


def build_test_app(tmp_path: Path):
    settings_path = tmp_path / "config" / "settings.yaml"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(
        (
            f"database_path: {tmp_path / 'data' / 'junior.sqlite3'}\n"
            f"reports_path: {tmp_path / 'reports'}\n"
            f"logs_path: {tmp_path / 'logs'}\n"
        ),
        encoding="utf-8",
    )
    return create_app(settings_path=settings_path, base_directory=tmp_path)


def create_test_profile(database_path: Path) -> ManagedProfile:
    profile = ManagedProfile(
        profile_id="profile_1234abcd",
        display_name="Test User",
    )
    create_profile(database_path, profile)
    return profile


def test_admin_routes_require_unlock_and_render_catalog(tmp_path: Path) -> None:
    app = build_test_app(tmp_path)
    client = app.test_client()

    locked = client.get("/administration/employers")
    client.post("/administration/unlock", data={"confirmation": "ADMIN"})
    unlocked = client.get("/administration/employers")

    assert locked.status_code == 302
    assert "/administration/unlock" in locked.headers["Location"]
    assert unlocked.status_code == 200
    unlocked_html = unlocked.get_data(as_text=True)
    assert (
        'href="/settings?section=administration">&larr; Back to Settings &amp; Diagnostics</a>'
        in unlocked_html
    )
    assert "Employer Catalog" in unlocked_html
    assert "Add employer" in unlocked_html


def test_create_validate_enable_and_filter_employer(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "junior.sqlite3"

    created = create_employer(
        database_path,
        name="Example Systems",
        source_type="greenhouse",
        source_config={
            "source_slug": "example-systems",
            "careers_url": "https://example.invalid/careers",
        },
        notes="Fictional test employer.",
    )

    assert created.employer.enabled is False
    assert created.validation_state == "not_checked"

    validated = validate_employer(database_path, created.employer.employer_id)
    monkeypatch.setattr(
        "job_radar.employer_connection_service.collect_jobs_for_company",
        lambda config: [object()],
    )
    run_employer_connection_test(database_path, created.employer.employer_id)
    enabled = set_employer_lifecycle(
        database_path, created.employer.employer_id, "enable"
    )
    filtered = list_admin_employers(
        database_path,
        search="systems",
        source_type="greenhouse",
        configuration="configured",
        availability="available",
        validation="valid",
    )

    assert validated.validation_state == "valid"
    assert enabled.employer.enabled is True
    assert filtered == (enabled,)
    assert [entry["operation"] for entry in list_employer_audit(
        database_path, created.employer.employer_id
    )] == ["enable", "validate", "create"]


def test_source_migration_preserves_identity_and_requires_live_recheck(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    profile = create_test_profile(database_path)
    created = create_employer(
        database_path,
        name="Example Storage",
        source_type="icims",
        source_config={"source_url": "https://old.example.invalid/jobs"},
        notes="",
    )
    employer_id = created.employer.employer_id
    monkeypatch.setattr(
        "job_radar.employer_connection_service.collect_jobs_for_company",
        lambda config: [object()],
    )
    validate_employer(database_path, employer_id)
    run_employer_connection_test(database_path, employer_id)
    set_employer_lifecycle(database_path, employer_id, "enable")
    assign_employer_to_profile(database_path, profile.profile_id, employer_id)

    with pytest.raises(EmployerAdminError, match="Confirm"):
        update_employer(
            database_path,
            employer_id,
            name="Example Storage",
            source_type="ashby",
            source_config={"source_slug": "example-storage"},
            notes="",
        )

    migrated = update_employer(
        database_path,
        employer_id,
        name="Example Storage",
        source_type="ashby",
        source_config={"source_slug": "example-storage"},
        notes="",
        confirm_source_migration=True,
    )

    assert migrated.employer.employer_id == employer_id
    assert migrated.employer.source_type == "ashby"
    assert migrated.employer.source_config["source_slug"] == "example-storage"
    assert migrated.employer.enabled is False
    assert migrated.validation_state == "not_checked"
    assert migrated.source_change_pending_test is True
    assert [
        item.employer_id
        for item in list_profile_employer_assignments(
            database_path, profile.profile_id
        )
    ] == [employer_id]
    assert list_employer_audit(database_path, employer_id)[0]["operation"] == (
        "source_migration"
    )

    validate_employer(database_path, employer_id)
    with pytest.raises(EmployerAdminError, match="connection"):
        set_employer_lifecycle(database_path, employer_id, "enable")
    run_employer_connection_test(database_path, employer_id)
    assert set_employer_lifecycle(
        database_path, employer_id, "enable"
    ).employer.enabled


def test_invalid_configuration_cannot_be_enabled(tmp_path: Path) -> None:
    database_path = tmp_path / "junior.sqlite3"
    created = create_employer(
        database_path,
        name="Incomplete Kitchens",
        source_type="workday",
        source_config={},
        notes="",
    )

    invalid = validate_employer(database_path, created.employer.employer_id)

    assert invalid.validation_state == "invalid"
    assert invalid.validation_issues == ("Job source URL is required.",)
    with pytest.raises(EmployerAdminError, match="Validate"):
        set_employer_lifecycle(
            database_path, created.employer.employer_id, "enable"
        )


def test_usajobs_validation_accepts_collector_query_params() -> None:
    employer = EmployerSource(
        employer_id="nasa",
        name="NASA",
        source_type="usajobs",
        source_config={"query_params": {"Organization": "NN"}},
    )

    assert validate_source_configuration(employer) == ()


def test_disable_and_retire_preserve_profile_assignment(tmp_path: Path) -> None:
    database_path = tmp_path / "junior.sqlite3"
    profile = create_test_profile(database_path)
    created = create_employer(
        database_path,
        name="Example Foods",
        source_type="lever",
        source_config={"source_slug": "example-foods"},
        notes="",
    )
    validate_employer(database_path, created.employer.employer_id)
    set_employer_lifecycle(database_path, created.employer.employer_id, "enable")
    assign_employer_to_profile(
        database_path, profile.profile_id, created.employer.employer_id
    )

    disabled = set_employer_lifecycle(
        database_path, created.employer.employer_id, "disable"
    )
    retired = set_employer_lifecycle(
        database_path, created.employer.employer_id, "retire"
    )

    assignments = list_profile_employer_assignments(
        database_path, profile.profile_id
    )
    assert disabled.assigned_profile_count == 1
    assert retired.retired is True
    assert [item.employer_id for item in assignments] == [
        created.employer.employer_id
    ]
    with pytest.raises(EmployerAdminError, match="retired"):
        set_employer_lifecycle(
            database_path, created.employer.employer_id, "enable"
        )
    with pytest.raises(EmployerInUseError, match="cannot be permanently deleted"):
        delete_employer_source(database_path, created.employer.employer_id)


def test_edit_requires_revalidation_and_audit_excludes_configuration(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    created = create_employer(
        database_path,
        name="Example Labs",
        source_type="greenhouse",
        source_config={"source_slug": "example-labs"},
        notes="",
    )
    validate_employer(database_path, created.employer.employer_id)
    update_employer_links(
        database_path,
        created.employer.employer_id,
        links={"linkedin_url": "https://www.linkedin.com/company/example-labs"},
    )

    updated = update_employer(
        database_path,
        created.employer.employer_id,
        name="Example Research Labs",
        source_type="greenhouse",
        source_config={"source_slug": "research-labs"},
        notes="Operational note.",
    )

    assert updated.validation_state == "not_checked"
    assert updated.employer.name == "Example Research Labs"
    assert updated.employer.source_config["linkedin_url"] == (
        "https://www.linkedin.com/company/example-labs"
    )
    with sqlite3.connect(database_path) as connection:
        audit_json = "\n".join(
            value
            for row in connection.execute(
                """
                SELECT previous_state_json, new_state_json
                FROM employer_catalog_audit
                """
            )
            for value in row
        )
    assert "research-labs" not in audit_json
    assert "Operational note" not in audit_json
    assert "source_config" not in audit_json
    with sqlite3.connect(database_path) as connection:
        latest_state = json.loads(
            connection.execute(
            """
            SELECT new_state_json
            FROM employer_catalog_audit
            ORDER BY audit_id DESC
            LIMIT 1
            """
            ).fetchone()[0]
        )
    assert latest_state["name"] == "Example Research Labs"


def test_admin_post_workflow_uses_csrf_and_keeps_new_employer_disabled(
    tmp_path: Path,
) -> None:
    app = build_test_app(tmp_path)
    client = app.test_client()
    client.post("/administration/unlock", data={"confirmation": "ADMIN"})

    response = client.post(
        "/administration/employers/new",
        data={
            "name": "Example Manufacturing",
            "source_type": "greenhouse",
            "source_slug": "example-manufacturing",
            "careers_url": "https://example.invalid/jobs",
            "notes": "",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Employer created" in response.get_data(as_text=True)
    record = get_admin_employer(
        tmp_path / "data" / "junior.sqlite3",
        "example-manufacturing",
    )
    assert record is not None
    assert record.employer.enabled is False


def test_admin_connection_test_shows_safe_result(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = build_test_app(tmp_path)
    database_path = tmp_path / "data" / "junior.sqlite3"
    record = create_employer(
        database_path,
        name="Example Bakery",
        source_type="greenhouse",
        source_config={"source_slug": "example-bakery"},
        notes="",
    )
    monkeypatch.setattr(
        "job_radar.employer_connection_service.collect_jobs_for_company",
        lambda config: [],
    )
    client = app.test_client()
    client.post("/administration/unlock", data={"confirmation": "ADMIN"})

    response = client.post(
        (
            "/administration/employers/"
            f"{record.employer.employer_id}/test-connection"
        ),
        follow_redirects=True,
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "currently has no public job openings" in html
    assert "Source connection</dt><dd>Connected" in html


def test_admin_edit_exposes_confirmed_platform_migration(tmp_path: Path) -> None:
    app = build_test_app(tmp_path)
    database_path = tmp_path / "data" / "junior.sqlite3"
    record = create_employer(
        database_path,
        name="Example Storage",
        source_type="icims",
        source_config={"source_url": "https://old.example.invalid/jobs"},
        notes="",
    )
    employer_id = record.employer.employer_id
    client = app.test_client()
    client.post("/administration/unlock", data={"confirmation": "ADMIN"})

    page = client.get(
        f"/administration/employers/{employer_id}/edit?source_type=ashby"
    )
    html = page.get_data(as_text=True)

    assert page.status_code == 200
    assert '<option value="ashby" selected>ashby</option>' in html
    assert 'name="source_slug"' in html
    assert 'name="confirm_source_migration"' in html
    assert "for every profile using it" in html

    saved = client.post(
        f"/administration/employers/{employer_id}/edit",
        data={
            "name": "Example Storage",
            "source_type": "ashby",
            "source_slug": "example-storage",
            "confirm_source_migration": "yes",
            "notes": "",
        },
        follow_redirects=True,
    )
    migrated = get_admin_employer(database_path, employer_id)

    assert saved.status_code == 200
    assert migrated is not None
    assert migrated.employer.source_type == "ashby"
    assert migrated.source_change_pending_test is True
    assert "Validation must pass" in saved.get_data(as_text=True)
    validate_employer(database_path, employer_id)
    validated_html = client.get(
        f"/administration/employers/{employer_id}"
    ).get_data(as_text=True)
    assert "successful connection test is required" in validated_html


def test_administrator_assigns_and_removes_one_profile_only(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    first = create_test_profile(database_path)
    second = ManagedProfile(
        profile_id="profile_5678efgh",
        display_name="Second Test User",
    )
    create_profile(database_path, second)
    employer = create_employer(
        database_path,
        name="Example Catering",
        source_type="greenhouse",
        source_config={"source_slug": "example-catering"},
        notes="",
    )
    validate_employer(database_path, employer.employer.employer_id)
    set_employer_lifecycle(
        database_path, employer.employer.employer_id, "enable"
    )

    assert set_employer_profile_assignment(
        database_path,
        employer.employer.employer_id,
        first.profile_id,
        assigned=True,
    )
    assignments = list_employer_profile_assignments(
        database_path, employer.employer.employer_id
    )
    assert [(item.profile_name, item.assigned) for item in assignments] == [
        ("Second Test User", False),
        ("Test User", True),
    ]

    assert set_employer_profile_assignment(
        database_path,
        employer.employer.employer_id,
        first.profile_id,
        assigned=False,
    )
    assert list_profile_employer_assignments(database_path, first.profile_id) == []
    assert list_profile_employer_assignments(database_path, second.profile_id) == []


def test_permanent_delete_requires_confirmation_and_unused_employer(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    profile = create_test_profile(database_path)
    unused = create_employer(
        database_path,
        name="Unused Example",
        source_type="lever",
        source_config={"source_slug": "unused-example"},
        notes="",
    )

    with pytest.raises(EmployerAdminError, match="Type DELETE"):
        permanently_delete_employer(
            database_path,
            unused.employer.employer_id,
            confirmation="delete",
        )
    assert permanently_delete_employer(
        database_path,
        unused.employer.employer_id,
        confirmation="DELETE",
    )
    assert get_admin_employer(
        database_path, unused.employer.employer_id
    ) is None
    safety_backups = list(
        (tmp_path / "backups" / "safety").glob(
            "junior.sqlite3.pre-company-delete-*.bak"
        )
    )
    assert len(safety_backups) == 1
    with sqlite3.connect(safety_backups[0]) as backup_connection:
        backed_up_employer = backup_connection.execute(
            "SELECT name FROM employer_sources WHERE employer_id = ?",
            (unused.employer.employer_id,),
        ).fetchone()
    assert backed_up_employer == ("Unused Example",)

    used = create_employer(
        database_path,
        name="Used Example",
        source_type="lever",
        source_config={"source_slug": "used-example"},
        notes="",
    )
    assign_employer_to_profile(
        database_path, profile.profile_id, used.employer.employer_id
    )
    with pytest.raises(EmployerAdminError, match="cannot be deleted"):
        permanently_delete_employer(
            database_path,
            used.employer.employer_id,
            confirmation="DELETE",
        )
    assert len(
        list(
            (tmp_path / "backups" / "safety").glob(
                "junior.sqlite3.pre-company-delete-*.bak"
            )
        )
    ) == 1


def test_admin_profile_assignment_and_delete_routes(tmp_path: Path) -> None:
    app = build_test_app(tmp_path)
    database_path = tmp_path / "data" / "junior.sqlite3"
    profile = create_test_profile(database_path)
    employer = create_employer(
        database_path,
        name="Example Restaurant",
        source_type="greenhouse",
        source_config={"source_slug": "example-restaurant"},
        notes="",
    )
    validate_employer(database_path, employer.employer.employer_id)
    set_employer_lifecycle(
        database_path, employer.employer.employer_id, "enable"
    )
    client = app.test_client()
    client.post("/administration/unlock", data={"confirmation": "ADMIN"})

    detail = client.get(
        f"/administration/employers/{employer.employer.employer_id}"
    )
    assert "Profile assignments" in detail.get_data(as_text=True)
    assert "Test User" in detail.get_data(as_text=True)

    assigned = client.post(
        (
            f"/administration/employers/{employer.employer.employer_id}"
            f"/profiles/{profile.profile_id}"
        ),
        data={"operation": "assign"},
        follow_redirects=True,
    )
    assert "Employer assigned to that profile." in assigned.get_data(as_text=True)

    invalid = client.post(
        (
            f"/administration/employers/{employer.employer.employer_id}"
            f"/profiles/{profile.profile_id}"
        ),
        data={"operation": "unexpected"},
        follow_redirects=True,
    )
    assert "Choose Assign or Remove." in invalid.get_data(as_text=True)
    assert len(list_profile_employer_assignments(
        database_path, profile.profile_id
    )) == 1

    blocked_delete = client.post(
        f"/administration/employers/{employer.employer.employer_id}/delete",
        data={"confirmation": "DELETE"},
        follow_redirects=True,
    )
    assert "cannot be deleted" in blocked_delete.get_data(as_text=True)
