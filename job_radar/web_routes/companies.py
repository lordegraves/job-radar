"""Serve profile-aware company-source list and detail pages."""

from collections.abc import Callable

from flask import Flask, abort, redirect, render_template, request, url_for

from job_radar.company_assignment_service import (
    add_existing_company_to_profile,
    remove_company_from_profile,
    set_company_scanning_state,
)
from job_radar.company_catalog_query_service import build_company_catalog_view
from job_radar.company_recommendation_models import (
    DISMISSED,
    MAYBE_LATER,
    NOT_RELEVANT,
)
from job_radar.company_recommendation_service import (
    CompanyRecommendationError,
    build_company_recommendations,
    build_company_starter_guidance,
    record_recommendation_feedback,
)
from job_radar.company_recommendation_storage import mark_added
from job_radar.company_workspace_service import build_company_workspace
from job_radar.domain_errors import (
    EmployerNotFoundError,
    InvalidCompanyStateError,
    JuniorDomainError,
)
from job_radar.employer_resolution_service import resolve_employer_submission
from job_radar.employer_review_service import list_profile_review_states
from job_radar.external_company_discovery_service import (
    ExternalCompanyDiscoveryError,
    build_external_company_candidates,
    send_external_candidate_to_review,
)


def register_company_routes(
    app: Flask,
    *,
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
                review_states=list_profile_review_states(
                    get_database_path(),
                    workspace.active_profile.profile_id,
                ),
            )

        return render_template(
            "companies.html",
            workspace=workspace,
            profile_required=True,
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

        abort(404)

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
            resolution=None,
            submission=request.args.get("q", "").strip(),
        )

    @app.get("/companies/recommendations")
    def company_recommendations() -> str:
        workspace = build_company_workspace(get_database_path())
        if workspace.active_profile is None:
            return redirect(
                url_for(
                    "companies",
                    company_result="error",
                    company_error=(
                        "Select a managed profile before viewing recommendations."
                    ),
                )
            )
        return render_template(
            "company_recommendations.html",
            profile=workspace.active_profile,
            recommendations=build_company_recommendations(get_database_path()),
            starter_guidance=build_company_starter_guidance(
                get_database_path()
            ),
            external_candidates=build_external_company_candidates(
                get_database_path()
            ),
            company_message=request.args.get("company_message", "").strip(),
            company_error=request.args.get("company_error", "").strip(),
        )

    @app.post("/companies/recommendations/<employer_id>/add")
    def add_company_recommendation(employer_id: str):
        workspace = build_company_workspace(get_database_path())
        if workspace.active_profile is None:
            return redirect(url_for("companies"))
        try:
            result = add_existing_company_to_profile(
                get_database_path(),
                workspace.active_profile.profile_id,
                employer_id,
            )
            mark_added(
                get_database_path(),
                profile_id=workspace.active_profile.profile_id,
                employer_id=employer_id,
            )
        except JuniorDomainError as error:
            return redirect(
                url_for(
                    "company_recommendations",
                    company_error=str(error),
                )
            )
        return redirect(
            url_for(
                "company_recommendations",
                company_message=(
                    f"{result.employer_name} was added and will be scanned."
                ),
            )
        )

    @app.post("/companies/recommendations/external/<candidate_key>/review")
    def review_external_company_candidate(candidate_key: str):
        workspace = build_company_workspace(get_database_path())
        if workspace.active_profile is None:
            return redirect(url_for("companies"))
        try:
            result = send_external_candidate_to_review(
                get_database_path(),
                profile_id=workspace.active_profile.profile_id,
                candidate_key=candidate_key,
            )
        except ExternalCompanyDiscoveryError as error:
            return redirect(
                url_for("company_recommendations", company_error=str(error))
            )
        return redirect(
            url_for(
                "company_recommendations",
                company_message=result.message,
            )
        )

    @app.post("/companies/recommendations/<employer_id>/feedback")
    def company_recommendation_feedback(employer_id: str):
        workspace = build_company_workspace(get_database_path())
        if workspace.active_profile is None:
            return redirect(url_for("companies"))
        state = request.form.get("state", "")
        if state not in {MAYBE_LATER, DISMISSED, NOT_RELEVANT}:
            return redirect(
                url_for(
                    "company_recommendations",
                    company_error="Choose a valid recommendation response.",
                )
            )
        try:
            record_recommendation_feedback(
                get_database_path(),
                profile_id=workspace.active_profile.profile_id,
                employer_id=employer_id,
                state=state,
            )
        except CompanyRecommendationError as error:
            return redirect(
                url_for("company_recommendations", company_error=str(error))
            )
        return redirect(
            url_for(
                "company_recommendations",
                company_message="Your response was saved for this profile.",
            )
        )

    @app.post("/companies/add/resolve")
    def resolve_company_submission():
        workspace = build_company_workspace(get_database_path())
        if workspace.active_profile is None:
            return redirect(
                url_for(
                    "companies",
                    company_result="error",
                    company_error=(
                        "Select a managed profile before adding a company."
                    ),
                )
            )

        submission = request.form.get("company", "").strip()
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
        )

    @app.post("/companies/add/confirm-detected")
    def confirm_detected_company():
        workspace = build_company_workspace(get_database_path())
        if workspace.active_profile is None:
            return redirect(url_for("companies"))
        company_name = request.form.get("company_name", "").strip()
        careers_url = request.form.get("careers_url", "").strip()
        resolution = resolve_employer_submission(
            get_database_path(),
            profile_id=workspace.active_profile.profile_id,
            company_name=company_name,
            careers_url=careers_url,
            confirm_detected=True,
        )
        catalog = build_company_catalog_view(get_database_path())
        return render_template(
            "company_add.html",
            catalog=catalog,
            company_error="",
            resolution=resolution,
            submission=careers_url or company_name,
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
