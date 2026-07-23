"""Verify only a genuinely empty installation enters first-run setup."""

import json
from io import BytesIO
from pathlib import Path

from job_radar.employer_models import EmployerSource
from job_radar.employer_storage import upsert_employer_source
from job_radar.first_run_service import needs_first_run_setup
from job_radar.profile_models import ManagedProfile
from job_radar.profile_storage import create_profile, get_active_profile
from job_radar.setup_progress_service import (
    COMPANIES,
    COMPLETE,
    RESUME,
    REVIEW,
    get_setup_progress,
)
from job_radar.web_app import create_app


def _app(tmp_path: Path):
    settings = tmp_path / "settings.yaml"
    settings.write_text(
        (
            f"database_path: {tmp_path / 'junior.sqlite3'}\n"
            f"reports_path: {tmp_path / 'reports'}\n"
            f"logs_path: {tmp_path / 'logs'}\n"
        ),
        encoding="utf-8",
    )
    return create_app(settings_path=settings, base_directory=tmp_path)


def test_empty_installation_opens_setup_welcome(tmp_path: Path) -> None:
    app = _app(tmp_path)
    client = app.test_client()

    response = client.get("/")
    setup = client.get(response.headers["Location"])

    assert response.status_code == 302
    assert response.headers["Location"] == "/setup"
    assert setup.status_code == 200
    html = setup.get_data(as_text=True)
    assert "Welcome to junior" in html
    assert "Nothing has been saved yet" in " ".join(html.split())
    assert 'action="/setup/start"' in html


def test_existing_profile_does_not_reenter_first_run(tmp_path: Path) -> None:
    app = _app(tmp_path)
    database_path = tmp_path / "junior.sqlite3"
    create_profile(
        database_path,
        ManagedProfile(
            profile_id="profile_aaaaaaaa",
            display_name="Test User",
        ),
    )
    client = app.test_client()

    assert needs_first_run_setup(database_path) is False
    assert client.get("/").status_code == 200
    assert client.get("/setup").headers["Location"] == "/profile"


def test_existing_employer_is_not_mistaken_for_new_installation(
    tmp_path: Path,
) -> None:
    app = _app(tmp_path)
    database_path = tmp_path / "junior.sqlite3"
    upsert_employer_source(
        database_path,
        EmployerSource(
            employer_id="example_employer",
            name="Example Employer",
            source_type="greenhouse",
            source_config={"source_slug": "example"},
        ),
    )

    assert needs_first_run_setup(database_path) is False
    assert app.test_client().get("/").status_code == 200


def test_guided_setup_reuses_profile_resume_company_and_review_workflows(
    tmp_path: Path,
) -> None:
    app = _app(tmp_path)
    client = app.test_client()

    start_response = client.post("/setup/start")
    assert start_response.headers["Location"] == "/profile/new?setup=1"

    create_response = client.post(
        "/preferences",
        data={
            "profile_mode": "create",
            "setup_mode": "1",
            "display_name": "Fictional Baker",
            "occupation_selections_json": json.dumps(
                [{"value": "35-2011.00", "label": "Bakers"}]
            ),
            "location_selections_json": "[]",
            "responsibility-level": ["Mid-level"],
            "employment-type": ["Full-time"],
            "workplace-arrangement": ["On-site"],
            "schedule_preference": "Day shift",
            "travel_percentage": "10",
        },
    )

    assert create_response.status_code == 302
    assert create_response.headers["Location"].startswith("/setup/resume")

    resume_page = client.get(create_response.headers["Location"])
    assert "Step 2 of 4" in resume_page.get_data(as_text=True)
    profile = get_active_profile(tmp_path / "junior.sqlite3")
    assert profile is not None
    progress = get_setup_progress(tmp_path / "junior.sqlite3")
    assert progress is not None
    assert progress.current_step == RESUME
    assert progress.profile_id == profile.profile_id

    restarted_client = _app(tmp_path).test_client()
    restarted_response = restarted_client.get("/")
    assert restarted_response.headers["Location"] == "/setup/resume?setup=1"

    upload_response = client.post(
        f"/profile/{profile.profile_id}/resume",
        data={
            "setup_mode": "1",
            "resume_file": (
                BytesIO(b"# Fictional Resume\n\nCommercial baking."),
                "resume.md",
            ),
        },
        content_type="multipart/form-data",
    )

    assert upload_response.headers["Location"] == "/setup/companies"
    progress = get_setup_progress(tmp_path / "junior.sqlite3")
    assert progress is not None
    assert progress.current_step == COMPANIES

    companies_html = client.get("/setup/companies").get_data(as_text=True)
    assert "Step 3 of 4" in companies_html
    assert "<strong>0</strong> companies are currently included" in " ".join(
        companies_html.split()
    )

    review_response = client.post("/setup/review")
    assert review_response.headers["Location"] == "/setup/review"
    progress = get_setup_progress(tmp_path / "junior.sqlite3")
    assert progress is not None
    assert progress.current_step == REVIEW

    review_html = client.get("/setup/review").get_data(as_text=True)
    assert "Step 4 of 4" in review_html
    assert "Fictional Baker" in review_html
    assert "Bakers" in review_html
    assert "Full-time" in review_html
    assert "Day shift" in review_html
    assert "On-site" in review_html
    assert "10%" in review_html
    assert "resume.md" in review_html
    assert "junior will scan only the companies you deliberately selected" in review_html
    assert str(tmp_path) in review_html

    rejected_completion = client.post(
        "/setup/complete",
        data={"confirmation": "not confirmed"},
    )
    assert rejected_completion.headers["Location"] == "/setup/review"
    progress = get_setup_progress(tmp_path / "junior.sqlite3")
    assert progress is not None
    assert progress.current_step == REVIEW
    assert progress.completed_at is None

    completion = client.post(
        "/setup/complete",
        data={"confirmation": "FINISH"},
    )
    assert completion.headers["Location"] == "/"
    progress = get_setup_progress(tmp_path / "junior.sqlite3")
    assert progress is not None
    assert progress.current_step == COMPLETE
    assert progress.completed_at is not None
    assert client.get("/").status_code == 200


def test_setup_can_skip_resume_and_resume_at_companies(tmp_path: Path) -> None:
    app = _app(tmp_path)
    client = app.test_client()
    client.post("/setup/start")
    create_response = client.post(
        "/preferences",
        data={
            "profile_mode": "create",
            "setup_mode": "1",
            "display_name": "Fictional Cook",
            "occupation_selections_json": json.dumps(
                [{"value": "35-2012.00", "label": "Cooks, Institution and Cafeteria"}]
            ),
            "location_selections_json": "[]",
            "responsibility-level": ["Mid-level"],
            "employment-type": ["Full-time"],
            "workplace-arrangement": ["On-site"],
            "schedule_preference": "Day shift",
            "travel_percentage": "10",
        },
    )
    assert create_response.headers["Location"].startswith("/setup/resume")

    skip_response = client.post("/setup/skip-resume")
    assert skip_response.headers["Location"] == "/setup/companies"
    progress = get_setup_progress(tmp_path / "junior.sqlite3")
    assert progress is not None
    assert progress.current_step == COMPANIES
    assert progress.profile_id is not None
    assert _app(tmp_path).test_client().get("/").headers[
        "Location"
    ] == "/setup/companies?setup=1"
