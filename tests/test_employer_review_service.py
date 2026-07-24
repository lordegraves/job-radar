"""Verify pending employer reviews preserve profile isolation and audit decisions."""

import sqlite3
from pathlib import Path

import pytest

from job_radar.employer_admin_service import (
    create_employer,
    set_employer_lifecycle,
    validate_employer,
)
from job_radar.employer_resolution_service import resolve_employer_submission
from job_radar.employer_review_service import (
    CANCELLED,
    CONFIGURED_NEW,
    MATCHED_EXISTING,
    PENDING,
    REJECTED,
    UNSUPPORTED,
    EmployerReviewError,
    assign_resolved_employer,
    cancel_profile_review_request,
    get_review_request,
    list_review_audit,
    list_review_requests,
    list_profile_review_states,
    mark_configured_new,
    mark_review_status,
    resolve_to_existing_employer,
)
from job_radar.employer_storage import list_profile_employer_assignments
from job_radar.profile_models import ManagedProfile
from job_radar.profile_storage import create_profile, set_active_profile
from job_radar.web_app import create_app


def create_test_profile(
    database_path: Path,
    profile_id: str = "profile_1234abcd",
    name: str = "Test User",
) -> ManagedProfile:
    profile = ManagedProfile(profile_id=profile_id, display_name=name)
    create_profile(database_path, profile)
    return profile


def create_pending_request(database_path: Path, profile_id: str) -> str:
    result = resolve_employer_submission(
        database_path,
        profile_id=profile_id,
        company_name="Example Kitchens",
    )
    assert result.review_request_id is not None
    return result.review_request_id


def create_available_employer(database_path: Path, name: str = "Example Foods"):
    record = create_employer(
        database_path,
        name=name,
        source_type="greenhouse",
        source_config={"source_slug": "example-foods"},
        notes="",
    )
    validate_employer(database_path, record.employer.employer_id)
    return set_employer_lifecycle(
        database_path, record.employer.employer_id, "enable"
    )


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


def test_review_queue_lists_safe_profile_context(tmp_path: Path) -> None:
    database_path = tmp_path / "junior.sqlite3"
    profile = create_test_profile(database_path)
    request_id = create_pending_request(database_path, profile.profile_id)

    reviews = list_review_requests(database_path)
    review = get_review_request(database_path, request_id)

    assert reviews == (review,)
    assert review is not None
    assert review.status == PENDING
    assert review.requesting_profile_name == "Test User"
    assert review.safe_summary.startswith("Junior needs an administrator")
    states = list_profile_review_states(database_path, profile.profile_id)
    assert states[0].state_label == "Setup pending"


