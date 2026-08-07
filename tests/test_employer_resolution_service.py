"""Verify safe company-name and careers-URL resolution with fictional data."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import pytest

from job_radar.employer_connection_service import get_employer_connection_health
from job_radar.employer_models import EmployerSource
from job_radar.employer_resolution_service import (
    ALREADY_ASSIGNED,
    AMBIGUOUS_MATCH,
    CREATED_SCAN_READY,
    DETECTED_SCAN_READY,
    DETECTED_SETUP_REQUIRED,
    DISCOVERY_TIMED_OUT,
    EXTERNAL_LOOKUP_DISABLED,
    EXTERNAL_LOOKUP_NO_SOURCE,
    EXTERNAL_LOOKUP_UNAVAILABLE,
    ExternalLookupAttempt,
    INVALID_INPUT,
    MATCHED_EXISTING,
    PENDING_REVIEW,
    _eightfold_detection_from_html,
    _talentbrew_detection_from_html,
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


def test_talentbrew_markers_create_reusable_job_search_detection() -> None:
    detection = _talentbrew_detection_from_html(
        source_url="https://careers.example.test/",
        careers_url="https://careers.example.test/",
        html='<script src="https://tbcdn.talentbrew.com/site.js"></script>',
    )

    assert detection is not None
    assert detection.source_type == "talentbrew"
    assert detection.source_config["source_url"] == (
        "https://careers.example.test/search-jobs"
    )
    assert detection.source_config["job_link_patterns"] == ["/job/"]


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
        (
            "https://workforcenow.adp.com/mascsr/default/mdf/recruitment/"
            "recruitment.html?cid=example-tenant"
            "&ccId=19000101_000001&lang=en_US",
            "adp",
            "example-tenant:19000101_000001",
            True,
        ),
        (
            "https://careers.nintendo.com/jobs/",
            "html",
            "careers.nintendo.com",
            True,
        ),
        (
            "https://www.valvesoftware.com/en",
            "html",
            "www.valvesoftware.com",
            True,
        ),
        (
            "https://careers.blizzard.com/global/en",
            "phenom",
            "careers.blizzard.com",
            True,
        ),
        (
            "https://example.wd5.myworkdayjobs.com/jobs",
            "workday",
            "example.wd5.myworkdayjobs.com:jobs",
            True,
        ),
        (
            "https://www.lockheedmartin.com/en-us/careers/index.html",
            "talentbrew",
            "talentbrew:www.lockheedmartinjobs.com",
            True,
        ),
        (
            "https://example.icims.com/jobs",
            "icims",
            "example.icims.com",
            True,
        ),
        (
            "https://recruiting.ultipro.com/TENANT/JobBoard/board-id/",
            "ukg",
            "recruiting.ultipro.com:tenant:board-id",
            True,
        ),
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


def test_custom_domain_eightfold_markers_build_a_scan_ready_source() -> None:
    detected = _eightfold_detection_from_html(
        source_url="https://jobs.example-systems.invalid/careers",
        careers_url="https://www.example-systems.invalid/careers",
        html=(
            '<link href="https://static.vscdn.net/example.css">'
            '<script>window._EF_GROUP_ID = "example.com";</script>'
        ),
    )

    assert detected is not None
    assert detected.source_type == "eightfold"
    assert detected.source_identifier == (
        "jobs.example-systems.invalid:example.com"
    )
    assert detected.source_config == {
        "source_url": "https://jobs.example-systems.invalid",
        "domain": "example.com",
        "careers_url": "https://www.example-systems.invalid/careers",
    }


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


def test_recognized_scan_ready_url_requires_confirmation_before_creation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "job_radar.employer_resolution_service.collect_jobs_for_company",
        lambda config: [object()],
    )
    database_path = tmp_path / "junior.sqlite3"
    profile = create_test_profile(database_path)

    detected = resolve_employer_submission(
        database_path,
        profile_id=profile.profile_id,
        company_name="Example Kitchens",
        careers_url="https://jobs.lever.co/example-kitchens",
    )
    assert detected.status == DETECTED_SCAN_READY
    assert detected.detected_source_label == "Lever"
    assert get_employer_source(database_path, "example-kitchens") is None
    assert list_profile_employer_assignments(
        database_path, profile.profile_id
    ) == []

    result = resolve_employer_submission(
        database_path,
        profile_id=profile.profile_id,
        company_name=detected.employer_name or "",
        careers_url=detected.careers_url or "",
        confirm_detected=True,
    )

    employer = get_employer_source(database_path, result.employer_id or "")
    assignments = list_profile_employer_assignments(
        database_path, profile.profile_id
    )
    assert result.status == CREATED_SCAN_READY
    assert employer is not None
    assert employer.source_type == "lever"
    assert employer.source_config["source_slug"] == "example-kitchens"
    health = get_employer_connection_health(
        database_path,
        employer.employer_id,
    )
    assert health.state == "success"
    assert health.job_count == 1
    assert health.tested_at is not None
    assert [item.employer_id for item in assignments] == [result.employer_id]


def test_complete_adp_url_requires_name_then_creates_scan_ready_employer(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "job_radar.employer_resolution_service.collect_jobs_for_company",
        lambda config: [object(), object()],
    )
    database_path = tmp_path / "junior.sqlite3"
    profile = create_test_profile(database_path)
    careers_url = (
        "https://workforcenow.adp.com/mascsr/default/mdf/recruitment/"
        "recruitment.html?cid=example-tenant"
        "&ccId=19000101_000001&lang=en_US"
    )

    detected = resolve_employer_submission(
        database_path,
        profile_id=profile.profile_id,
        careers_url=careers_url,
    )

    assert detected.status == DETECTED_SCAN_READY
    assert detected.detected_source_label == "ADP"
    assert detected.requires_company_name is True
    assert detected.employer_name == ""

    missing_name = resolve_employer_submission(
        database_path,
        profile_id=profile.profile_id,
        careers_url=careers_url,
        confirm_detected=True,
    )
    assert missing_name.status == INVALID_INPUT

    created = resolve_employer_submission(
        database_path,
        profile_id=profile.profile_id,
        company_name="Example Hospitality",
        careers_url=careers_url,
        confirm_detected=True,
    )

    employer = get_employer_source(database_path, created.employer_id or "")
    assert created.status == CREATED_SCAN_READY
    assert employer is not None
    assert employer.name == "Example Hospitality"
    assert employer.source_type == "adp"
    assert employer.source_config["source_url"] == careers_url
    assert employer.source_config["cid"] == "example-tenant"
    assert employer.source_config["ccId"] == "19000101_000001"
    assert employer.source_config["locale"] == "en_US"


def test_name_only_uses_review_but_unknown_url_waits_for_validation(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    profile = create_test_profile(database_path)

    name_only = resolve_employer_submission(
        database_path,
        profile_id=profile.profile_id,
        company_name="Example Catering",
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
    assert unsupported.status == DETECTED_SETUP_REQUIRED
    assert len(requests) == 1
    assert requests[0][1:] == (PENDING_REVIEW, "PENDING")
    assert list_profile_employer_assignments(database_path, profile.profile_id) == []


def test_assignments_remain_profile_specific(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "job_radar.employer_resolution_service.collect_jobs_for_company",
        lambda config: [object()],
    )
    database_path = tmp_path / "junior.sqlite3"
    first = create_test_profile(database_path, "profile_1111aaaa")
    second = create_test_profile(database_path, "profile_2222bbbb")

    result = resolve_employer_submission(
        database_path,
        profile_id=first.profile_id,
        careers_url="https://boards.greenhouse.io/example",
        confirm_detected=True,
    )

    assert result.status == CREATED_SCAN_READY
    assert len(list_profile_employer_assignments(database_path, first.profile_id)) == 1
    assert list_profile_employer_assignments(database_path, second.profile_id) == []


def test_recruitee_url_is_configured_without_administrator(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "job_radar.employer_resolution_service.collect_jobs_for_company",
        lambda config: [object()],
    )
    database_path = tmp_path / "junior.sqlite3"
    profile = create_test_profile(database_path)
    url = "https://example-bakery.recruitee.com/o/head-baker"

    detected = resolve_employer_submission(
        database_path,
        profile_id=profile.profile_id,
        careers_url=url,
    )
    created = resolve_employer_submission(
        database_path,
        profile_id=profile.profile_id,
        company_name="Example Bakery",
        careers_url=url,
        confirm_detected=True,
    )

    assert detected.status == DETECTED_SCAN_READY
    assert detected.detected_source_label == "Recruitee"
    assert created.status == CREATED_SCAN_READY
    employer = get_employer_source(database_path, "example-bakery")
    assert employer is not None
    assert employer.source_type == "recruitee"
    assert employer.source_config["source_url"] == (
        "https://example-bakery.recruitee.com/api/offers/"
    )


def test_icims_url_is_configured_with_the_icims_collector(
    tmp_path: Path,
    monkeypatch,
) -> None:
    attempted_configs: list[dict[str, object]] = []

    def collect(config):
        attempted_configs.append(config)
        return [object()]

    monkeypatch.setattr(
        "job_radar.employer_resolution_service.collect_jobs_for_company",
        collect,
    )
    database_path = tmp_path / "junior.sqlite3"
    profile = create_test_profile(database_path)
    url = "https://careers-example.icims.com/jobs/"

    detected = resolve_employer_submission(
        database_path,
        profile_id=profile.profile_id,
        careers_url=url,
    )
    created = resolve_employer_submission(
        database_path,
        profile_id=profile.profile_id,
        company_name="Example Kitchens",
        careers_url=url,
        confirm_detected=True,
    )

    assert detected.status == DETECTED_SCAN_READY
    assert detected.detected_source_label == "iCIMS"
    assert created.status == CREATED_SCAN_READY
    assert attempted_configs[0]["source_type"] == "icims"
    assert attempted_configs[0]["source_url"] == url.rstrip("/")
    employer = get_employer_source(database_path, "example-kitchens")
    assert employer is not None
    assert employer.source_type == "icims"
    assert employer.source_config["source_url"] == url.rstrip("/")


def test_ukg_url_is_configured_with_the_ukg_collector(
    tmp_path: Path,
    monkeypatch,
) -> None:
    attempted_configs: list[dict[str, object]] = []

    def collect(config):
        attempted_configs.append(config)
        return [object()]

    monkeypatch.setattr(
        "job_radar.employer_resolution_service.collect_jobs_for_company",
        collect,
    )
    database_path = tmp_path / "junior.sqlite3"
    profile = create_test_profile(database_path)
    url = (
        "https://recruiting.ultipro.com/TENANT/JobBoard/"
        "d1569a66-00f5-4887-b2a9-048c2d9169a7/?q="
    )

    detected = resolve_employer_submission(
        database_path,
        profile_id=profile.profile_id,
        careers_url=url,
    )
    created = resolve_employer_submission(
        database_path,
        profile_id=profile.profile_id,
        company_name="Synthetic Manufacturer",
        careers_url=url,
        confirm_detected=True,
    )

    assert detected.status == DETECTED_SCAN_READY
    assert detected.detected_source_label == "UKG Pro Recruiting"
    assert created.status == CREATED_SCAN_READY
    assert attempted_configs[0]["source_type"] == "ukg"
    assert attempted_configs[0]["source_url"] == (
        "https://recruiting.ultipro.com/TENANT/JobBoard/"
        "d1569a66-00f5-4887-b2a9-048c2d9169a7/"
    )
    employer = get_employer_source(
        database_path,
        "synthetic-manufacturer",
    )
    assert employer is not None
    assert employer.source_type == "ukg"


def test_unknown_site_must_pass_generic_collector_before_being_added(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    profile = create_test_profile(database_path)
    url = "https://careers.example.invalid/jobs"

    detected = resolve_employer_submission(
        database_path,
        profile_id=profile.profile_id,
        careers_url=url,
    )
    assert detected.status == DETECTED_SETUP_REQUIRED

    monkeypatch.setattr(
        "job_radar.employer_resolution_service._discover_branded_sources",
        lambda url: [],
    )
    monkeypatch.setattr(
        "job_radar.employer_resolution_service.collect_jobs_for_company",
        lambda config: [object()],
    )
    created = resolve_employer_submission(
        database_path,
        profile_id=profile.profile_id,
        company_name="Example Kitchens",
        careers_url=url,
        confirm_detected=True,
    )

    assert created.status == CREATED_SCAN_READY
    employer = get_employer_source(database_path, "example-kitchens")
    assert employer is not None
    assert employer.source_type == "html"
    assert employer.enabled is True


def test_google_careers_url_uses_first_class_collector() -> None:
    detected = detect_employer_source(
        "https://www.google.com/about/careers/applications/jobs/results"
    )

    assert detected.source_type == "google_careers"
    assert detected.source_identifier == "google-careers"
    assert detected.scan_ready is True
    assert detected.source_config["display_name"] == "Google"


def test_google_careers_url_can_be_confirmed_and_added(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    profile = create_test_profile(database_path)
    careers_url = "https://www.google.com/about/careers/applications/jobs/results"
    monkeypatch.setattr(
        "job_radar.employer_resolution_service.collect_jobs_for_company",
        lambda config: [object()],
    )

    detected = resolve_employer_submission(
        database_path,
        profile_id=profile.profile_id,
        careers_url=careers_url,
    )
    created = resolve_employer_submission(
        database_path,
        profile_id=profile.profile_id,
        careers_url=careers_url,
        confirm_detected=True,
    )

    assert detected.status == DETECTED_SCAN_READY
    assert detected.employer_name == "Google"
    assert detected.detected_source_label == "Google Careers"
    assert created.status == CREATED_SCAN_READY
    employer = get_employer_source(database_path, "google")
    assert employer is not None
    assert employer.source_type == "google_careers"
    assert list_profile_employer_assignments(
        database_path, profile.profile_id
    )[0].employer_id == "google"


def test_unknown_site_failure_directs_user_to_safe_support(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    profile = create_test_profile(database_path)
    monkeypatch.setattr(
        "job_radar.employer_resolution_service._discover_branded_sources",
        lambda url: [],
    )
    monkeypatch.setattr(
        "job_radar.employer_resolution_service._discover_public_job_sources",
        lambda **kwargs: ExternalLookupAttempt(state="no_match"),
    )
    monkeypatch.setattr(
        "job_radar.employer_resolution_service.collect_jobs_for_company",
        lambda config: [],
    )

    result = resolve_employer_submission(
        database_path,
        profile_id=profile.profile_id,
        company_name="Example Kitchens",
        careers_url="https://careers.example.invalid/jobs",
        confirm_detected=True,
        allow_external_lookup=True,
    )

    assert result.status == EXTERNAL_LOOKUP_NO_SOURCE
    assert "claytonmgraves@outlook.com" in result.message
    assert "Do not send passwords" in result.message
    assert list_profile_employer_assignments(database_path, profile.profile_id) == []


def test_unknown_site_discovery_has_an_overall_timeout_and_writes_nothing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    profile = create_test_profile(database_path)
    release_worker = Event()

    def slow_discovery(**kwargs):
        release_worker.wait(timeout=1)
        return None

    monkeypatch.setattr(
        "job_radar.employer_resolution_service._COMPANY_DISCOVERY_TIMEOUT_SECONDS",
        0.01,
    )
    monkeypatch.setattr(
        "job_radar.employer_resolution_service._resolve_generic_source",
        slow_discovery,
    )
    try:
        result = resolve_employer_submission(
            database_path,
            profile_id=profile.profile_id,
            company_name="Example Kitchens",
            careers_url="https://careers.example.invalid/jobs",
            confirm_detected=True,
        )
    finally:
        release_worker.set()

    assert result.status == DISCOVERY_TIMED_OUT
    assert "after two minutes" in result.message
    assert "did not add" in result.message
    assert get_employer_source(database_path, "example-kitchens") is None
    assert list_profile_employer_assignments(database_path, profile.profile_id) == []


def test_blocked_landing_page_can_find_and_verify_separate_official_job_site(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    profile = create_test_profile(database_path)
    landing_url = "https://example-kitchens.invalid/careers"
    job_url = "https://jobs.example-kitchens.invalid/search-jobs"

    class SearchResponse:
        text = (
            '<a href="/l/?uddg=https%3A%2F%2Funrelated.invalid%2Fjobs">Bad</a>'
            '<a href="/l/?uddg=https%3A%2F%2Fjobs.example-kitchens.invalid'
            '%2Fsearch-jobs">Official careers</a>'
        )

    monkeypatch.setattr(
        "job_radar.employer_resolution_service._discover_branded_sources",
        lambda url: [],
    )
    monkeypatch.setattr(
        "job_radar.employer_resolution_service.get_response",
        lambda *args, **kwargs: SearchResponse(),
    )

    attempted_sources: list[str] = []

    def collect(config):
        source_url = str(config["source_url"])
        attempted_sources.append(source_url)
        return [object()] if source_url == job_url else []

    monkeypatch.setattr(
        "job_radar.employer_resolution_service.collect_jobs_for_company",
        collect,
    )

    created = resolve_employer_submission(
        database_path,
        profile_id=profile.profile_id,
        company_name="Example Kitchens",
        careers_url=landing_url,
        confirm_detected=True,
        allow_external_lookup=True,
    )

    assert created.status == CREATED_SCAN_READY
    employer = get_employer_source(database_path, "example-kitchens")
    assert employer is not None
    assert employer.source_config["source_url"] == job_url
    assert "https://unrelated.invalid/jobs" not in attempted_sources
    with sqlite3.connect(database_path) as connection:
        stored_employers = connection.execute(
            "SELECT employer_id FROM employer_sources"
        ).fetchall()
        review_requests = connection.execute(
            "SELECT request_id FROM employer_review_requests"
        ).fetchall()
    assert stored_employers == [("example-kitchens",)]
    assert review_requests == []


def test_unknown_site_requires_consent_and_discloses_complete_lookup_payload(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    profile = create_test_profile(database_path)
    external_lookup_called = False

    monkeypatch.setattr(
        "job_radar.employer_resolution_service._discover_branded_sources",
        lambda url: [],
    )
    monkeypatch.setattr(
        "job_radar.employer_resolution_service.collect_jobs_for_company",
        lambda config: [],
    )

    def discover(**kwargs):
        nonlocal external_lookup_called
        external_lookup_called = True
        return []

    monkeypatch.setattr(
        "job_radar.employer_resolution_service._discover_public_job_sources",
        discover,
    )

    result = resolve_employer_submission(
        database_path,
        profile_id=profile.profile_id,
        company_name="Example Kitchens",
        careers_url=(
            "https://careers.example.invalid/jobs"
            "?tenant=private-path-value"
        ),
        confirm_detected=True,
    )

    assert result.status == EXTERNAL_LOOKUP_DISABLED
    assert result.external_lookup_provider == "Bing"
    assert result.external_lookup_fields == (
        (
            "q",
            "Example Kitchens careers.example.invalid official careers jobs",
        ),
        ("format", "rss"),
    )
    assert "private-path-value" not in str(result.external_lookup_fields)
    assert external_lookup_called is False
    assert list_profile_employer_assignments(database_path, profile.profile_id) == []


@pytest.mark.parametrize(
    ("lookup_attempt", "expected_status", "expected_message"),
    [
        (
            ExternalLookupAttempt(state="unavailable"),
            EXTERNAL_LOOKUP_UNAVAILABLE,
            "Bing could not be reached",
        ),
        (
            ExternalLookupAttempt(state="no_match"),
            EXTERNAL_LOOKUP_NO_SOURCE,
            "did not find a job source it could independently verify",
        ),
    ],
)
def test_enabled_external_lookup_reports_safe_distinct_failure_outcomes(
    tmp_path: Path,
    monkeypatch,
    lookup_attempt: ExternalLookupAttempt,
    expected_status: str,
    expected_message: str,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    profile = create_test_profile(database_path)
    monkeypatch.setattr(
        "job_radar.employer_resolution_service._discover_branded_sources",
        lambda url: [],
    )
    monkeypatch.setattr(
        "job_radar.employer_resolution_service.collect_jobs_for_company",
        lambda config: [],
    )
    monkeypatch.setattr(
        "job_radar.employer_resolution_service._discover_public_job_sources",
        lambda **kwargs: lookup_attempt,
    )

    result = resolve_employer_submission(
        database_path,
        profile_id=profile.profile_id,
        company_name="Example Kitchens",
        careers_url="https://careers.example.invalid/jobs",
        confirm_detected=True,
        allow_external_lookup=True,
    )

    assert result.status == expected_status
    assert expected_message in result.message
    assert result.external_lookup_provider == "Bing"
    assert list_profile_employer_assignments(database_path, profile.profile_id) == []


def test_concurrent_submission_cannot_duplicate_scan_ready_employer(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "job_radar.employer_resolution_service.collect_jobs_for_company",
        lambda config: [object()],
    )
    database_path = tmp_path / "junior.sqlite3"
    first = create_test_profile(database_path, "profile_1111aaaa")
    second = create_test_profile(database_path, "profile_2222bbbb")

    def resolve(profile_id: str):
        return resolve_employer_submission(
            database_path,
            profile_id=profile_id,
            careers_url="https://jobs.lever.co/concurrent-example",
            confirm_detected=True,
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
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "job_radar.employer_resolution_service.collect_jobs_for_company",
        lambda config: [object()],
    )
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
            confirm_detected=True,
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
