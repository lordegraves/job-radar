"""Tests company-setting views, filters, summaries, and safe editing readiness."""

from pathlib import Path

from job_radar.company_config_service import (
    build_company_config_views,
    build_company_config_write_strategy,
    build_company_source_summaries,
    filter_company_config_views,
    get_company_config_view,
)


def write_companies_file(companies_file: Path) -> None:
    companies_file.write_text(
        """
companies:
  - company_key: enabled_ai
    name: Enabled AI
    source_type: greenhouse
    source_slug: enabledai
    enabled: true
    notes: Strong target.
  - company_key: disabled_lab
    name: Disabled Lab
    source_type: workday
    source_url: https://example.com/workday/jobs
    source_base_url: https://example.com/workday
    enabled: false
  - company_key: nasa_usajobs
    name: NASA
    source_type: usajobs
    enabled: true
    query_params:
      Organization: NN
""",
        encoding="utf-8",
    )


def test_build_company_config_views_includes_source_details_and_config_items(tmp_path: Path) -> None:
    companies_file = tmp_path / "target-companies.yaml"
    write_companies_file(companies_file)

    companies = build_company_config_views(str(companies_file))

    assert [company.company_key for company in companies] == [
        "enabled_ai",
        "nasa_usajobs",
        "disabled_lab",
    ]
    assert companies[0].name == "Enabled AI"
    assert companies[0].source_type == "greenhouse"
    assert companies[0].enabled is True
    assert companies[0].source_detail == "source_slug: enabledai"
    assert companies[0].notes == "Strong target."
    assert ("company_key", "enabled_ai") in companies[0].config_items
    assert "query_params: Organization=NN" in companies[1].source_detail
    assert "source_url: https://example.com/workday/jobs" in companies[2].source_detail


def test_get_company_config_view_returns_matching_company(tmp_path: Path) -> None:
    companies_file = tmp_path / "target-companies.yaml"
    write_companies_file(companies_file)

    company = get_company_config_view(str(companies_file), "nasa_usajobs")
    missing_company = get_company_config_view(str(companies_file), "missing")

    assert company is not None
    assert company.name == "NASA"
    assert company.source_type == "usajobs"
    assert missing_company is None


def test_filter_company_config_views_filters_by_status_source_and_search(tmp_path: Path) -> None:
    companies_file = tmp_path / "target-companies.yaml"
    write_companies_file(companies_file)
    companies = build_company_config_views(str(companies_file))

    enabled_companies = filter_company_config_views(
        companies,
        selected_status="enabled",
        selected_source_type="",
        search_query="",
    )
    disabled_companies = filter_company_config_views(
        companies,
        selected_status="disabled",
        selected_source_type="",
        search_query="",
    )
    source_companies = filter_company_config_views(
        companies,
        selected_status="",
        selected_source_type="greenhouse",
        search_query="",
    )
    searched_companies = filter_company_config_views(
        companies,
        selected_status="",
        selected_source_type="",
        search_query="organization",
    )
    combined_companies = filter_company_config_views(
        companies,
        selected_status="enabled",
        selected_source_type="usajobs",
        search_query="nn",
    )

    assert [company.company_key for company in enabled_companies] == [
        "enabled_ai",
        "nasa_usajobs",
    ]
    assert [company.company_key for company in disabled_companies] == [
        "disabled_lab",
    ]
    assert [company.company_key for company in source_companies] == [
        "enabled_ai",
    ]
    assert [company.company_key for company in searched_companies] == [
        "nasa_usajobs",
    ]
    assert [company.company_key for company in combined_companies] == [
        "nasa_usajobs",
    ]


def test_build_company_source_summaries_counts_enabled_disabled_and_total(tmp_path: Path) -> None:
    companies_file = tmp_path / "target-companies.yaml"
    write_companies_file(companies_file)
    companies = build_company_config_views(str(companies_file))

    summaries = build_company_source_summaries(companies)

    assert [
        (summary.source_type, summary.enabled, summary.disabled, summary.total)
        for summary in summaries
    ] == [
        ("greenhouse", 1, 0, 1),
        ("usajobs", 1, 0, 1),
        ("workday", 0, 1, 1),
    ]


def test_build_company_config_write_strategy_blocks_writes_without_ruamel(monkeypatch) -> None:
    monkeypatch.setattr(
        "job_radar.company_config_service.importlib.util.find_spec",
        lambda name: None,
    )

    strategy = build_company_config_write_strategy()

    assert strategy.writer_name == "none"
    assert strategy.dependency_available is False
    assert strategy.preserves_comments is False
    assert strategy.supports_gui_writes is False
    assert "PyYAML can read target-companies.yaml" in strategy.reason
    assert "does not preserve comments or source grouping" in strategy.reason


def test_build_company_config_write_strategy_allows_writes_with_ruamel(monkeypatch) -> None:
    monkeypatch.setattr(
        "job_radar.company_config_service.importlib.util.find_spec",
        lambda name: object(),
    )

    strategy = build_company_config_write_strategy()

    assert strategy.writer_name == "ruamel.yaml"
    assert strategy.dependency_available is True
    assert strategy.preserves_comments is True
    assert strategy.supports_gui_writes is True
    assert "preserve comments, ordering, and source grouping" in strategy.reason
