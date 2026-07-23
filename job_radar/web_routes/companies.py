"""Serve profile-aware company-source list and detail pages."""

from collections.abc import Callable

from flask import Flask, abort, redirect, render_template, request, url_for

from job_radar.company_assignment_service import (
    add_existing_company_to_profile,
    remove_company_from_profile,
    set_company_scanning_state,
)
from job_radar.company_catalog_query_service import build_company_catalog_view
from job_radar.company_config_service import (
    build_company_source_summaries,
    filter_company_config_views,
)
from job_radar.company_workspace_service import build_company_workspace
from job_radar.company_view_resolution import resolve_company_page_source
from job_radar.domain_errors import (
    EmployerNotFoundError,
    InvalidCompanyStateError,
    JuniorDomainError,
)


def register_company_routes(
    app: Flask,
    *,
    get_company_config_path: Callable[[], str],
    get_database_path: Callable[[], str],
) -> None:
    """Register profile-aware read-only company configuration pages."""

    @app.get("/companies")
    def companies() -> str:
        workspace = build_company_workspace(get_database_path())

        if workspace.active_profile is not None:
            return render_template(
                "companies.html",
                workspace=workspace,
                active_profile=workspace.active_profile,
                uses_legacy_yaml=False,
                company_result=request.args.get("company_result", "").strip(),
                company_message=request.args.get("company_message", "").strip(),
                company_error=request.args.get("company_error", "").strip(),
            )

        # Compatibility: technical YAML visibility remains until the legacy
        # configuration workflow is deliberately retired.
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
            workspace=workspace,
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
            company_result=request.args.get("company_result", "").strip(),
            company_message=request.args.get("company_message", "").strip(),
            company_error=request.args.get("company_error", "").strip(),
        )

    @app.get("/companies/<company_key>")
    def company_detail(company_key: str) -> str:
        workspace = build_company_workspace(get_database_path())

        if workspace.active_profile is not None:
            company = next(
                (
                    item
                    for item in workspace.companies
                    if item.company_key == company_key
                ),
                None,
            )
            if company is None:
                abort(404)

            return render_template(
                "company_detail.html",
                company=company,
                active_profile=workspace.active_profile,
                uses_legacy_yaml=False,
                company_result=request.args.get("company_result", "").strip(),
                company_message=request.args.get("company_message", "").strip(),
                company_error=request.args.get("company_error", "").strip(),
            )

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
            company_result=request.args.get("company_result", "").strip(),
            company_message=request.args.get("company_message", "").strip(),
            company_error=request.args.get("company_error", "").strip(),
        )

    @app.post("/companies/<company_key>/scanning")
    def set_company_scanning(company_key: str):
        workspace = build_company_workspace(get_database_path())
        if workspace.active_profile is None:
            return redirect(
                url_for(
                    "companies",
                    company_result="error",
                    company_error=(
                        "Select a managed profile before changing a company."
                    ),
                )
            )

        requested_state = request.form.get("state", "").strip().casefold()
        try:
            if requested_state not in {"scanning", "paused"}:
                raise InvalidCompanyStateError(
                    "Choose Pause or Resume and try again."
                )

            result = set_company_scanning_state(
                get_database_path(),
                workspace.active_profile.profile_id,
                company_key,
                scanning=requested_state == "scanning",
            )
        except JuniorDomainError as error:
            return redirect(
                url_for(
                    "companies",
                    company_result="error",
                    company_error=str(error),
                )
            )

        state_label = "scanning" if result.scanning else "paused"
        return redirect(
            url_for(
                "companies",
                company_result="updated",
                company_message=(
                    f"{result.employer_name} is now {state_label} for "
                    f"{result.profile_name}'s profile."
                ),
            )
        )

    @app.post("/companies/<company_key>/remove")
    def remove_profile_company(company_key: str):
        workspace = build_company_workspace(get_database_path())
        if workspace.active_profile is None:
            return redirect(
                url_for(
                    "companies",
                    company_result="error",
                    company_error=(
                        "Select a managed profile before removing a company."
                    ),
                )
            )

        try:
            if request.form.get("confirmation", "").strip() != "REMOVE":
                raise InvalidCompanyStateError(
                    "Type REMOVE to confirm removing this company from the "
                    "active profile."
                )

            result = remove_company_from_profile(
                get_database_path(),
                workspace.active_profile.profile_id,
                company_key,
            )
        except JuniorDomainError as error:
            return redirect(
                url_for(
                    "companies",
                    company_result="error",
                    company_error=str(error),
                )
            )

        return redirect(
            url_for(
                "companies",
                company_result="updated",
                company_message=(
                    f"{result.employer_name} was removed from "
                    f"{result.profile_name}'s company list. Existing jobs and "
                    "application history were kept."
                ),
            )
        )

    @app.get("/companies/add")
    def add_company_page() -> str:
        catalog = build_company_catalog_view(
            get_database_path(),
            search_query=request.args.get("q", ""),
        )
        if catalog.active_profile is None:
            return redirect(
                url_for(
                    "companies",
                    company_result="error",
                    company_error=(
                        "Select a managed profile before adding a company."
                    ),
                )
            )

        return render_template(
            "company_add.html",
            catalog=catalog,
            company_error=request.args.get("company_error", "").strip(),
        )

    @app.post("/companies/add")
    def add_existing_company():
        catalog = build_company_catalog_view(get_database_path())
        if catalog.active_profile is None:
            return redirect(
                url_for(
                    "companies",
                    company_result="error",
                    company_error=(
                        "Select a managed profile before adding a company."
                    ),
                )
            )

        employer_id = request.form.get("employer_id", "").strip()
        try:
            if not employer_id:
                raise EmployerNotFoundError("Choose a company to add.")

            result = add_existing_company_to_profile(
                get_database_path(),
                catalog.active_profile.profile_id,
                employer_id,
            )
        except JuniorDomainError as error:
            return redirect(
                url_for(
                    "add_company_page",
                    company_error=str(error),
                )
            )

        return redirect(
            url_for(
                "companies",
                company_result="updated",
                company_message=(
                    f"{result.employer_name} was added to "
                    f"{result.profile_name}'s company list and will be scanned."
                ),
            )
        )
