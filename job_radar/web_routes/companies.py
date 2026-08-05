"""Serve profile-aware company-source list and detail pages."""

from collections.abc import Callable

from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    url_for,
)
from job_radar.company_transfer_service import (
    export_company_catalog,
    import_company_catalog,
)

from job_radar.company_assignment_service import (
    add_existing_company_to_profile,
    remove_company_from_profile,
    set_company_scanning_state,
)
from job_radar.company_catalog_query_service import build_company_catalog_view
from job_radar.company_workspace_service import build_company_workspace
from job_radar.company_discovery_log import record_company_discovery_event
from job_radar.config import ConfigError, load_settings
from job_radar.domain_errors import (
    EmployerNotFoundError,
    InvalidCompanyStateError,
    JuniorDomainError,
)
from job_radar.employer_admin_service import (
    EmployerAdminError,
    rename_employer,
    update_employer_links,
)
from job_radar.employer_connection_service import (
    EmployerConnectionError,
    test_employer_connection,
)
from job_radar.employer_resolution_service import (
    ALREADY_ASSIGNED,
    CREATED_SCAN_READY,
    resolve_employer_submission,
)
from job_radar.employer_review_service import (
    EmployerReviewError,
    cancel_profile_review_request,
    get_review_request,
    list_profile_review_states,
    mark_configured_new,
)
from job_radar.source_health_service import build_source_health_items
from job_radar.source_test_runner import SourceTestRunner


