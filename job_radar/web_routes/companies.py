"""Serve profile-aware company-source list and detail pages."""

from collections.abc import Callable

from flask import Flask, abort, render_template, request

from job_radar.company_config_service import (
    build_company_source_summaries,
    filter_company_config_views,
)
from job_radar.company_view_resolution import resolve_company_page_source


def register_company_routes(
    app: Flask,
    *,
    get_company_config_path: Callable[[], str],
    get_database_path: Callable[[], str],
) -> None:
    """Register profile-aware read-only company configuration pages."""

    @app.get("/companies")
    def companies() -> str:
        page_source = resolve_company_page_source(
            get_database_path(),
            get_company_config_path(),
        )
        company_views = page_source.companies
        selected_status = request.args.get("status", "")
        selected_source_type = request.args.get("source_type", "")
        search_query = request.args.get("q", "").strip()
        filtered_companies = filter_company_config_views(
            company_views,
            selected_status=selected_status,
            selected_source_type=selected_source_type,
            search_query=search_query,
        )
        source_summaries = build_company_source_summaries(company_views)

        return render_template(
            "companies.html",
            companies=filtered_companies,
            source_summaries=source_summaries,
            company_config_path=page_source.company_config_path,
            active_profile=page_source.active_profile,
            uses_legacy_yaml=page_source.uses_legacy_yaml,
            total_companies=len(company_views),
            enabled_companies=sum(
                1 for company in company_views if company.enabled
            ),
            disabled_companies=sum(
                1 for company in company_views if not company.enabled
            ),
            selected_status=selected_status,
            selected_source_type=selected_source_type,
            search_query=search_query,
            filtered_company_count=len(filtered_companies),
        )

    @app.get("/companies/<company_key>")
    def company_detail(company_key: str) -> str:
        page_source = resolve_company_page_source(
            get_database_path(),
            get_company_config_path(),
        )
        company_view = next(
            (
                company
                for company in page_source.companies
                if company.company_key == company_key
            ),
            None,
        )

        if company_view is None:
            abort(404)

        return render_template(
            "company_detail.html",
            company=company_view,
            company_config_path=page_source.company_config_path,
            active_profile=page_source.active_profile,
            uses_legacy_yaml=page_source.uses_legacy_yaml,
        )
