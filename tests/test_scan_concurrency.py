import job_radar.scan_service as scan_service


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
