"""Verify safe company-name and careers-URL resolution with fictional data."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from threading import Event

import pytest
import requests

from job_radar.employer_connection_service import get_employer_connection_health
from job_radar.employer_models import EmployerSource
from job_radar.employer_resolution_service import (
    ALREADY_ASSIGNED,
    AMBIGUOUS_MATCH,
    CREATED_SCAN_READY,
    DetectedEmployerSource,
    EmployerResolutionResult,
    DETECTED_SCAN_READY,
    DETECTED_SETUP_REQUIRED,
    DISCOVERY_TIMED_OUT,
    INVALID_INPUT,
    MATCHED_EXISTING,
    NO_CURRENT_JOBS,
    UNSUPPORTED_SITE,
    _eightfold_detection_from_html,
    _discover_branded_sources,
    _discover_sources_from_document,
    _discovery_priority,
    _domain_slug_ats_candidates,
    _document_reports_expired_opening,
    _first_working_source,
    _resolve_generic_source,
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
from job_radar.profile_models import ManagedProfile, ProfilePreferences
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


def test_talentbrew_detection_preserves_employer_scope_without_geolocation() -> None:
    detection = _talentbrew_detection_from_html(
        source_url=(
            "https://jobs.example.test/search-jobs?orgIds=391-28648&"
            "ascf=Industrial%20Light%20%26%20Magic&glat=34.05&glon=-118.24&p=3"
        ),
        careers_url="https://example.test/careers",
        html='<script src="https://tbcdn.talentbrew.com/site.js"></script>',
    )

    assert detection is not None
    assert detection.source_config["source_url"] == (
        "https://jobs.example.test/search-jobs?"
        "orgIds=391-28648&ascf=Industrial+Light+%26+Magic"
    )
    assert "orgids=391-28648" in detection.source_identifier
    assert "glat" not in detection.source_identifier


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
            "https://example.hrmdirect.com/employment/job-openings.php?search=true",
            "html",
            "hrmdirect:example.hrmdirect.com",
            True,
        ),
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
        (
            "https://jobs.smartrecruiters.com/Example",
            "smartrecruiters",
            "example",
            True,
        ),
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


def test_layered_discovery_follows_official_pages_to_supported_platform(
    monkeypatch,
) -> None:
    pages = {
        "https://example.invalid/": '<a href="/about/careers">Careers</a>',
        "https://example.invalid/about/careers": (
            '<a href="https://jobs.smartrecruiters.com/ExampleCo">Open jobs</a>'
        ),
    }
    requested: list[str] = []

    class Response:
        def __init__(self, url: str, text: str) -> None:
            self.url = url
            self.text = text

    def fetch(url: str, **kwargs):
        requested.append(url)
        return Response(url, pages.get(url, ""))

    monkeypatch.setattr(
        "job_radar.employer_resolution_service.get_response",
        fetch,
    )

    discoveries = _discover_branded_sources("https://example.invalid/")

    assert any(
        item.source_type == "smartrecruiters"
        and item.source_identifier == "exampleco"
        for item in discoveries
    )
    assert len(requested) == len(set(requested))


def test_layered_discovery_inspects_explicit_external_careers_handoff(
    monkeypatch,
) -> None:
    official_url = "https://example.invalid/careers"
    filtered_url = (
        "https://jobs.parent.invalid/search-jobs?division=Example+Studio"
    )
    pages = {
        official_url: f'<a href="{filtered_url}">Browse job opportunities</a>',
        filtered_url: '<script src="https://tbcdn.talentbrew.com/site.js"></script>',
    }
    requested: list[str] = []

    class Response:
        def __init__(self, url: str, text: str) -> None:
            self.url = url
            self.text = text

    def fetch(url: str, **kwargs):
        requested.append(url)
        return Response(url, pages.get(url, ""))

    monkeypatch.setattr(
        "job_radar.employer_resolution_service.get_response",
        fetch,
    )

    discoveries = _discover_branded_sources(official_url)

    talentbrew = next(item for item in discoveries if item.source_type == "talentbrew")
    assert talentbrew.source_config["source_url"] == filtered_url
    assert filtered_url in requested


def test_layered_discovery_does_not_follow_social_job_links(monkeypatch) -> None:
    official_url = "https://example.invalid/careers"
    social_url = "https://www.linkedin.com/company/example/jobs/"
    requested: list[str] = []

    class Response:
        def __init__(self, url: str, text: str) -> None:
            self.url = url
            self.text = text

    def fetch(url: str, **kwargs):
        requested.append(url)
        return Response(url, f'<a href="{social_url}">Jobs</a>')

    monkeypatch.setattr(
        "job_radar.employer_resolution_service.get_response",
        fetch,
    )

    _discover_branded_sources(official_url)

    assert social_url not in requested


def test_layered_discovery_inspects_lazy_loaded_careers_module(monkeypatch) -> None:
    official_url = "https://example.invalid/careers"
    app_url = "https://example.invalid/assets/app.js"
    careers_module = "https://example.invalid/assets/CareersView.123.js"
    adp_url = (
        "https://workforcenow.adp.com/mascsr/default/mdf/recruitment/"
        "recruitment.html?cid=11111111-2222-3333-4444-555555555555&"
        "ccId=19000101_000001"
    )
    pages = {
        official_url: f'<script type="module" src="{app_url}"></script>',
        app_url: 'const route = "./CareersView.123.js";',
        careers_module: f'const openings = "{adp_url}";',
    }

    class Response:
        def __init__(self, url: str) -> None:
            self.url = url
            self.text = pages.get(url, "")

    monkeypatch.setattr(
        "job_radar.employer_resolution_service.get_response",
        lambda url, **kwargs: Response(url),
    )

    discoveries = _discover_branded_sources(official_url)

    assert any(item.source_type == "adp" for item in discoveries)


def test_blocked_official_page_can_use_maintained_public_handoff(monkeypatch) -> None:
    def blocked(*args, **kwargs):
        raise requests.RequestException("blocked")

    monkeypatch.setattr(
        "job_radar.employer_resolution_service.get_response",
        blocked,
    )

    discoveries = _discover_branded_sources(
        "https://www.sony.com/en_us/SCA/careers/main.html"
    )

    source = next(item for item in discoveries if item.source_type == "workday")
    assert source.source_config["source_url"] == (
        "https://sonyglobal.wd1.myworkdayjobs.com/wday/cxs/"
        "sonyglobal/SonyGlobalCareers/jobs"
    )


def test_explicit_empty_careers_page_is_not_reported_as_unsupported(
    monkeypatch,
) -> None:
    empty = DetectedEmployerSource(
        source_type=None,
        source_identifier=None,
        source_config={},
        scan_ready=False,
        evidence=("explicit no current openings",),
    )
    monkeypatch.setattr(
        "job_radar.employer_resolution_service._discover_branded_sources",
        lambda *args, **kwargs: [empty],
    )
    monkeypatch.setattr(
        "job_radar.employer_resolution_service.collect_jobs_for_company",
        lambda config: [],
    )

    result = _resolve_generic_source(
        display_name="Example Research Center",
        normalized_url="https://example.invalid/careers",
        discovery_observer=None,
    )

    assert result.status == NO_CURRENT_JOBS
    assert "requires at least one actual job" in result.message


def test_expired_public_job_deadline_is_not_treated_as_an_active_job() -> None:
    assert _document_reports_expired_opening(
        "End date for tendering position: 30 June 2026",
        today=date(2026, 8, 11),
    )
    assert not _document_reports_expired_opening(
        "Application deadline: September 30, 2026",
        today=date(2026, 8, 11),
    )


def test_layered_discovery_builds_html_source_from_repeated_job_links(
    monkeypatch,
) -> None:
    url = "https://example.invalid/careers/positions/"
    html = (
        '<a href="/careers/positions/software-engineer-1001/">Software Engineer</a>'
        '<a href="/careers/positions/platform-engineer-1002/">Platform Engineer</a>'
    )

    class Response:
        def __init__(self) -> None:
            self.url = url
            self.text = html

    monkeypatch.setattr(
        "job_radar.employer_resolution_service.get_response",
        lambda *args, **kwargs: Response(),
    )

    discoveries = _discover_branded_sources(url)

    source = next(item for item in discoveries if item.source_type == "html")
    assert source.source_config["source_url"] == url
    assert source.source_config["job_link_patterns"] == ["/careers/positions/"]


def test_complete_embedded_feed_outranks_landing_page_teaser(monkeypatch) -> None:
    landing_url = "https://careers.example.invalid"
    jobs_url = f"{landing_url}/jobs"
    pages = {
        landing_url: (
            f'<a href="{jobs_url}">All jobs</a>'
            '<a href="/jobs/1">One</a><a href="/jobs/2">Two</a>'
        ),
        jobs_url: "<script>const jobsData = [{\"id\": 1}];</script>",
    }

    class Response:
        def __init__(self, url: str) -> None:
            self.url = url
            self.text = pages.get(url, "")

    monkeypatch.setattr(
        "job_radar.employer_resolution_service.get_response",
        lambda url, **kwargs: Response(url),
    )

    discoveries = _discover_branded_sources(landing_url)
    discoveries.sort(key=_discovery_priority)

    assert discoveries[0].source_config["source_url"] == jobs_url
    assert discoveries[0].evidence == ("embedded public job data",)


def test_detected_platform_outranks_secondary_html_category() -> None:
    careers_url = "https://jobs.example.invalid/"
    category = DetectedEmployerSource(
        source_type="html",
        source_identifier="html:category",
        source_config={
            "source_url": f"{careers_url}category/engineering",
            "careers_url": careers_url,
        },
        scan_ready=True,
    )
    platform = DetectedEmployerSource(
        source_type="talentbrew",
        source_identifier="talentbrew:example",
        source_config={
            "source_url": f"{careers_url}search-jobs",
            "careers_url": careers_url,
        },
        scan_ready=True,
    )

    assert _discovery_priority(platform) < _discovery_priority(category)


def test_domain_probe_includes_safe_company_suffix_variant() -> None:
    candidates = _domain_slug_ats_candidates("https://www.example-space.com/careers")

    greenhouse_slugs = {
        item.source_config.get("source_slug")
        for item in candidates
        if item.source_type == "greenhouse"
    }
    assert greenhouse_slugs == {"example-space", "example"}


def test_source_validation_uses_normal_collector_depth(monkeypatch) -> None:
    captured: list[dict[str, object]] = []

    def collect(config):
        captured.append(config)
        return [object(), object()]

    monkeypatch.setattr(
        "job_radar.employer_resolution_service.collect_jobs_for_company",
        collect,
    )
    discovery = DetectedEmployerSource(
        source_type="greenhouse",
        source_identifier="example",
        source_config={"source_slug": "example"},
        scan_ready=True,
    )

    result = _first_working_source([discovery], display_name="Example")

    assert result == (discovery, 2)
    assert captured[0]["connection_test"] is True
    assert "max_pages" not in captured[0]
    assert "page_size" not in captured[0]


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


def test_url_submission_never_uses_similar_catalog_name(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    profile = create_test_profile(database_path)
    add_catalog_employer(database_path, name="VAST Data")
    monkeypatch.setattr(
        "job_radar.employer_resolution_service._resolve_generic_source",
        lambda **_kwargs: EmployerResolutionResult(
            status=UNSUPPORTED_SITE,
            message="unsupported",
        ),
    )

    result = resolve_employer_submission(
        database_path,
        profile_id=profile.profile_id,
        company_name="Vast",
        careers_url="https://www.vastspace.com/careers",
        confirm_detected=True,
    )

    assert result.status == UNSUPPORTED_SITE
    assert result.possible_employers == ()


def test_official_subsidiary_page_derives_scoped_parent_job_search() -> None:
    discoveries = _discover_sources_from_document(
        source_url="https://subsidiary.example/careers/",
        careers_url="https://subsidiary.example/careers/",
        html=(
            "<p>Located in beautiful Fort Collins, CO.</p>"
            '<a href="https://jobs.example-parent.com/">Careers</a>'
        ),
    )

    scoped = next(
        item
        for item in discoveries
        if "official location-scoped recruiting handoff" in item.evidence
    )
    assert scoped.source_type == "html"
    assert scoped.source_config["source_url"] == (
        "https://jobs.example-parent.com/search/"
        "?q=&locationsearch=Fort+Collins%2C+CO"
    )
    assert scoped.source_config["required_job_url_terms"] == [
        "/job/fort-collins-"
    ]


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


def test_name_only_without_lookup_saves_no_review_request(
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
    assert name_only.status == UNSUPPORTED_SITE
    assert unsupported.status == DETECTED_SETUP_REQUIRED
    assert requests == []
    assert list_profile_employer_assignments(database_path, profile.profile_id) == []


def test_name_only_never_uses_removed_external_lookup(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    profile = create_test_profile(database_path)
    result = resolve_employer_submission(
        database_path,
        profile_id=profile.profile_id,
        company_name="Example Catering",
    )

    assert result.status == UNSUPPORTED_SITE
    assert "official company webpage" in result.message
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT request_id FROM employer_review_requests"
        ).fetchall() == []


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
        lambda url, **kwargs: [],
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


def test_walmart_url_uses_profile_scope_and_adds_first_class_collector(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    profile = ManagedProfile(
        profile_id="profile_1234abcd",
        display_name="Test User",
        preferences=ProfilePreferences(
            target_roles=("Platform Engineer",),
            preferred_locations=("Colorado", "Remote"),
        ),
    )
    create_profile(database_path, profile)
    observed = {}

    def collect(config):
        observed.update(config)
        return [object()]

    monkeypatch.setattr(
        "job_radar.employer_resolution_service.collect_jobs_for_company",
        collect,
    )

    detected = resolve_employer_submission(
        database_path,
        profile_id=profile.profile_id,
        careers_url="https://careers.walmart.com/",
    )
    created = resolve_employer_submission(
        database_path,
        profile_id=profile.profile_id,
        careers_url="https://careers.walmart.com/",
        confirm_detected=True,
    )

    assert detected.status == DETECTED_SCAN_READY
    assert detected.detected_source_label == "Walmart Careers"
    assert created.status == CREATED_SCAN_READY
    assert observed["walmart_target_roles"] == ["Platform Engineer"]
    assert observed["walmart_locations"] == ["Colorado", "Remote"]
    employer = get_employer_source(database_path, "walmart")
    assert employer is not None
    assert employer.source_type == "walmart"
    assert "walmart_target_roles" not in employer.source_config


def test_unknown_site_failure_directs_user_to_safe_support(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    profile = create_test_profile(database_path)
    monkeypatch.setattr(
        "job_radar.employer_resolution_service._discover_branded_sources",
        lambda url, **kwargs: [],
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
    )

    assert result.status == UNSUPPORTED_SITE
    assert "claytonmgraves@outlook.com" in result.message
    assert "Do not send passwords" in result.message
    assert list_profile_employer_assignments(database_path, profile.profile_id) == []


def test_generic_discovery_accepts_profile_scope_without_changing_page_traversal(
    monkeypatch,
) -> None:
    observed = {}
    monkeypatch.setattr(
        "job_radar.employer_resolution_service._discover_branded_sources",
        lambda url, **kwargs: [],
    )

    def first_working(discoveries, **kwargs):
        observed.update(kwargs)
        return None

    monkeypatch.setattr(
        "job_radar.employer_resolution_service._first_working_source",
        first_working,
    )

    result = _resolve_generic_source(
        display_name="Example Kitchens",
        normalized_url="https://example.invalid/careers",
        discovery_observer=None,
        walmart_scope={"walmart_target_roles": ["Platform Engineer"]},
    )

    assert result.status == UNSUPPORTED_SITE
    assert observed["walmart_scope"] == {
        "walmart_target_roles": ["Platform Engineer"]
    }


def test_blocked_official_page_recovers_matching_public_ashby_board(
    monkeypatch,
) -> None:
    attempted: list[tuple[str, str | None]] = []
    monkeypatch.setattr(
        "job_radar.employer_resolution_service._discover_branded_sources",
        lambda url, **kwargs: [],
    )

    def collect(config):
        attempted.append((config["source_type"], config.get("source_slug")))
        if config["source_type"] == "ashby" and config["source_slug"] == "vultr":
            return [object(), object()]
        return []

    monkeypatch.setattr(
        "job_radar.employer_resolution_service.collect_jobs_for_company",
        collect,
    )

    result = _resolve_generic_source(
        display_name="Vultr",
        normalized_url="https://www.vultr.com/company/careers/",
        discovery_observer=None,
    )

    assert isinstance(result, tuple)
    source, job_count = result
    assert source.source_type == "ashby"
    assert source.source_identifier == "vultr"
    assert source.source_config["careers_url"] == (
        "https://www.vultr.com/company/careers/"
    )
    assert job_count == 2
    assert attempted == [("html", None), ("ashby", "vultr")]


def test_domain_ats_recovery_rejects_candidates_without_actual_jobs(
    monkeypatch,
) -> None:
    attempted: list[str] = []
    monkeypatch.setattr(
        "job_radar.employer_resolution_service._discover_branded_sources",
        lambda url, **kwargs: [],
    )

    def collect(config):
        attempted.append(config["source_type"])
        return []

    monkeypatch.setattr(
        "job_radar.employer_resolution_service.collect_jobs_for_company",
        collect,
    )

    result = _resolve_generic_source(
        display_name="No Openings Example",
        normalized_url="https://www.no-openings-example.com/careers/",
        discovery_observer=None,
    )

    assert result.status == UNSUPPORTED_SITE
    assert attempted == ["html", "ashby", "greenhouse", "lever", "html"]


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

    monkeypatch.setattr(
        "job_radar.employer_resolution_service._discover_branded_sources",
        lambda url, **kwargs: [
            DetectedEmployerSource(
                source_type="html",
                source_identifier="jobs.example-kitchens.invalid",
                source_config={
                    "source_url": job_url,
                    "careers_url": landing_url,
                },
                scan_ready=True,
            )
        ],
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
    )

    assert created.status == CREATED_SCAN_READY
    employer = get_employer_source(database_path, "example-kitchens")
    assert employer is not None
    assert employer.source_config["source_url"] == job_url
    assert attempted_sources[0] == job_url
    with sqlite3.connect(database_path) as connection:
        stored_employers = connection.execute(
            "SELECT employer_id FROM employer_sources"
        ).fetchall()
        review_requests = connection.execute(
            "SELECT request_id FROM employer_review_requests"
        ).fetchall()
    assert stored_employers == [("example-kitchens",)]
    assert review_requests == []


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