def register_company_routes(
    app: Flask,
    *,
    get_database_path: Callable[[], str],
    settings_path: str,
) -> None:
    """Register profile-aware company management and safe source testing."""
    source_test_runner = SourceTestRunner(
        lambda employer_id: test_employer_connection(
            get_database_path(),
            employer_id,
        )
    )

    @app.get("/companies")
    def companies() -> str:
        workspace = build_company_workspace(get_database_path())

        if workspace.active_profile is not None:
            source_health = {
                item.employer_id: item
                for item in build_source_health_items(get_database_path())
            }
            profile_source_health = tuple(
                source_health[company.company_key]
                for company in workspace.companies
                if company.company_key in source_health
            )
            return render_template(
                "companies.html",
                workspace=workspace,
                active_profile=workspace.active_profile,
                uses_legacy_yaml=False,
                review_states=list_profile_review_states(
                    get_database_path(),
                    workspace.active_profile.profile_id,
                ),
                source_health_counts={
                    "working": sum(
                        item.state == "success" for item in profile_source_health
                    ),
                    "attention": sum(
                        item.state == "error" for item in profile_source_health
                    ),
                    "untested": sum(
                        item.state == "not_tested" for item in profile_source_health
                    ),
                },
                source_health=source_health,
                source_test_status=source_test_runner.status(),
            )

        return render_template(
            "companies.html",
            workspace=workspace,
            profile_required=True,
        )

    @app.get("/companies/export")
    def export_companies():
        filename, content = export_company_catalog(get_database_path())
        response = make_response(content)
        response.headers["Content-Type"] = "application/json; charset=utf-8"
        response.headers["Content-Disposition"] = (
            f'attachment; filename="{filename}"'
        )
        return response

    @app.post("/companies/import")
    def import_companies():
        uploaded = request.files.get("company_file")
        if uploaded is None or not uploaded.filename:
            flash("Choose a Junior company catalog file to import.", "error")
            return redirect(url_for("companies"))
        try:
            result = import_company_catalog(get_database_path(), uploaded.read())
        except (ConfigError, ValueError) as error:
            flash(str(error), "error")
            return redirect(url_for("companies"))
        flash(
            f"Added {result.added} companies to the global catalog. "
            f"Skipped {result.skipped_duplicates} duplicates. "
            "No profile company list was changed.",
            "success",
        )
        return redirect(url_for("companies"))

    @app.post("/companies/test-sources")
    def test_company_sources():
        background_request = (
            request.headers.get("X-Junior-Background-Test") == "1"
        )
        workspace = build_company_workspace(get_database_path())
        if workspace.active_profile is None:
            if not background_request:
                flash("Select a profile before testing company sources.", "error")
                return redirect(url_for("companies"))
            return jsonify(
                {"status": "error", "message": "Select a profile first."}
            ), 400

        available = {
            company.company_key: company
            for company in workspace.companies
        }
        requested = request.form.getlist("employer_id")
        if request.form.get("test_scope") == "untested":
            requested = [
                company.company_key
                for company in workspace.companies
                if company.connection_health.state == "not_tested"
            ]
        selected = [company_id for company_id in requested if company_id in available]
        if not selected:
            if not background_request:
                flash("Select at least one company source to test.", "error")
                return redirect(url_for("companies"))
            return jsonify(
                {
                    "status": "error",
                    "message": "Select at least one company source to test.",
                }
            ), 400
        if not source_test_runner.start(
            selected,
            labels={
                company_id: available[company_id].name
                for company_id in selected
            },
        ):
            if not background_request:
                flash("A company-source test is already running.", "warning")
                return redirect(url_for("companies"))
            return jsonify(
                {
                    "status": "busy",
                    "message": "A company-source test is already running.",
                }
            ), 409
        if not background_request:
            flash(
                f"Testing {len(selected)} company source"
                f"{'' if len(selected) == 1 else 's'} in the background.",
                "success",
            )
            return redirect(url_for("companies"))
        return jsonify({"status": "starting", "total": len(selected)}), 202

    @app.get("/companies/test-sources/status")
    def company_source_test_status():
        return jsonify(source_test_runner.status())

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
            )

        abort(404)

    @app.post("/companies/<company_key>/test-source")
    def test_company_source(company_key: str):
        workspace = build_company_workspace(get_database_path())
        if workspace.active_profile is None or not any(
            item.company_key == company_key for item in workspace.companies
        ):
            abort(404)
        try:
            health = test_employer_connection(
                get_database_path(),
                company_key,
            )
        except EmployerConnectionError as error:
            flash(str(error), "error")
        else:
            flash(
                health.message or "The job-source test finished.",
                "success" if health.state == "success" else "error",
            )
        return redirect(url_for("company_detail", company_key=company_key))

    @app.post("/companies/<company_key>/scanning")
    def set_company_scanning(company_key: str):
        workspace = build_company_workspace(get_database_path())
        if workspace.active_profile is None:
            flash(
                "Select a managed profile before changing a company.",
                "error",
            )
            return redirect(url_for("companies"))

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
            flash(str(error), "error")
            return redirect(url_for("companies"))

        state_label = "scanning" if result.scanning else "paused"
        flash(
            f"{result.employer_name} is now {state_label} for "
            f"{result.profile_name}'s profile.",
            "success",
        )
        return redirect(url_for("companies"))

    @app.post("/companies/<company_key>/remove")
    def remove_profile_company(company_key: str):
        workspace = build_company_workspace(get_database_path())
        if workspace.active_profile is None:
            flash(
                "Select a managed profile before removing a company.",
                "error",
            )
            return redirect(url_for("companies"))

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
            flash(str(error), "error")
            return redirect(url_for("companies"))

        flash(
            f"{result.employer_name} was removed from "
            f"{result.profile_name}'s company list. Existing jobs and "
            "application history were kept.",
            "success",
        )
        return redirect(url_for("companies"))

    @app.post("/companies/<company_key>/name")
    def correct_company_name(company_key: str):
        workspace = build_company_workspace(get_database_path())
        if workspace.active_profile is None:
            abort(404)
        if not any(
            item.company_key == company_key for item in workspace.companies
        ):
            abort(404)
        try:
            renamed = rename_employer(
                get_database_path(),
                company_key,
                name=request.form.get("company_name", ""),
            )
        except EmployerAdminError as error:
            flash(str(error), "error")
            return redirect(url_for("company_detail", company_key=company_key))
        flash(
            f"The shared company name is now {renamed.employer.name}.",
            "success",
        )
        return redirect(url_for("company_detail", company_key=company_key))

    @app.post("/companies/<company_key>/links")
    def save_company_links(company_key: str):
        workspace = build_company_workspace(get_database_path())
        if workspace.active_profile is None:
            abort(404)
        if not any(
            item.company_key == company_key for item in workspace.companies
        ):
            abort(404)
        try:
            update_employer_links(
                get_database_path(),
                company_key,
                links={
                    "website_url": request.form.get("website_url", ""),
                    "careers_link_url": request.form.get(
                        "careers_link_url", ""
                    ),
                    "linkedin_url": request.form.get("linkedin_url", ""),
                    "glassdoor_url": request.form.get("glassdoor_url", ""),
                },
            )
        except EmployerAdminError as error:
            flash(str(error), "error")
            return redirect(url_for("company_detail", company_key=company_key))
        flash(
            "Company links were saved. The working job source was not changed.",
            "success",
        )
        return redirect(url_for("company_detail", company_key=company_key))

    @app.post("/companies/setup-requests/<request_id>/remove")
    def remove_company_setup_request(request_id: str):
        workspace = build_company_workspace(get_database_path())
        if workspace.active_profile is None:
            abort(404)
        try:
            cancel_profile_review_request(
                get_database_path(),
                request_id,
                profile_id=workspace.active_profile.profile_id,
                confirmation=request.form.get("confirmation", ""),
            )
        except EmployerReviewError as error:
            flash(str(error), "error")
            return redirect(url_for("companies"))
        flash(
            "The unfinished setup attempt was removed. Working companies, "
            "jobs, applications, and history were not changed.",
            "success",
        )
        return redirect(url_for("companies"))

    @app.get("/companies/add")
    def add_company_page() -> str:
        retry_request_id = request.args.get("retry", "").strip()
        retry_request = (
            get_review_request(get_database_path(), retry_request_id)
            if retry_request_id
            else None
        )
        catalog = build_company_catalog_view(
            get_database_path(),
            search_query=request.args.get("q", ""),
        )
        if catalog.active_profile is None:
            flash(
                "Select a managed profile before adding a company.",
                "error",
            )
            return redirect(url_for("companies"))
        if (
            retry_request is not None
            and retry_request.requesting_profile_id
            != catalog.active_profile.profile_id
        ):
            retry_request = None

        return render_template(
            "company_add.html",
            catalog=catalog,
            company_error=request.args.get("company_error", "").strip(),
            resolution=None,
            submission=(
                retry_request.submitted_careers_url
                or retry_request.submitted_company_name
                if retry_request is not None
                else request.args.get("q", "").strip()
            ),
            retry_request_id=(
                retry_request.request_id if retry_request is not None else ""
            ),
        )

    @app.post("/companies/add/resolve")
    def resolve_company_submission():
        workspace = build_company_workspace(get_database_path())
        if workspace.active_profile is None:
            flash(
                "Select a managed profile before adding a company.",
                "error",
            )
            return redirect(url_for("companies"))

        submission = request.form.get("company", "").strip()
        retry_request_id = request.form.get("retry_request_id", "").strip()
        looks_like_url = (
            "://" in submission
            or ("." in submission and " " not in submission)
        )
        resolution = resolve_employer_submission(
            get_database_path(),
            profile_id=workspace.active_profile.profile_id,
            company_name="" if looks_like_url else submission,
            careers_url=submission if looks_like_url else "",
        )
        catalog = build_company_catalog_view(
            get_database_path(),
            search_query="" if looks_like_url else submission,
        )
        return render_template(
            "company_add.html",
            catalog=catalog,
            company_error="",
            resolution=resolution,
            submission=submission,
            retry_request_id=retry_request_id,
        )

    @app.post("/companies/add/confirm-detected")
    def confirm_detected_company():
        workspace = build_company_workspace(get_database_path())
        if workspace.active_profile is None:
            return redirect(url_for("companies"))
        company_name = request.form.get("company_name", "").strip()
        careers_url = request.form.get("careers_url", "").strip()
        retry_request_id = request.form.get("retry_request_id", "").strip()
        allow_external_lookup = load_settings(
            settings_path
        ).company_discovery.external_lookup_enabled
        logs_path = load_settings(settings_path).logs_path
        resolution = resolve_employer_submission(
            get_database_path(),
            profile_id=workspace.active_profile.profile_id,
            company_name=company_name,
            careers_url=careers_url,
            confirm_detected=True,
            allow_external_lookup=allow_external_lookup,
            discovery_observer=lambda stage, fields: (
                record_company_discovery_event(logs_path, stage, fields)
            ),
        )
        if resolution.status in {CREATED_SCAN_READY, ALREADY_ASSIGNED}:
            if retry_request_id and resolution.employer_id:
                retry_request = get_review_request(
                    get_database_path(), retry_request_id
                )
                if (
                    retry_request is not None
                    and retry_request.requesting_profile_id
                    == workspace.active_profile.profile_id
                    and retry_request.status == "PENDING"
                ):
                    mark_configured_new(
                        get_database_path(),
                        retry_request_id,
                        resolution.employer_id,
                    )
            flash(resolution.message, "success")
            return redirect(url_for("companies"))
        catalog = build_company_catalog_view(get_database_path())
        return render_template(
            "company_add.html",
            catalog=catalog,
            company_error="",
            resolution=resolution,
            submission=careers_url or company_name,
            retry_request_id=retry_request_id,
        )

    @app.post("/companies/add")
    def add_existing_company():
        catalog = build_company_catalog_view(get_database_path())
        if catalog.active_profile is None:
            flash(
                "Select a managed profile before adding a company.",
                "error",
            )
            return redirect(url_for("companies"))

        employer_id = request.form.get("employer_id", "").strip()
        retry_request_id = request.form.get("retry_request_id", "").strip()
        try:
            if not employer_id:
                raise EmployerNotFoundError("Choose a company to add.")

            result = add_existing_company_to_profile(
                get_database_path(),
                catalog.active_profile.profile_id,
                employer_id,
            )
            if retry_request_id:
                retry_request = get_review_request(
                    get_database_path(), retry_request_id
                )
                if (
                    retry_request is not None
                    and retry_request.requesting_profile_id
                    == catalog.active_profile.profile_id
                    and retry_request.status == "PENDING"
                ):
                    mark_configured_new(
                        get_database_path(),
                        retry_request_id,
                        employer_id,
                    )
        except JuniorDomainError as error:
            flash(str(error), "error")
            return redirect(url_for("add_company_page"))

        flash(
            f"{result.employer_name} was added to "
            f"{result.profile_name}'s company list and will be scanned.",
            "success",
        )
        return redirect(url_for("companies"))
