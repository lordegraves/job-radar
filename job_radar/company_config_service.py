"""Prepare company-source settings for safe display and future GUI editing."""

import importlib.util
from collections.abc import Mapping

from dataclasses import dataclass

from job_radar.config import load_yaml_file


@dataclass(frozen=True)
class CompanyConfigView:
    company_key: str
    name: str
    source_type: str
    enabled: bool
    source_detail: str
    notes: str | None
    config_items: list[tuple[str, object]]


@dataclass(frozen=True)
class CompanySourceSummaryView:
    source_type: str
    total: int
    enabled: int
    disabled: int


@dataclass(frozen=True)
class CompanyConfigWriteStrategyView:
    writer_name: str
    dependency_available: bool
    preserves_comments: bool
    supports_gui_writes: bool
    reason: str


def build_company_config_write_strategy() -> CompanyConfigWriteStrategyView:
    if _is_ruamel_yaml_available():
        return CompanyConfigWriteStrategyView(
            writer_name="ruamel.yaml",
            dependency_available=True,
            preserves_comments=True,
            supports_gui_writes=True,
            reason=(
                "ruamel.yaml is available, so future company config writes can "
                "preserve comments, ordering, and source grouping."
            ),
        )

    return CompanyConfigWriteStrategyView(
        writer_name="none",
        dependency_available=False,
        preserves_comments=False,
        supports_gui_writes=False,
        reason=(
            "Company config writes are disabled because only read-oriented YAML "
            "support is available. PyYAML can read target-companies.yaml, but it "
            "does not preserve comments or source grouping when writing."
        ),
    )


def _is_ruamel_yaml_available() -> bool:
    try:
        return importlib.util.find_spec("ruamel.yaml") is not None
    except ModuleNotFoundError:
        return False


def build_company_config_views(config_path: str) -> list[CompanyConfigView]:
    data = load_yaml_file(config_path)
    companies = data.get("companies", [])

    if not isinstance(companies, list):
        return []

    return build_company_config_views_from_mappings(companies)


def build_company_config_views_from_mappings(
    companies: list[object],
) -> list[CompanyConfigView]:
    """Build display views from YAML or app-owned employer mappings."""

    company_views: list[CompanyConfigView] = []

    for company in companies:
        if not isinstance(company, Mapping):
            continue

        company_mapping = dict(company)
        company_views.append(
            CompanyConfigView(
                company_key=str(company_mapping.get("company_key", "")),
                name=str(company_mapping.get("name", "")),
                source_type=str(company_mapping.get("source_type", "")),
                enabled=bool(company_mapping.get("enabled", True)),
                source_detail=get_company_source_detail(company_mapping),
                notes=company_mapping.get("notes"),
                config_items=get_company_config_items(company_mapping),
            )
        )

    return sorted(
        company_views,
        key=lambda company: (
            company.source_type.lower(),
            company.name.lower(),
        ),
    )


def get_company_config_view(
    config_path: str,
    company_key: str,
) -> CompanyConfigView | None:
    companies = build_company_config_views(config_path)

    for company in companies:
        if company.company_key == company_key:
            return company

    return None


def filter_company_config_views(
    companies: list[CompanyConfigView],
    *,
    selected_status: str,
    selected_source_type: str,
    search_query: str,
) -> list[CompanyConfigView]:
    filtered_companies = companies

    if selected_status == "enabled":
        filtered_companies = [
            company for company in filtered_companies if company.enabled
        ]
    elif selected_status == "disabled":
        filtered_companies = [
            company for company in filtered_companies if not company.enabled
        ]

    if selected_source_type:
        filtered_companies = [
            company
            for company in filtered_companies
            if company.source_type == selected_source_type
        ]

    if search_query:
        filtered_companies = [
            company
            for company in filtered_companies
            if search_query.lower() in get_company_search_text(company)
        ]

    return filtered_companies


def build_company_source_summaries(
    companies: list[CompanyConfigView],
) -> list[CompanySourceSummaryView]:
    source_types = sorted({company.source_type for company in companies})

    return [
        CompanySourceSummaryView(
            source_type=source_type,
            total=sum(1 for company in companies if company.source_type == source_type),
            enabled=sum(
                1
                for company in companies
                if company.source_type == source_type and company.enabled
            ),
            disabled=sum(
                1
                for company in companies
                if company.source_type == source_type and not company.enabled
            ),
        )
        for source_type in source_types
    ]


def get_company_search_text(company: CompanyConfigView) -> str:
    searchable_values = [
        company.company_key,
        company.name,
        company.source_type,
        company.source_detail,
        company.notes,
    ]

    searchable_values.extend(
        f"{name} {value}"
        for name, value in company.config_items
    )

    return " ".join(str(value or "") for value in searchable_values).lower()


def get_company_config_items(company: dict) -> list[tuple[str, object]]:
    return sorted(company.items(), key=lambda item: item[0])


def get_company_source_detail(company: dict) -> str:
    detail_keys = (
        "source_slug",
        "source_url",
        "source_base_url",
        "domain_name",
        "company_identifier",
        "origin_url",
        "referer_url",
        "job_base_url",
        "site_number",
    )

    details = [
        f"{key}: {company[key]}"
        for key in detail_keys
        if company.get(key)
    ]

    query_params = company.get("query_params")

    if isinstance(query_params, dict) and query_params:
        details.append(
            "query_params: "
            + ", ".join(
                f"{key}={value}"
                for key, value in sorted(query_params.items())
            )
        )

    if not details:
        return "No source detail configured."

    return " | ".join(details)
