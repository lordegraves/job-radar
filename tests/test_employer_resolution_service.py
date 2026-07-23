"""Verify safe company-name and careers-URL resolution with fictional data."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from job_radar.employer_models import EmployerSource
from job_radar.employer_resolution_service import (
    ALREADY_ASSIGNED,
    AMBIGUOUS_MATCH,
    CREATED_SCAN_READY,
    INVALID_INPUT,
    MATCHED_EXISTING,
    PENDING_REVIEW,
    UNSUPPORTED_SITE,
    detect_employer_source,
    normalize_careers_url,
    normalize_company_name,
    resolve_employer_submission,
)
from job_radar.employer_storage import (
    assign_employer_to_profile,
    get_employer_source,
    list_profile_employer_assignments,
    upsert_employer_source,
)
from job_radar.profile_models import ManagedProfile
from job_radar.profile_storage import create_profile
from job_radar.storage import initialize_database


def create_test_profile(
    database_path: Path,
    profile_id: str = "profile_1234abcd",
) -> ManagedProfile:
    profile = ManagedProfile(profile_id=profile_id, display_name="Test User")
    create_profile(database_path, profile)
    return profile


def add_catalog_employer(
    database_path: Path,
    *,
    employer_id: str = "example-systems",
    name: str = "Example Systems",
    careers_url: str = "https://example.invalid/careers",
) -> EmployerSource:
    employer = EmployerSource(
        employer_id=employer_id,
        name=name,
        source_type="greenhouse",
        source_config={
            "source_slug": employer_id,
            "careers_url": careers_url,
        },
    )
    upsert_employer_source(database_path, employer)
    return employer


def test_name_and_url_normalization_is_safe_and_stable() -> None:
    assert normalize_company_name("  Éxample   Foods  ") == "éxample foods"
    assert normalize_careers_url(
        "HTTPS://Jobs.Example.COM/careers/?utm_source=test&team=food#openings"
    ) == "https://jobs.example.com/careers?team=food"

    for unsafe in (
        "file:///etc/passwd",
        "http://localhost/jobs",
        "http://127.0.0.1/jobs",
        "http://169.254.1.1/jobs",
        "http://10.0.0.2/jobs",
        "https://jobs.example.com:8443/jobs",
    ):
        with pytest.raises(ValueError):
            normalize_careers_url(unsafe)


@pytest.mark.parametrize(
    ("url", "source_type", "identifier", "scan_ready"),
    (
        ("https://boards.greenhouse.io/example", "greenhouse", "example", True),
        ("https://jobs.lever.co/example", "lever", "example", True),
        ("https://jobs.ashbyhq.com/example", "ashby", "example", True),
        ("https://example.wd5.myworkdayjobs.com/jobs", "workday", None, False),
        ("https://example.icims.com/jobs", "icims", None, False),
        ("https://jobs.smartrecruiters.com/Example", "smartrecruiters", None, False),
        ("https://example.invalid/careers", "html", None, False),
    ),
)
def test_supported_source_detection_is_centralized(
    url: str,
    source_type: str,
    identifier: str | None,
    scan_ready: bool,
) -> None:
    detected = detect_employer_source(url)

    assert detected.source_type == source_type
    assert detected.source_identifier == identifier
    assert detected.scan_ready is scan_ready


def test_exact_name_url_alias_and_already_assigned_resolution(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    profile = create_test_profile(database_path)
    employer = add_catalog_employer(database_path)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO employer_aliases (employer_id, alias, normalized_alias)
            VALUES (?, 'Example Tech', 'example tech')
            """,
            (employer.employer_id,),
        )

    by_name = resolve_employer_submission(
        database_path,
        profile_id=profile.profile_id,
        company_name="EXAMPLE SYSTEMS",
    )
    by_url = resolve_employer_submission(
        database_path,
        profile_id=profile.profile_id,
        careers_url="https://example.invalid/careers/",
    )
    by_alias = resolve_employer_submission(
        database_path,
        profile_id=profile.profile_id,
        company_name="Example Tech",
    )
    assign_employer_to_profile(
        database_path, profile.profile_id, employer.employer_id
    )
    assigned = resolve_employer_submission(
        database_path,
        profile_id=profile.profile_id,
        company_name="Example Systems",
    )

    assert by_name.status == MATCHED_EXISTING
    assert by_url.status == MATCHED_EXISTING
    assert by_alias.status == MATCHED_EXISTING
    assert assigned.status == ALREADY_ASSIGNED


