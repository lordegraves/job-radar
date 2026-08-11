import job_radar.scan_service as scan_service
from job_radar.models import JobPosting


def test_rate_sensitive_sources_use_dedicated_bounded_pools() -> None:
    assert scan_service._collection_pool_name("workday") == "workday"
    assert scan_service._collection_pool_name("eightfold") == "eightfold"
    assert scan_service._collection_pool_name("greenhouse") == "general"
    assert scan_service._WORKDAY_COLLECTION_WORKERS == 2
    assert scan_service._EIGHTFOLD_COLLECTION_WORKERS == 1
    assert scan_service._GENERAL_COLLECTION_WORKERS == 2


def test_collection_records_actual_worker_start(monkeypatch) -> None:
    config: dict[str, object] = {}

    monkeypatch.setattr(
        scan_service,
        "collect_jobs_for_company",
        lambda _config: [],
    )

    assert scan_service._collect_company_with_start_progress(config) == []
    assert isinstance(
        config[scan_service._COLLECTOR_STARTED_AT_CONFIG_KEY],
        float,
    )


def test_overlapping_parent_board_prefers_scoped_company() -> None:
    def posting(company_key: str, company_name: str) -> JobPosting:
        return JobPosting(
            company_key=company_key,
            company_name=company_name,
            source_type="talentbrew",
            source_url="https://jobs.example.com/job/shared-role/123",
            source_job_id="123",
            title="Shared Role",
            location="Remote",
            description="Complete role description. " * 20,
        )

    result = scan_service._dedupe_cross_company_postings(
        {
            1: [posting("parent", "Parent Company")],
            2: [posting("studio", "Studio")],
        },
        [
            {
                "company_key": "parent",
                "source_url": "https://jobs.example.com/search-jobs",
            },
            {
                "company_key": "studio",
                "source_url": (
                    "https://jobs.example.com/search-jobs?division=Studio"
                ),
            },
        ],
    )

    assert len(result) == 1
    assert result[0].company_key == "studio"
