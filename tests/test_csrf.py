"""Verify shared CSRF protection rejects unsafe mutations without side effects."""

from pathlib import Path

from job_radar.csrf import CSRF_HEADER_NAME
from job_radar.domain_errors import (
    AdminAccessRequiredError,
    EmployerAlreadyAssignedError,
    EmployerConfigurationError,
    EmployerInUseError,
    EmployerNotAssignedError,
    EmployerNotFoundError,
    EmployerUnavailableError,
    InvalidCompanyStateError,
    JuniorDomainError,
    NoActiveProfileError,
    RecommendationNotFoundError,
)
from job_radar.web_app import create_app


def build_test_app(tmp_path: Path):
    settings_path = tmp_path / "config" / "settings.yaml"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(
        (
            f"database_path: {tmp_path / 'data' / 'junior.sqlite3'}\n"
            f"reports_path: {tmp_path / 'reports'}\n"
            f"logs_path: {tmp_path / 'logs'}\n"
        ),
        encoding="utf-8",
    )
    return create_app(
        settings_path=settings_path,
        base_directory=tmp_path,
    )


def test_missing_and_invalid_tokens_are_rejected_without_unlocking(
    tmp_path: Path,
) -> None:
    app = build_test_app(tmp_path)
    client = app.test_client()
    client.get("/administration/unlock")

    missing_response = client.post(
        "/administration/unlock",
        data={"confirmation": "ADMIN"},
        _without_csrf=True,
    )
    invalid_response = client.post(
        "/administration/unlock",
        data={"confirmation": "ADMIN"},
        headers={CSRF_HEADER_NAME: "invalid-token"},
    )

    assert missing_response.status_code == 400
    assert invalid_response.status_code == 400
    assert "could not safely submit" in missing_response.get_data(as_text=True)
    assert "No change was made" in missing_response.get_data(as_text=True)
    assert client.get("/administration").status_code == 302


def test_valid_token_allows_mutation_and_json_failure_is_safe(
    tmp_path: Path,
) -> None:
    app = build_test_app(tmp_path)
    client = app.test_client()

    valid_response = client.post(
        "/administration/unlock",
        data={"confirmation": "ADMIN"},
    )
    json_failure = client.post(
        "/scan/run",
        headers={"Accept": "application/json"},
        _without_csrf=True,
    )

    assert valid_response.status_code == 302
    assert valid_response.headers["Location"] == "/administration"
    assert json_failure.status_code == 400
    assert json_failure.get_json() == {
        "status": "error",
        "message": (
            "Junior could not safely submit this request. "
            "Refresh the page and try again."
        ),
    }


def test_every_current_post_form_renders_a_csrf_token() -> None:
    template_root = Path("job_radar/templates")
    templates_with_post_forms = (
        "administration/unlock.html",
        "administration/employer_detail.html",
        "administration/employer_form.html",
        "administration/employer_review_detail.html",
        "administration/recommendations.html",
        "base.html",
        "companies.html",
        "company_add.html",
        "company_recommendations.html",
        "company_detail.html",
        "history_edit.html",
        "legacy_profile_form.html",
        "preferences.html",
        "profile.html",
        "profile_fit_board.html",
        "profile_form.html",
        "role_discovery.html",
        "scan.html",
        "setup_resume.html",
        "setup_welcome.html",
        "setup_companies.html",
        "setup_review.html",
        "tracker_add.html",
        "tracker_edit.html",
    )

    for template_name in templates_with_post_forms:
        template = (template_root / template_name).read_text(encoding="utf-8")
        assert template.count('method="post"') == template.count(
            'name="_csrf_token"'
        ), template_name


def test_mutation_routes_do_not_accept_get_requests(tmp_path: Path) -> None:
    app = build_test_app(tmp_path)
    mutation_endpoints = {
        "administration_unlock_submit",
        "administration_lock",
        "administration_employer_new_submit",
        "administration_employer_edit_submit",
        "administration_employer_validate",
        "administration_employer_disable",
        "administration_employer_enable",
        "administration_employer_retire",
        "administration_employer_review_match",
        "administration_employer_review_status",
        "administration_employer_review_assign",
        "run_scan",
        "save_new_tracker_application",
        "update_tracker_application",
        "update_history_record",
        "save_preferences",
        "create_profile_route",
        "add_existing_company",
        "add_company_recommendation",
        "company_recommendation_feedback",
        "review_external_company_candidate",
        "resolve_company_submission",
        "remove_profile_company",
        "set_company_scanning",
        "select_profile_route",
        "edit_profile_route",
        "save_profile_fit_board_route",
        "delete_profile_route",
        "upload_managed_resume",
        "upload_resume",
    }

    methods_by_endpoint = {
        rule.endpoint: rule.methods
        for rule in app.url_map.iter_rules()
        if rule.endpoint in mutation_endpoints
    }

    assert methods_by_endpoint.keys() == mutation_endpoints
    assert all(
        methods is not None and "POST" in methods and "GET" not in methods
        for methods in methods_by_endpoint.values()
    )


def test_company_domain_errors_share_a_safe_base_type() -> None:
    error_types = (
        NoActiveProfileError,
        EmployerNotFoundError,
        EmployerNotAssignedError,
        EmployerAlreadyAssignedError,
        EmployerUnavailableError,
        EmployerConfigurationError,
        EmployerInUseError,
        InvalidCompanyStateError,
        AdminAccessRequiredError,
        RecommendationNotFoundError,
    )

    assert all(issubclass(error_type, JuniorDomainError) for error_type in error_types)