def test_similar_name_requires_confirmation_without_merging(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    profile = create_test_profile(database_path)
    add_catalog_employer(
        database_path,
        name="Example Systems Group",
    )

    result = resolve_employer_submission(
        database_path,
        profile_id=profile.profile_id,
        company_name="Example Systems",
    )

    assert result.status == AMBIGUOUS_MATCH
    assert result.possible_employers == (
        ("example-systems", "Example Systems Group"),
    )


def test_recognized_scan_ready_url_creates_and_assigns_atomically(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    profile = create_test_profile(database_path)

    result = resolve_employer_submission(
        database_path,
        profile_id=profile.profile_id,
        company_name="Example Kitchens",
        careers_url="https://jobs.lever.co/example-kitchens",
    )

    employer = get_employer_source(database_path, result.employer_id or "")
    assignments = list_profile_employer_assignments(
        database_path, profile.profile_id
    )
    assert result.status == CREATED_SCAN_READY
    assert employer is not None
    assert employer.source_type == "lever"
    assert employer.source_config["source_slug"] == "example-kitchens"
    assert [item.employer_id for item in assignments] == [result.employer_id]


def test_unresolved_and_unsupported_submissions_create_one_pending_request(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    profile = create_test_profile(database_path)

    name_only = resolve_employer_submission(
        database_path,
        profile_id=profile.profile_id,
        company_name="Example Catering",
    )
    duplicate = resolve_employer_submission(
        database_path,
        profile_id=profile.profile_id,
        company_name="example catering",
    )
    unsupported = resolve_employer_submission(
        database_path,
        profile_id=profile.profile_id,
        careers_url="https://unsupported.example.invalid/openings",
    )

    with sqlite3.connect(database_path) as connection:
        requests = connection.execute(
            """
            SELECT request_id, detection_result, status
            FROM employer_review_requests
            ORDER BY created_at, request_id
            """
        ).fetchall()
    assert name_only.status == PENDING_REVIEW
    assert duplicate.review_request_id == name_only.review_request_id
    assert unsupported.status == UNSUPPORTED_SITE
    assert len(requests) == 2
    assert {row[1] for row in requests} == {
        PENDING_REVIEW,
        UNSUPPORTED_SITE,
    }
    assert {row[2] for row in requests} == {"PENDING"}


def test_assignments_remain_profile_specific(tmp_path: Path) -> None:
    database_path = tmp_path / "junior.sqlite3"
    first = create_test_profile(database_path, "profile_1111aaaa")
    second = create_test_profile(database_path, "profile_2222bbbb")

    result = resolve_employer_submission(
        database_path,
        profile_id=first.profile_id,
        careers_url="https://boards.greenhouse.io/example",
    )

    assert result.status == CREATED_SCAN_READY
    assert len(list_profile_employer_assignments(database_path, first.profile_id)) == 1
    assert list_profile_employer_assignments(database_path, second.profile_id) == []


def test_concurrent_submission_cannot_duplicate_scan_ready_employer(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    first = create_test_profile(database_path, "profile_1111aaaa")
    second = create_test_profile(database_path, "profile_2222bbbb")

    def resolve(profile_id: str):
        return resolve_employer_submission(
            database_path,
            profile_id=profile_id,
            careers_url="https://jobs.lever.co/concurrent-example",
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(resolve, (first.profile_id, second.profile_id)))

    with sqlite3.connect(database_path) as connection:
        employers = connection.execute(
            """
            SELECT employer_id
            FROM employer_sources
            WHERE source_identifier = 'concurrent-example'
            """
        ).fetchall()
    assert len(employers) == 1
    assert {result.status for result in results} <= {
        CREATED_SCAN_READY,
        MATCHED_EXISTING,
        ALREADY_ASSIGNED,
    }


def test_transaction_rolls_back_employer_when_assignment_fails(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    profile = create_test_profile(database_path)
    original_connect = sqlite3.connect

    # A database trigger simulates an assignment failure after the employer
    # insert, exercising the real transaction boundary without mocking storage.
    initialize_database(database_path)
    with original_connect(database_path) as connection:
        connection.execute(
            """
            CREATE TRIGGER fail_test_assignment
            BEFORE INSERT ON profile_company_associations
            BEGIN
                SELECT RAISE(ABORT, 'synthetic assignment failure');
            END
            """
        )

    with pytest.raises(sqlite3.IntegrityError):
        resolve_employer_submission(
            database_path,
            profile_id=profile.profile_id,
            careers_url="https://jobs.ashbyhq.com/rollback-example",
        )

    assert get_employer_source(database_path, "rollback-example") is None


def test_invalid_input_returns_safe_result(tmp_path: Path) -> None:
    database_path = tmp_path / "junior.sqlite3"
    profile = create_test_profile(database_path)

    empty = resolve_employer_submission(
        database_path,
        profile_id=profile.profile_id,
    )
    private = resolve_employer_submission(
        database_path,
        profile_id=profile.profile_id,
        careers_url="http://192.168.1.20/jobs",
    )

    assert empty.status == INVALID_INPUT
    assert private.status == INVALID_INPUT