def test_match_existing_optionally_assigns_only_requesting_profile(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    requesting = create_test_profile(database_path, "profile_1111aaaa", "First")
    other = create_test_profile(database_path, "profile_2222bbbb", "Second")
    request_id = create_pending_request(database_path, requesting.profile_id)
    employer = create_available_employer(database_path)

    resolved = resolve_to_existing_employer(
        database_path,
        request_id,
        employer.employer.employer_id,
        assign_to_profile=True,
    )

    assert resolved.status == MATCHED_EXISTING
    assert [
        item.employer_id
        for item in list_profile_employer_assignments(
            database_path, requesting.profile_id
        )
    ] == [employer.employer.employer_id]
    assert list_profile_employer_assignments(database_path, other.profile_id) == []
    audit = list_review_audit(database_path, request_id)
    assert audit[0]["operation"] == "match_existing"
    assert audit[0]["assignment_completed"] == 1


def test_match_rejects_unavailable_employer_when_assignment_requested(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    profile = create_test_profile(database_path)
    request_id = create_pending_request(database_path, profile.profile_id)
    employer = create_employer(
        database_path,
        name="Disabled Example",
        source_type="greenhouse",
        source_config={"source_slug": "disabled-example"},
        notes="",
    )

    with pytest.raises(EmployerReviewError, match="available"):
        resolve_to_existing_employer(
            database_path,
            request_id,
            employer.employer.employer_id,
            assign_to_profile=True,
        )
    assert get_review_request(database_path, request_id).status == PENDING  # type: ignore[union-attr]


@pytest.mark.parametrize("status", (UNSUPPORTED, REJECTED, CANCELLED))
def test_close_review_statuses_are_audited(
    tmp_path: Path,
    status: str,
) -> None:
    database_path = tmp_path / f"{status}.sqlite3"
    profile = create_test_profile(database_path)
    request_id = create_pending_request(database_path, profile.profile_id)

    resolved = mark_review_status(database_path, request_id, status)

    assert resolved.status == status
    assert list_review_audit(database_path, request_id)[0]["new_status"] == status
    with pytest.raises(EmployerReviewError, match="already"):
        mark_review_status(database_path, request_id, status)


def test_profile_can_remove_only_its_own_unfinished_attempt(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "cancel.sqlite3"
    owner = create_test_profile(database_path, "profile_1111aaaa", "Owner")
    other = create_test_profile(database_path, "profile_2222bbbb", "Other")
    request_id = create_pending_request(database_path, owner.profile_id)

    with pytest.raises(EmployerReviewError, match="not available"):
        cancel_profile_review_request(
            database_path,
            request_id,
            profile_id=other.profile_id,
            confirmation="REMOVE",
        )
    with pytest.raises(EmployerReviewError, match="Type REMOVE"):
        cancel_profile_review_request(
            database_path,
            request_id,
            profile_id=owner.profile_id,
            confirmation="",
        )

    cancel_profile_review_request(
        database_path,
        request_id,
        profile_id=owner.profile_id,
        confirmation="REMOVE",
    )

    assert get_review_request(database_path, request_id).status == CANCELLED  # type: ignore[union-attr]
    assert list_profile_review_states(database_path, owner.profile_id) == ()


def test_profile_routes_offer_retry_and_guarded_attempt_removal(
    tmp_path: Path,
) -> None:
    app = build_test_app(tmp_path)
    database_path = tmp_path / "data" / "junior.sqlite3"
    profile = create_test_profile(database_path)
    set_active_profile(database_path, profile.profile_id)
    request_id = create_pending_request(database_path, profile.profile_id)
    client = app.test_client()

    companies_html = client.get("/companies").get_data(as_text=True)
    retry_html = client.get(
        f"/companies/add?retry={request_id}"
    ).get_data(as_text=True)
    removed = client.post(
        f"/companies/setup-requests/{request_id}/remove",
        data={"confirmation": "REMOVE"},
        follow_redirects=True,
    )

    assert "Retry setup" in companies_html
    assert "Remove attempt" in companies_html
    assert "Example Kitchens" in retry_html
    assert f'value="{request_id}"' in retry_html
    assert "unfinished setup attempt was removed" in removed.get_data(
        as_text=True
    )
    assert get_review_request(database_path, request_id).status == CANCELLED  # type: ignore[union-attr]


def test_configured_new_can_be_assigned_after_validation_and_enablement(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    profile = create_test_profile(database_path)
    request_id = create_pending_request(database_path, profile.profile_id)
    employer = create_employer(
        database_path,
        name="New Example",
        source_type="greenhouse",
        source_config={"source_slug": "new-example"},
        notes="",
    )

    configured = mark_configured_new(
        database_path, request_id, employer.employer.employer_id
    )
    assert configured.status == CONFIGURED_NEW
    with pytest.raises(EmployerReviewError, match="Validate"):
        assign_resolved_employer(database_path, request_id)

    validate_employer(database_path, employer.employer.employer_id)
    set_employer_lifecycle(
        database_path, employer.employer.employer_id, "enable"
    )
    assert assign_resolved_employer(database_path, request_id) is True
    assert assign_resolved_employer(database_path, request_id) is False


def test_review_queue_routes_require_administration_and_support_match(
    tmp_path: Path,
) -> None:
    app = build_test_app(tmp_path)
    database_path = tmp_path / "data" / "junior.sqlite3"
    profile = create_test_profile(database_path)
    request_id = create_pending_request(database_path, profile.profile_id)
    employer = create_available_employer(database_path)
    client = app.test_client()

    locked = client.get("/administration/employer-reviews")
    client.post("/administration/unlock", data={"confirmation": "ADMIN"})
    queue = client.get("/administration/employer-reviews")
    resolved = client.post(
        f"/administration/employer-reviews/{request_id}/match",
        data={
            "employer_id": employer.employer.employer_id,
            "assign_to_profile": "yes",
        },
        follow_redirects=True,
    )

    assert locked.status_code == 302
    assert "Employer Review Queue" in queue.get_data(as_text=True)
    assert "Example Kitchens" in queue.get_data(as_text=True)
    assert "Review matched" in resolved.get_data(as_text=True)


def test_review_audit_contains_no_raw_submission_or_profile_content(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    profile = create_test_profile(database_path)
    request_id = create_pending_request(database_path, profile.profile_id)
    mark_review_status(database_path, request_id, REJECTED)

    with sqlite3.connect(database_path) as connection:
        audit_values = "\n".join(
            str(value)
            for row in connection.execute(
                "SELECT * FROM employer_review_audit"
            ).fetchall()
            for value in row
        )
    assert "Example Kitchens" not in audit_values
    assert "Test User" not in audit_values
