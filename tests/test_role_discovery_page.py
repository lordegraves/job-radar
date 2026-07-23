"""Verify the GUI exposes evidence-grounded role suggestions and feedback."""

from pathlib import Path

from job_radar.profile_models import (
    ManagedProfile,
    ManagedResume,
    OccupationPreference,
    ProfilePreferences,
    get_managed_resume_directory,
)
from job_radar.profile_storage import create_and_select_profile
from job_radar.role_discovery_service import list_role_suggestions
from job_radar.web_app import create_app


def _app_with_profile(tmp_path: Path):
    settings = tmp_path / "settings.yaml"
    database = tmp_path / "junior.sqlite3"
    settings.write_text(
        (
            f"database_path: {database}\n"
            f"reports_path: {tmp_path / 'reports'}\n"
            f"logs_path: {tmp_path / 'logs'}\n"
        ),
        encoding="utf-8",
    )
    profile = ManagedProfile(
        profile_id="profile_aaaaaaaa",
        display_name="Fictional Network Profile",
        preferences=ProfilePreferences(
            target_roles=("Network and Computer Systems Administrators",),
            occupation_selections=(
                OccupationPreference(
                    value="15-1244.00",
                    label="Network and Computer Systems Administrators",
                ),
            ),
        ),
        resume=ManagedResume(source_file_name="resume.txt"),
    )
    create_and_select_profile(database, profile)
    resume_directory = tmp_path / get_managed_resume_directory(profile.profile_id)
    resume_directory.mkdir(parents=True)
    (resume_directory / "resume.txt").write_text(
        (
            "Configured and maintained computer networks, operating systems, "
            "servers, security, and system performance."
        ),
        encoding="utf-8",
    )
    return (
        create_app(settings_path=settings, base_directory=tmp_path),
        database,
        profile,
    )


def test_role_discovery_page_refreshes_and_records_feedback(
    tmp_path: Path,
) -> None:
    app, database, profile = _app_with_profile(tmp_path)
    client = app.test_client()

    empty_page = client.get(f"/profile/{profile.profile_id}/roles")
    assert empty_page.status_code == 200
    assert "No suggestions yet" in empty_page.get_data(as_text=True)

    refresh = client.post(f"/profile/{profile.profile_id}/roles/refresh")
    assert refresh.status_code == 302
    suggestions = list_role_suggestions(
        database,
        profile_id=profile.profile_id,
    )
    assert suggestions

    page = client.get(refresh.headers["Location"])
    html = page.get_data(as_text=True)
    assert "not dictionary synonyms" in html
    assert suggestions[0].suggested_title in html
    assert "Relevant" in html
    assert "Not relevant" in html
    assert "Different discipline" in html

    feedback = client.post(
        (
            f"/profile/{profile.profile_id}/roles/"
            f"{suggestions[0].suggestion_id}/feedback"
        ),
        data={"feedback_state": "different_discipline"},
    )
    assert feedback.status_code == 302
    stored = list_role_suggestions(
        database,
        profile_id=profile.profile_id,
    )
    assert next(
        item
        for item in stored
        if item.suggestion_id == suggestions[0].suggestion_id
    ).feedback_state == "different_discipline"


def test_profile_summary_links_to_role_discovery(tmp_path: Path) -> None:
    app, _, profile = _app_with_profile(tmp_path)

    html = app.test_client().get("/profile").get_data(as_text=True)

    assert "Related roles" in html
    assert f"/profile/{profile.profile_id}/roles" in html
