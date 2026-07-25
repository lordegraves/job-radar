"""Tests the complete web interface and its workflows with temporary user data."""

import json
import os
import threading
from datetime import date, datetime
from io import BytesIO
from pathlib import Path

import job_radar.web_app as web_app_module

from job_radar.config import load_settings
from job_radar.database import connect_database
from job_radar.history_models import JobHistoryRecord
from job_radar.job_decision_service import (
    DECISION_PASSED,
    DECISION_SAVED,
    list_job_decisions,
    save_job_decision,
)
from job_radar.employer_models import EmployerSource
from job_radar.employer_storage import upsert_employer_source
from job_radar.profile_models import ManagedProfile
from job_radar.profile_storage import (
    create_profile,
    get_active_profile,
    list_profiles,
    set_active_profile,
)
from job_radar.storage import (
    complete_scan_run,
    fetch_included_job_history_records,
    initialize_database,
    start_scan_run,
    update_scan_run_progress,
    upsert_job_history_record,
)
from job_radar.tracker.tracker_models import ApplicationRecord
from job_radar.tracker.tracker_storage import (
    get_application,
    list_applications,
    upsert_application,
)
from job_radar.web_app import create_app


def mark_existing_installation(database_file: Path) -> None:
    """Keep dashboard-only tests outside the intentional first-run path."""

    upsert_employer_source(
        database_file,
        EmployerSource(
            employer_id="existing_test_employer",
            name="Existing Test Employer",
            source_type="greenhouse",
            enabled=False,
            source_config={"source_slug": "existing-test"},
        ),
    )


def test_profile_switch_isolates_tracker_and_history_pages(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"
    write_settings_file(settings_file, database_file)
    app = create_app(settings_path=str(settings_file))
    first_profile = ManagedProfile(
        profile_id="profile_11111111",
        display_name="First synthetic profile",
    )
    second_profile = ManagedProfile(
        profile_id="profile_22222222",
        display_name="Second synthetic profile",
    )
    create_profile(database_file, first_profile)
    create_profile(database_file, second_profile)
    client = app.test_client()

    set_active_profile(database_file, first_profile.profile_id)
    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-first-12345678",
            company_name="First Synthetic Company",
            role_title="First Synthetic Role",
        ),
        profile_id=first_profile.profile_id,
    )
    upsert_job_history_record(
        database_file,
        JobHistoryRecord(
            history_type="Pipeline",
            company="First History Company",
            role="First History Role",
            source=None,
            ats_platform=None,
            work_arrangement=None,
            location=None,
            comp_range=None,
            event_date=None,
            status="Passed",
            outcome_category=None,
            recruiter_contact=None,
            technical_match=None,
            hiring_probability=None,
            skills_signals=None,
            primary_blocker=None,
            secondary_blocker=None,
            revisit=None,
            include_in_job_radar=True,
            import_key="first-history-key",
            notes=None,
        ),
        profile_id=first_profile.profile_id,
    )

    first_tracker_html = client.get("/tracker").get_data(as_text=True)
    first_history_html = client.get("/history").get_data(as_text=True)
    set_active_profile(database_file, second_profile.profile_id)
    second_tracker_html = client.get("/tracker").get_data(as_text=True)
    second_history_html = client.get("/history").get_data(as_text=True)

    assert "First Synthetic Company" in first_tracker_html
    assert "First History Company" in first_history_html
    assert "First Synthetic Company" not in second_tracker_html
    assert "First History Company" not in second_history_html
    assert client.get("/tracker/jr-first-12345678/edit").status_code == 404
    assert client.get("/history/first-history-key/edit").status_code == 404


def test_profile_gui_creates_edits_and_deletes_managed_profile(
    tmp_path: Path,
) -> None:
    settings_file = tmp_path / "config" / "settings.yaml"
    database_file = tmp_path / "data" / "job_radar.sqlite3"
    settings_file.parent.mkdir(parents=True)
    write_settings_file(settings_file, database_file)
    app = create_app(settings_path=str(settings_file), base_directory=str(tmp_path))
    client = app.test_client()

    response = client.post(
        "/profile/create",
        data={"display_name": "Example Search"},
    )
    assert response.status_code == 302
    profile = get_active_profile(database_file)
    assert profile is not None

    response = client.post(
        f"/profile/{profile.profile_id}/edit",
        data={
            "display_name": "Platform Search",
            "core_strengths": "Linux\nHPC",
            "compensation_floor_usd": "150000",
        },
    )
    assert response.status_code == 302
    updated = get_active_profile(database_file)
    assert updated is not None
    assert updated.display_name == "Platform Search"
    assert updated.preferences.core_strengths == ("Linux", "HPC")

    page = client.get("/profile").get_data(as_text=True)
    assert "Manage profiles" in page
    assert "Platform Search" in page
    assert "— Active" in page
    assert 'id="managed-profile-select"' in page
    assert "Use this profile" in page
    assert ">Edit</a>" in page
    assert "Create profile" in page
    assert ">Delete</button>" in page
    assert "Type DELETE to confirm" in page
    assert "Archive profile" not in page
    assert "Restore profile" not in page

    response = client.post(
        "/profile/delete", data={"profile_id": profile.profile_id}
    )
    assert response.status_code == 302
    assert get_active_profile(database_file) is None
    assert list_profiles(database_file, include_archived=True) == []


def test_profile_gui_uploads_resume_to_managed_directory(tmp_path: Path) -> None:
    settings_file = tmp_path / "config" / "settings.yaml"
    database_file = tmp_path / "data" / "job_radar.sqlite3"
    settings_file.parent.mkdir(parents=True)
    write_settings_file(settings_file, database_file)
    app = create_app(settings_path=str(settings_file), base_directory=str(tmp_path))
    client = app.test_client()
    client.post("/profile/create", data={"display_name": "Example Search"})
    profile = get_active_profile(database_file)
    assert profile is not None

    response = client.post(
        "/profile/resume",
        data={
            "resume_file": (
                BytesIO(b"# Example Resume\n\nLinux infrastructure"),
                "renamed-later.md",
            )
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 302
    resume_directory = tmp_path / "resumes" / profile.profile_id
    assert (resume_directory / "resume.md").is_file()
    assert (resume_directory / "resume.normalized.txt").is_file()


def write_settings_file(
    settings_file: Path,
    database_file: Path,
    reports_path: Path | None = None,
) -> None:
    resolved_reports_path = reports_path or settings_file.parent

    settings_file.write_text(
        f"""
database_path: {database_file}
reports_path: {resolved_reports_path}
logs_path: {settings_file.parent}

""",
        encoding="utf-8",
    )


def make_report_snapshot_job(
    *,
    title: str,
    url: str,
    company: str,
    location: str | None = None,
    compensation: str | None = None,
    hiring_probability: str = "Unknown",
    recommended_action: str = "Review",
    action_rationale: str = "",
    why_matched: str = "",
    technical_match: str = "Unknown",
    resume_match: str = "Unknown",
    resume_evidence: str = "None",
    resume_gaps: str = "None",
    hiring_risks: str = "None",
    history_context: str = "None",
    history_risk: str | None = None,
    job_radar_id: str = "",
    eligibility_status: str | None = None,
    eligibility_reasons: list[str] | None = None,
) -> dict[str, object]:
    return {
        "title": title,
        "url": url,
        "company": company,
        "location": location,
        "compensation": compensation,
        "hiring_probability": hiring_probability,
        "recommended_action": recommended_action,
        "action_rationale": action_rationale,
        "why_matched": why_matched,
        "technical_match": technical_match,
        "resume_match": resume_match,
        "resume_evidence": resume_evidence,
        "resume_gaps": resume_gaps,
        "hiring_risks": hiring_risks,
        "history_context": history_context,
        "history_risk": history_risk,
        "job_radar_id": job_radar_id,
        "eligibility_status": eligibility_status,
        "eligibility_reasons": eligibility_reasons,
    }


def write_report_snapshot_file(
    snapshot_path: Path,
    *,
    generated_at: str,
    top_matches: list[dict[str, object]] | None = None,
    review_needed: list[dict[str, object]] | None = None,
    tracked_applications: list[dict[str, object]] | None = None,
    new_jobs: list[dict[str, object]] | None = None,
    passed_not_recommended: list[dict[str, object]] | None = None,
    collector_errors: list[dict[str, str]] | None = None,
    new_jobs_count: int | None = None,
) -> None:
    top_matches = top_matches or []
    review_needed = review_needed or []
    tracked_applications = tracked_applications or []
    new_jobs = new_jobs or []
    passed_not_recommended = passed_not_recommended or []
    collector_errors = collector_errors or []

    snapshot_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "summary": {
                    "generated_at": generated_at,
                    "top_matches": len(top_matches),
                    "review_needed": len(review_needed),
                    "tracked_applications": len(tracked_applications),
                    "new_jobs": (
                        len(new_jobs)
                        if new_jobs_count is None
                        else new_jobs_count
                    ),
                    "collector_errors": len(collector_errors),
                },
                "top_matches": top_matches,
                "review_needed": review_needed,
                "tracked_applications": tracked_applications,
                "new_jobs": new_jobs,
                "passed_not_recommended": passed_not_recommended,
                "collector_errors": collector_errors,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def test_tracker_page_lists_tracked_applications(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    initialize_database(database_file)
    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-example-mobility-12345678",
            company_name="Example Mobility",
            role_title="Senior Site Reliability Engineer",
            source_url="https://example.com/jobs/example-mobility-sre",
            status="applied",
            follow_up_on="2099-07-10",
            applied_on="2026-07-03",
            last_activity_on="2026-07-05",
            outcome="Interviewing",
            notes="Applied through company site.",
        ),
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/tracker")
    html = response.get_data(as_text=True)
    normalized_html = " ".join(html.split())

    assert response.status_code == 200
    assert "Active Applications" in html
    assert "Applications shown:</strong> 1" in html
    assert "Active Applications summary" in html
    assert "Total tracked" in html
    assert "Needs action" in html
    assert "Needs review" in html
    assert "Active pipeline" in html
    assert "Closed" in html
    assert 'class="tracker-summary-card is-active"' in html
    assert "filter=needs_action" in html
    assert "filter=needs_review" in html
    assert "filter=active" in html
    assert "filter=closed" in html
    assert "Example Mobility" in html
    assert "Senior Site Reliability Engineer" in html
    assert "Applied" in html
    assert "Waiting" in html
    assert "workflow-badge workflow-follow_up_scheduled" in html
    assert "2026-07-03" in html
    assert "2026-07-05" in html
    assert "2099-07-10" in html
    assert "Interview Scheduled" in html
    assert "outcome-cell" in html
    assert "jr-example-mobility-12345678" in html
    assert 'href="/tracker/jr-example-mobility-12345678/edit?filter=all"' in normalized_html
    assert ">Open</a>" in normalized_html


def test_tracker_page_summarizes_workflow_counts(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    initialize_database(database_file)

    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-action-12345678",
            company_name="ActionCo",
            role_title="SRE",
            status="Applied",
            follow_up_on="2026-01-01",
            applied_on="2026-01-01",
            outcome="Pending / In Progress",
        ),
    )
    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-review-12345678",
            company_name="ReviewCo",
            role_title="Platform Engineer",
            status="Applied",
            applied_on="2025-01-01",
            outcome="Pending / In Progress",
        ),
    )
    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-active-12345678",
            company_name="ActiveCo",
            role_title="Infrastructure Engineer",
            status="Applied",
            applied_on="2026-01-01",
            outcome="Interview Scheduled",
        ),
    )
    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-closed-12345678",
            company_name="ClosedCo",
            role_title="Linux Engineer",
            status="rejected",
            outcome="Rejected - No Interview",
        ),
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/tracker")
    html = response.get_data(as_text=True)
    normalized_html = " ".join(html.split())

    assert response.status_code == 200
    assert "Active Applications summary" in html
    assert '<a class="tracker-summary-card is-active" href="/tracker?filter=all' in normalized_html
    assert '<strong>4</strong> <span class="muted">Total tracked</span>' in normalized_html
    assert '<a class="tracker-summary-card is-action " href="/tracker?filter=needs_action' in normalized_html
    assert '<strong>2</strong> <span class="muted">Needs action</span>' in normalized_html
    assert 'href="/tracker?filter=needs_review' in normalized_html
    assert '<strong>1</strong> <span class="muted">Needs review</span>' in normalized_html
    assert 'href="/tracker?filter=active' in normalized_html
    assert '<strong>3</strong> <span class="muted">Active pipeline</span>' in normalized_html
    assert 'href="/tracker?filter=closed' in normalized_html
    assert '<strong>1</strong> <span class="muted">Closed</span>' in normalized_html


def test_tracker_page_handles_empty_tracker(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/tracker")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Active Applications" in html
    assert "Applications shown:</strong> 0" in html
    assert "No tracked applications." in html


def test_tracker_trailing_slash_redirects_to_tracker(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/tracker/?filter=needs_action")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/tracker?filter=needs_action")


def test_index_page_links_to_history_archive(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    mark_existing_installation(database_file)

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'href="/history"' in html
    assert "Application History" in html
    assert "Active Applications dashboard" in html
    assert "Tracked applications" in html
    assert "Need action" in html
    assert "Need review" in html
    assert "Active pipeline" in html
    assert "Closed" in html
    assert "Latest scan" in html
    assert "Needs attention" in html
    assert "Support Junior" in html
    assert "Donations never change" in html
    assert (
        'href="mailto:claytonmgraves@outlook.com?subject=My%20Junior%20story"'
        in html
    )
    assert 'href="https://account.venmo.com/u/LordGraves"' in html
    assert 'rel="noopener noreferrer"' in html


def test_index_page_shows_tracker_dashboard_counts(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    initialize_database(database_file)

    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-action-12345678",
            company_name="ActionCo",
            role_title="SRE",
            status="Applied",
            follow_up_on="2026-01-01",
            applied_on="2026-01-01",
            outcome="Pending / In Progress",
        ),
    )
    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-active-12345678",
            company_name="ActiveCo",
            role_title="Infrastructure Engineer",
            status="Applied",
            applied_on="2026-01-01",
            outcome="Interview Scheduled",
        ),
    )
    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-closed-12345678",
            company_name="ClosedCo",
            role_title="Linux Engineer",
            status="rejected",
            outcome="Rejected - No Interview",
        ),
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/")
    html = response.get_data(as_text=True)
    normalized_html = " ".join(html.split())

    assert response.status_code == 200
    assert "Active Applications dashboard" in html
    assert '<a class="dashboard-card" href="/tracker?filter=all">' in normalized_html
    assert '<strong>3</strong> <span class="muted">Tracked applications</span>' in normalized_html
    assert '<a class="dashboard-card is-action" href="/tracker?filter=needs_action">' in normalized_html
    assert '<strong>2</strong> <span class="muted">Need action</span>' in normalized_html
    assert '<a class="dashboard-card" href="/tracker?filter=needs_review">' in normalized_html
    assert '<strong>0</strong> <span class="muted">Need review</span>' in normalized_html
    assert '<a class="dashboard-card" href="/tracker?filter=active">' in normalized_html
    assert '<strong>2</strong> <span class="muted">Active pipeline</span>' in normalized_html
    assert '<a class="dashboard-card" href="/tracker?filter=closed">' in normalized_html
    assert '<strong>1</strong> <span class="muted">Closed</span>' in normalized_html
    assert "Latest scan" in html
    assert "Top Matches" in html
    assert "Review Needed" in html
    assert "Tracked Applications" in html
    assert "New Jobs" in html
    assert "Collector Errors" in html
    assert "Needs attention" in html
    assert "ActionCo — SRE" in html
    assert 'href="/tracker/jr-action-12345678/edit?filter=needs_review"' in html


def test_index_page_surfaces_dashboard_follow_up_work(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    initialize_database(database_file)

    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-due-12345678",
            company_name="DueCo",
            role_title="Linux Engineer",
            status="Applied",
            follow_up_on="2026-01-01",
            applied_on="2026-01-01",
            outcome="Pending / In Progress",
        ),
    )
    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-date-review-12345678",
            company_name="ReviewCo",
            role_title="Platform Engineer",
            status="Applied",
            follow_up_on="not-a-date",
            applied_on="2026-01-02",
            outcome="Pending / In Progress",
        ),
    )
    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-dormant-12345678",
            company_name="DormantCo",
            role_title="Infrastructure Engineer",
            status="Applied",
            applied_on="2026-01-03",
            outcome="Dormant",
        ),
    )
    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-active-12345678",
            company_name="ActiveCo",
            role_title="Senior SRE",
            status="Applied",
            applied_on="2026-01-04",
            outcome="Interview Scheduled",
        ),
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "What do I need to act on today?" not in html
    assert "Dashboard overview" in html
    assert "Needs attention" in html
    assert "DueCo — Linux Engineer" in html
    assert "Follow-up: 2026-01-01" in html
    assert "ReviewCo — Platform Engineer" in html
    assert "Follow-up: not-a-date" in html
    assert "DormantCo — Infrastructure Engineer" in html
    assert "ActiveCo — Senior SRE" not in html
    assert 'href="/tracker/jr-due-12345678/edit?filter=needs_review"' in html
    assert 'href="/tracker/jr-date-review-12345678/edit?filter=needs_review"' in html
    assert 'href="/tracker/jr-dormant-12345678/edit?filter=needs_review"' in html


def test_index_page_summarizes_latest_scan_report(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"
    reports_path = tmp_path / "reports"

    reports_path.mkdir()
    write_settings_file(settings_file, database_file, reports_path=reports_path)
    mark_existing_installation(database_file)

    (reports_path / "target-scan.html").write_text(
        "<html><body><h1>Job Radar Report</h1></body></html>",
        encoding="utf-8",
    )
    write_report_snapshot_file(
        reports_path / "target-scan.json",
        generated_at="2026-07-11T11:57:00+00:00",
        top_matches=[
            make_report_snapshot_job(
                title="Site Reliability Engineer",
                url="https://example.com/top",
                company="Example",
            )
        ],
        review_needed=[
            make_report_snapshot_job(
                title="Senior Systems Software Engineer, GPU Compute",
                url="https://example.com/review-one",
                company="Example",
            ),
            make_report_snapshot_job(
                title="Hardware Operations Engineer",
                url="https://example.com/review-two",
                company="Example",
            ),
        ],
        tracked_applications=[
            make_report_snapshot_job(
                title="Site Reliability Engineer",
                url="https://example.com/tracked",
                company="Example",
            )
        ],
        new_jobs_count=3,
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/")
    html = response.get_data(as_text=True)
    normalized_html = " ".join(html.split())

    assert response.status_code == 200
    assert "Generated at 2026-07-11 11:57 UTC" in html
    assert '<a href="/reports/view/target-scan.html">Open HTML report</a>' in html
    assert '<a class="scan-card" href="/reports/section/top_matches">' in normalized_html
    assert '<strong>1</strong> <span class="muted">Top Matches</span>' in normalized_html
    assert '<a class="scan-card" href="/reports/section/review_needed">' in normalized_html
    assert '<strong>2</strong> <span class="muted">Review Needed</span>' in normalized_html
    assert '<a class="scan-card" href="/reports/section/tracked_applications">' in normalized_html
    assert '<strong>1</strong> <span class="muted">Tracked Applications</span>' in normalized_html
    assert '<a class="scan-card" href="/reports/section/new_jobs">' in normalized_html
    assert '<strong>3</strong> <span class="muted">New Jobs</span>' in normalized_html
    assert "Actionable stored" not in html
    assert '<a class="scan-card" href="/reports/section/collector_errors">' in normalized_html
    assert '<strong>0</strong> <span class="muted">Collector Errors</span>' in normalized_html


def test_report_section_view_shows_structured_job_cards_for_requested_section(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"
    reports_path = tmp_path / "reports"

    reports_path.mkdir()
    write_settings_file(settings_file, database_file, reports_path=reports_path)

    (reports_path / "target-scan.html").write_text(
        "<html><body><h1>Job Radar Report</h1></body></html>",
        encoding="utf-8",
    )
    write_report_snapshot_file(
        reports_path / "target-scan.json",
        generated_at="2026-07-11T11:57:00+00:00",
        top_matches=[
            make_report_snapshot_job(
                title="Site Reliability Engineer",
                url="https://example.com/top",
                company="ExampleCompute",
                location="Remote - USA",
                hiring_probability="High",
                recommended_action="Apply",
                action_rationale=(
                        "Clean apply: very strong role fit, very strong "
                    "resume match, high hiring probability, and no hiring risks."
                ),
                why_matched="linux, infrastructure, sre, gpu, observability",
                technical_match="Very Strong",
                resume_match="Very Strong",
                resume_evidence=(
                    "Linux infrastructure; reliability engineering"
                ),
                history_context=(
                    "Prior similar role at ExampleCompute; outcome: "
                    "Rejected - No Interview"
                ),
                history_risk="neutral: prior_similar_role",
                job_radar_id="jr-examplecompute-655a542b",
                eligibility_status="needs_review",
                eligibility_reasons=[
                    "The posting does not provide usable compensation.",
                    "The posting includes an on-call requirement.",
                ],
            )
        ],
        review_needed=[
            make_report_snapshot_job(
                title="Hardware Operations Engineer",
                url="https://example.com/review",
                company="Example Labs",
                location="Remote - US",
                recommended_action="Network First",
            )
        ],
        tracked_applications=[
            make_report_snapshot_job(
                title="Tracked SRE",
                url="https://example.com/tracked",
                company="ExampleCloud",
            )
        ],
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/reports/section/top_matches")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Top Matches" in html
    assert "Cleanest roles from the latest scan" in html
    assert "ExampleCompute" in html
    assert "Site Reliability Engineer" in html
    assert "Remote - USA" in html
    assert "Hiring probability: High" in html
    assert "Eligibility: Needs Review" in html
    assert "Eligibility summary" in html
    assert "Needs Review: 1" in html
    assert "Eligibility review" in html
    assert "The posting does not provide usable compensation." in html
    assert "The posting includes an on-call requirement." in html
    assert "Recommended action" in html
    assert "Apply" in html
    assert "Why this is worth acting on" in html
    assert "Clean apply: very strong role fit" in html
    assert "Matched because" in html
    assert "linux, infrastructure, sre, gpu, observability" in html
    assert "Role fit" in html
    assert "Very Strong" in html
    assert "Resume evidence" in html
    assert "Linux infrastructure; reliability engineering" in html
    assert "History context" in html
    assert "Prior similar role at ExampleCompute" in html
    assert "Job Radar ID" not in html
    assert 'target="_blank" rel="noopener noreferrer"' in html
    assert "I applied" in html
    assert "Save for later" in html
    assert "Pass" in html
    assert "show again" in html
    assert "/tracker/add?" in html
    assert "job_radar_id=jr-examplecompute-655a542b" in html
    assert "company_name=ExampleCompute" in html
    assert "role_title=Site+Reliability+Engineer" in html
    assert "source_url=https://example.com/top" in html
    assert "status=Applied" in html
    assert "outcome=Pending+%2F+In+Progress" in html or "outcome=Pending+/+In+Progress" in html
    assert "jr-examplecompute-655a542b" in html
    assert "Score: 122" not in html
    assert "score 122 meets top-match threshold 120" not in html
    assert "Work location fit" not in html
    assert "Canonical key" not in html
    assert "Hardware Operations Engineer" not in html
    assert "Tracked SRE" not in html


def test_review_needed_job_can_be_passed_without_creating_application(
    tmp_path: Path,
) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"
    reports_path = tmp_path / "reports"
    reports_path.mkdir()
    write_settings_file(
        settings_file,
        database_file,
        reports_path=reports_path,
    )
    profile = ManagedProfile(
        profile_id="profile_33333333",
        display_name="Synthetic reviewer",
    )
    create_profile(database_file, profile)
    set_active_profile(database_file, profile.profile_id)
    write_report_snapshot_file(
        reports_path / "target-scan.json",
        generated_at="2026-07-24T10:00:00+00:00",
        review_needed=[
            make_report_snapshot_job(
                title="Synthetic Systems Role",
                url="https://example.invalid/jobs/review",
                company="Synthetic Company",
                location="Remote",
                job_radar_id="jr-synthetic-12345678",
            )
        ],
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()
    response = client.post(
        "/reports/jobs/jr-synthetic-12345678/decision",
        data={
            "section_name": "review_needed",
            "decision": DECISION_PASSED,
        },
    )

    assert response.status_code == 302
    decisions = list_job_decisions(
        database_file,
        profile_id=profile.profile_id,
        decision=DECISION_PASSED,
    )
    assert len(decisions) == 1
    assert decisions[0].title == "Synthetic Systems Role"
    assert list_applications(
        database_file,
        profile_id=profile.profile_id,
    ) == []
    refreshed_html = client.get(
        "/reports/section/review_needed",
    ).get_data(as_text=True)
    assert 'href="https://example.invalid/jobs/review"' not in refreshed_html

    workspace_html = client.get("/job-decisions").get_data(as_text=True)
    assert "Reviewed and passed" in workspace_html
    assert "Synthetic Systems Role" in workspace_html
    assert "Allow in future scans" in workspace_html


def test_saved_job_moves_out_of_bookmarks_when_application_is_created(
    tmp_path: Path,
) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"
    write_settings_file(settings_file, database_file)
    profile = ManagedProfile(
        profile_id="profile_55555555",
        display_name="Synthetic applicant",
    )
    create_profile(database_file, profile)
    set_active_profile(database_file, profile.profile_id)
    save_job_decision(
        database_file,
        profile_id=profile.profile_id,
        job_radar_id="jr-synthetic-87654321",
        decision=DECISION_SAVED,
        company="Synthetic Company",
        title="Synthetic Role",
        source_url="https://example.invalid/jobs/apply",
        location="Remote",
    )
    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.post(
        "/tracker/add",
        data={
            "job_radar_id": "jr-synthetic-87654321",
            "company_name": "Synthetic Company",
            "role_title": "Synthetic Role",
            "source_url": "https://example.invalid/jobs/apply",
            "status": "Applied",
            "outcome": "Pending / In Progress",
            "applied_on": "2026-07-24",
            "follow_up_on": "",
            "last_activity_on": "2026-07-24",
            "notes": "",
        },
    )

    assert response.status_code == 302
    assert list_job_decisions(
        database_file,
        profile_id=profile.profile_id,
    ) == []
    application = get_application(
        database_file,
        "jr-synthetic-87654321",
        profile_id=profile.profile_id,
    )
    assert application is not None


def test_report_section_view_shows_new_jobs_from_latest_scan(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"
    reports_path = tmp_path / "reports"

    reports_path.mkdir()
    write_settings_file(settings_file, database_file, reports_path=reports_path)

    (reports_path / "target-scan.html").write_text(
        "<html><body><h1>Job Radar Report</h1></body></html>",
        encoding="utf-8",
    )
    write_report_snapshot_file(
        reports_path / "target-scan.json",
        generated_at="2026-07-14T14:20:00+00:00",
        new_jobs=[
            make_report_snapshot_job(
                title="Senior Linux Infrastructure Engineer",
                url="https://example.com/new-job",
                company="NewCo",
                location="Remote - USA",
                compensation="$180,000 - $220,000",
                hiring_probability="Medium",
                recommended_action="Tailor Resume",
                action_rationale=(
                    "Strong infrastructure fit, but the resume should "
                    "emphasize large-scale Linux operations."
                ),
                why_matched=(
                    "linux, infrastructure, automation, reliability"
                ),
                technical_match="Very Strong",
                resume_match="Strong",
                resume_evidence=(
                    "Large-scale Linux; Ansible; infrastructure reliability"
                ),
                resume_gaps="Production Kubernetes",
                hiring_risks="Production Kubernetes translation",
                job_radar_id="jr-newco-12345678",
            )
        ],
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/reports/section/new_jobs")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "New Jobs" in html
    assert "Actionable roles first discovered during the latest scan." in html
    assert "NewCo" in html
    assert "Senior Linux Infrastructure Engineer" in html
    assert "Remote - USA" in html
    assert "$180,000 - $220,000" in html
    assert "Hiring probability: Medium" in html
    assert "Eligibility: Not Evaluated" in html
    assert "Not Evaluated: 1" in html
    assert "Eligibility review" not in html
    assert "Tailor Resume" in html
    assert "Strong infrastructure fit" in html
    assert "linux, infrastructure, automation, reliability" in html
    assert "Production Kubernetes translation" in html
    assert "I applied" in html
    assert "job_radar_id=jr-newco-12345678" in html
    assert "source_url=https://example.com/new-job" in html


def test_report_section_view_shows_collector_errors_and_clean_empty_state(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"
    reports_path = tmp_path / "reports"

    reports_path.mkdir()
    write_settings_file(settings_file, database_file, reports_path=reports_path)

    (reports_path / "target-scan.html").write_text(
        "<html><body><h1>Job Radar Report</h1></body></html>",
        encoding="utf-8",
    )
    snapshot_path = reports_path / "target-scan.json"
    write_report_snapshot_file(
        snapshot_path,
        generated_at="2026-07-14T14:20:00+00:00",
        collector_errors=[
            {
                "company_key": "example-company",
                "company_name": "Example Company",
                "source_type": "greenhouse",
                "message": (
                    "Request timed out while contacting the job board."
                ),
            }
        ],
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/reports/section/collector_errors")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Collector Errors" in html
    assert "Company sources that could not be collected successfully during the latest scan." in html
    assert "Example Company" in html
    assert "greenhouse" in html
    assert "Request timed out while contacting the job board." in html
    assert "example-company" in html
    assert "Track this application" not in html


    write_report_snapshot_file(
        snapshot_path,
        generated_at="2026-07-14T15:00:00+00:00",
    )

    empty_response = client.get("/reports/section/collector_errors")
    empty_html = empty_response.get_data(as_text=True)

    assert empty_response.status_code == 200
    assert "No collector errors were reported in the latest scan." in empty_html
    assert "Example Company" not in empty_html


def test_report_section_view_rejects_unknown_section(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/reports/section/unknown")

    assert response.status_code == 404


def test_tracker_add_prefills_from_report_card_query_params(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get(
        "/tracker/add",
        query_string={
            "job_radar_id": "jr-examplecompute-655a542b",
            "company_name": "ExampleCompute",
            "role_title": "Site Reliability Engineer",
            "source_url": "https://example.com/top",
            "status": "Applied",
            "outcome": "Pending / In Progress",
            "applied_on": "2026-07-11",
        },
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'id="job_radar_id" name="job_radar_id" value="jr-examplecompute-655a542b" readonly' in html
    assert 'id="company_name" name="company_name" value="ExampleCompute" required' in html
    assert 'id="role_title" name="role_title" value="Site Reliability Engineer" required' in html
    assert 'id="source_url" name="source_url" value="https://example.com/top"' in html
    assert '<option value="Applied" selected>' in html
    assert '<option value="Pending / In Progress" selected>' in html
    assert 'id="applied_on" name="applied_on" type="date" value="2026-07-11"' in html
    assert 'id="follow_up_on" name="follow_up_on" type="date" value=""' in html
    assert 'id="last_activity_on" name="last_activity_on" type="date" value=""' in html


def test_tracker_add_saves_prefilled_scan_job_radar_id(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.post(
        "/tracker/add",
        data={
            "job_radar_id": "jr-examplecompute-655a542b",
            "company_name": "ExampleCompute",
            "role_title": "Site Reliability Engineer",
            "source_url": "https://example.com/top",
            "status": "Applied",
            "outcome": "Pending / In Progress",
            "applied_on": "2026-07-11",
            "follow_up_on": "",
            "last_activity_on": "",
            "notes": "",
        },
    )

    assert response.status_code == 302

    application = get_application(database_file, "jr-examplecompute-655a542b")

    assert application is not None
    assert application.company_name == "ExampleCompute"
    assert application.role_title == "Site Reliability Engineer"
    assert application.source_url == "https://example.com/top"
    assert application.status == "Applied"
    assert application.outcome == "Pending / In Progress"
    assert application.applied_on == "2026-07-11"


def test_history_page_lists_imported_history_records(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    initialize_database(database_file)
    upsert_job_history_record(
        database_file,
        JobHistoryRecord(
            history_type="Reviewed",
            company="ArchiveCo",
            role="Senior Linux Engineer",
            source="LinkedIn",
            ats_platform=None,
            work_arrangement=None,
            location=None,
            comp_range=None,
            event_date="2026-07-01",
            status="Skipped",
            outcome_category="Skipped / Avoid",
            recruiter_contact="Example Recruiter",
            technical_match=None,
            hiring_probability=None,
            skills_signals=None,
            primary_blocker=None,
            secondary_blocker=None,
            revisit=None,
            include_in_job_radar=True,
            import_key="manual:archiveco:senior-linux-engineer",
            notes="Skipped because the role was onsite outside target area.",
        ),
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/history")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Application History" in html
    assert "History records shown:</strong> 1" in html
    assert "Archive summary" in html
    assert "Total archived" in html
    assert "Applied records" in html
    assert "Passed records" in html
    assert "Rejected records" in html
    assert "Withdrawn records" in html
    assert "Closed before apply" in html
    assert "history-summary-card" in html
    assert 'href="/history?quick_filter=applied"' in html
    assert 'href="/history?quick_filter=passed"' in html
    assert 'href="/history?quick_filter=rejected"' in html
    assert 'href="/history?quick_filter=withdrawn"' in html
    assert 'href="/history?quick_filter=closed_before_application"' in html
    assert "history-chip" in html
    assert "ArchiveCo" in html
    assert "Senior Linux Engineer" in html
    assert "Skipped" in html
    assert "Skipped / Avoid" in html
    assert "outcome-cell" in html
    assert 'href="/history/manual:archiveco:senior-linux-engineer/edit"' in html
    assert ">Open</a>" in html
    assert "LinkedIn" not in html
    assert "Example Recruiter" not in html
    assert "Skipped because the role was onsite outside target area." not in html
    assert "Viewing these records does not add them to Active Applications." in html


def test_history_page_sorts_by_company_status_role_outcome_and_date(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    initialize_database(database_file)

    upsert_job_history_record(
        database_file,
        JobHistoryRecord(
            history_type="Reviewed",
            company="ZetaCo",
            role="Linux Engineer",
            source="LinkedIn",
            ats_platform=None,
            work_arrangement=None,
            location=None,
            comp_range=None,
            event_date="2026-06-01",
            status="Passed",
            outcome_category="N/A",
            recruiter_contact=None,
            technical_match=None,
            hiring_probability=None,
            skills_signals=None,
            primary_blocker=None,
            secondary_blocker=None,
            revisit=None,
            include_in_job_radar=True,
            import_key="manual:zetaco:linux-engineer",
            notes=None,
        ),
    )
    upsert_job_history_record(
        database_file,
        JobHistoryRecord(
            history_type="Pipeline",
            company="AlphaCo",
            role="Platform Engineer",
            source="Job Radar",
            ats_platform=None,
            work_arrangement=None,
            location=None,
            comp_range=None,
            event_date="2026-07-01",
            status="Withdrawn",
            outcome_category="Withdrawn",
            recruiter_contact=None,
            technical_match=None,
            hiring_probability=None,
            skills_signals=None,
            primary_blocker=None,
            secondary_blocker=None,
            revisit=None,
            include_in_job_radar=True,
            import_key="manual:alphaco:platform-engineer",
            notes=None,
        ),
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    default_response = client.get("/history")
    default_html = default_response.get_data(as_text=True)
    assert default_response.status_code == 200
    assert '<option value="event_desc" selected>' in default_html
    assert default_html.index("AlphaCo") < default_html.index("ZetaCo")

    date_asc_response = client.get("/history?sort=event_asc")
    date_asc_html = date_asc_response.get_data(as_text=True)
    assert date_asc_response.status_code == 200
    assert '<option value="event_asc" selected>' in date_asc_html
    assert date_asc_html.index("ZetaCo") < date_asc_html.index("AlphaCo")

    company_response = client.get("/history?sort=company")
    company_html = company_response.get_data(as_text=True)
    assert company_response.status_code == 200
    assert '<option value="company" selected>' in company_html
    assert company_html.index("AlphaCo") < company_html.index("ZetaCo")

    role_response = client.get("/history?sort=role")
    role_html = role_response.get_data(as_text=True)
    assert role_response.status_code == 200
    assert '<option value="role" selected>' in role_html
    assert role_html.index("Linux Engineer") < role_html.index("Platform Engineer")

    status_response = client.get("/history?sort=status")
    status_html = status_response.get_data(as_text=True)
    assert status_response.status_code == 200
    assert '<option value="status" selected>' in status_html
    assert status_html.index("ZetaCo") < status_html.index("AlphaCo")

    outcome_response = client.get("/history?sort=outcome")
    outcome_html = outcome_response.get_data(as_text=True)
    assert outcome_response.status_code == 200
    assert '<option value="outcome" selected>' in outcome_html
    assert outcome_html.index("ZetaCo") < outcome_html.index("AlphaCo")


def test_history_page_searches_and_filters_records(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    initialize_database(database_file)

    upsert_job_history_record(
        database_file,
        JobHistoryRecord(
            history_type="Pipeline",
            company="Example Hosting",
            role="HPC Solutions Engineer",
            source="Recruiter",
            ats_platform=None,
            work_arrangement=None,
            location=None,
            comp_range=None,
            event_date="2026-07-01",
            status="Applied",
            outcome_category="Pending / In Progress",
            recruiter_contact="Hydra Recruiter",
            technical_match=None,
            hiring_probability=None,
            skills_signals=None,
            primary_blocker=None,
            secondary_blocker=None,
            revisit=None,
            include_in_job_radar=True,
            import_key="manual:example-hosting:hpc-solutions-engineer",
            notes="Strong InfiniBand and Slurm fit.",
        ),
    )
    upsert_job_history_record(
        database_file,
        JobHistoryRecord(
            history_type="Reviewed",
            company="SkipCo",
            role="Desktop Support Engineer",
            source="LinkedIn",
            ats_platform=None,
            work_arrangement=None,
            location=None,
            comp_range=None,
            event_date="2026-06-01",
            status="Passed",
            outcome_category="Closed Before Application",
            recruiter_contact=None,
            technical_match=None,
            hiring_probability=None,
            skills_signals=None,
            primary_blocker=None,
            secondary_blocker=None,
            revisit=None,
            include_in_job_radar=True,
            import_key="manual:skipco:desktop-support-engineer",
            notes="Wrong role family.",
        ),
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    search_response = client.get("/history?q=infiniband")
    search_html = search_response.get_data(as_text=True)

    assert search_response.status_code == 200
    assert "History records shown:</strong> 1" in search_html
    assert "Example Hosting" in search_html
    assert "SkipCo" not in search_html
    assert 'value="infiniband"' in search_html

    filter_response = client.get(
        "/history",
        query_string={
            "decision_filter": "Passed",
            "outcome_filter": "Closed Before Application",
            "sort": "company",
        },
    )
    filter_html = filter_response.get_data(as_text=True)

    assert filter_response.status_code == 200
    assert "History records shown:</strong> 1" in filter_html
    assert "SkipCo" in filter_html
    assert "Example Hosting" not in filter_html
    assert '<option value="Applied"' in filter_html
    assert '<option value="Passed" selected>' in filter_html
    assert '<option value="Withdrawn"' in filter_html
    assert '<option value="Revisit"' in filter_html
    assert "history-outcome-filter" in filter_html
    assert '<option value="Closed Before Application" selected>' in filter_html
    assert '<option value="Rejected - No Interview"' in filter_html
    assert '<option value="Rejected - After Interview"' in filter_html
    assert '<option value="Withdrawn"' in filter_html
    assert '<option value="N/A"' in filter_html
    assert "Pending / In Progress" not in filter_html
    assert "Interview Scheduled" not in filter_html
    assert "Interview Completed" not in filter_html
    assert "Waiting For Feedback" not in filter_html
    assert "Offer" not in filter_html
    assert "Dormant" not in filter_html
    assert '<option value="company" selected>' in filter_html
    assert "Clear search/filters/sort" in filter_html


def test_history_page_summary_cards_apply_filters(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    initialize_database(database_file)

    upsert_job_history_record(
        database_file,
        JobHistoryRecord(
            history_type="Pipeline",
            company="RejectCo",
            role="SRE",
            source="Job Radar",
            ats_platform=None,
            work_arrangement=None,
            location=None,
            comp_range=None,
            event_date="2026-07-01",
            status="Applied",
            outcome_category="Rejected - No Interview",
            recruiter_contact=None,
            technical_match=None,
            hiring_probability=None,
            skills_signals=None,
            primary_blocker=None,
            secondary_blocker=None,
            revisit=None,
            include_in_job_radar=True,
            import_key="manual:rejectco:sre",
            notes=None,
        ),
    )
    upsert_job_history_record(
        database_file,
        JobHistoryRecord(
            history_type="Reviewed",
            company="PassCo",
            role="Support Engineer",
            source="LinkedIn",
            ats_platform=None,
            work_arrangement=None,
            location=None,
            comp_range=None,
            event_date="2026-06-01",
            status="Passed",
            outcome_category="Closed Before Application",
            recruiter_contact=None,
            technical_match=None,
            hiring_probability=None,
            skills_signals=None,
            primary_blocker=None,
            secondary_blocker=None,
            revisit=None,
            include_in_job_radar=True,
            import_key="manual:passco:support-engineer",
            notes=None,
        ),
    )
    upsert_job_history_record(
        database_file,
        JobHistoryRecord(
            history_type="Pipeline",
            company="WithdrawCo",
            role="Platform Engineer",
            source="Job Radar Tracker",
            ats_platform=None,
            work_arrangement=None,
            location=None,
            comp_range=None,
            event_date="2026-05-01",
            status="Withdrawn",
            outcome_category="N/A",
            recruiter_contact=None,
            technical_match=None,
            hiring_probability=None,
            skills_signals=None,
            primary_blocker=None,
            secondary_blocker=None,
            revisit=None,
            include_in_job_radar=True,
            import_key="manual:withdrawco:platform-engineer",
            notes=None,
        ),
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    passed_response = client.get("/history?quick_filter=passed")
    passed_html = passed_response.get_data(as_text=True)

    assert passed_response.status_code == 200
    assert "History records shown:</strong> 1" in passed_html
    assert "PassCo" in passed_html
    assert "RejectCo" not in passed_html
    assert '<option value="Passed" selected>' in passed_html
    assert "is-active" in passed_html

    rejected_response = client.get("/history?quick_filter=rejected")
    rejected_html = rejected_response.get_data(as_text=True)

    assert rejected_response.status_code == 200
    assert "History records shown:</strong> 1" in rejected_html
    assert "RejectCo" in rejected_html
    assert "PassCo" not in rejected_html
    assert "WithdrawCo" not in rejected_html
    assert "Rejected records" in rejected_html
    assert "is-active" in rejected_html

    withdrawn_response = client.get("/history?quick_filter=withdrawn")
    withdrawn_html = withdrawn_response.get_data(as_text=True)

    assert withdrawn_response.status_code == 200
    assert "History records shown:</strong> 1" in withdrawn_html
    assert "WithdrawCo" in withdrawn_html
    assert "RejectCo" not in withdrawn_html
    assert "PassCo" not in withdrawn_html
    assert '<option value="Withdrawn" selected>' in withdrawn_html


def test_history_page_rejects_unknown_quick_filter(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/history?quick_filter=unknown")

    assert response.status_code == 404


def test_history_page_rejects_unknown_sort(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/history?sort=unknown")

    assert response.status_code == 404


def test_history_page_handles_empty_history(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/history")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Application History" in html
    assert "History records shown:</strong> 0" in html
    assert "No application history records." in html


def test_profile_page_shows_resume_upload_form(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"
    profile_file = tmp_path / "profile.yaml"
    resume_file = tmp_path / "resume.md"
    normalized_resume_file = tmp_path / "resume.normalized.txt"

    write_settings_file(settings_file, database_file)
    settings_file.write_text(
        settings_file.read_text(encoding="utf-8")
        + f"candidate_profile_path: {profile_file}\n",
        encoding="utf-8",
    )
    profile_file.write_text(
        f"""
candidate:
  name: Example Candidate
  resume:
    source_path: {resume_file}
    normalized_text_path: {normalized_resume_file}
  core_strengths:
    - Linux infrastructure
  credible_adjacent: []
  learning_or_gap: []
  avoid: []
""",
        encoding="utf-8",
    )
    resume_file.write_text("Linux infrastructure", encoding="utf-8")

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/profile/legacy/edit")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Replace résumé" in html
    assert "Current résumé" in html
    assert "resume.md" in html
    assert "Back to profile summary" in html
    assert "Cancel" in html
    assert 'enctype="multipart/form-data"' in html
    assert 'accept=".md,.txt,.pdf,.docx"' in html
    assert "Save résumé" in html
    assert "Supported formats: .md, .txt, .pdf, and .docx." in html
    assert "Selecting a file does not change anything until you press Save résumé" in html


def test_profile_resume_upload_updates_resume_and_normalized_text(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"
    profile_file = tmp_path / "profile.yaml"
    resume_file = tmp_path / "resume.md"
    normalized_resume_file = tmp_path / "resume.normalized.txt"

    write_settings_file(settings_file, database_file)
    settings_file.write_text(
        settings_file.read_text(encoding="utf-8")
        + f"candidate_profile_path: {profile_file}\n",
        encoding="utf-8",
    )
    profile_file.write_text(
        f"""
candidate:
  name: Example Candidate
  resume:
    source_path: {resume_file}
    normalized_text_path: {normalized_resume_file}
  core_strengths:
    - Linux infrastructure
  credible_adjacent: []
  learning_or_gap: []
  avoid: []
""",
        encoding="utf-8",
    )
    resume_file.write_text("Old resume", encoding="utf-8")

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.post(
        "/profile/resume",
        data={
            "resume_file": (
                BytesIO(b"# Updated Resume\n\nLinux infrastructure and HPC operations"),
                "resume.md",
            )
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Resume updated." in html
    assert resume_file.read_text(encoding="utf-8") == (
        "# Updated Resume\n\nLinux infrastructure and HPC operations"
    )
    assert normalized_resume_file.read_text(encoding="utf-8") == (
        "# Updated Resume Linux infrastructure and HPC operations\n"
    )
    assert "# Updated Resume" in html
    assert "Linux infrastructure and HPC operations" in html


def test_profile_resume_upload_rejects_unsupported_file_type(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"
    profile_file = tmp_path / "profile.yaml"
    resume_file = tmp_path / "resume.md"
    normalized_resume_file = tmp_path / "resume.normalized.txt"

    write_settings_file(settings_file, database_file)
    settings_file.write_text(
        settings_file.read_text(encoding="utf-8")
        + f"candidate_profile_path: {profile_file}\n",
        encoding="utf-8",
    )
    profile_file.write_text(
        f"""
candidate:
  name: Example Candidate
  resume:
    source_path: {resume_file}
    normalized_text_path: {normalized_resume_file}
  core_strengths:
    - Linux infrastructure
  credible_adjacent: []
  learning_or_gap: []
  avoid: []
""",
        encoding="utf-8",
    )
    resume_file.write_text("Old resume", encoding="utf-8")

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.post(
        "/profile/resume",
        data={
            "resume_file": (
                BytesIO(b"name,experience"),
                "resume.csv",
            )
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Resume upload failed:" in html
    assert "Unsupported resume format: .csv" in html
    assert resume_file.read_text(encoding="utf-8") == "Old resume"


def test_index_page_links_to_scan(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    mark_existing_installation(database_file)

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'href="/scan"' in html
    assert ">Scan</a>" in html


def test_index_page_links_to_settings(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    mark_existing_installation(database_file)

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'href="/settings"' in html
    assert ">Settings</a>" in html


def test_index_page_links_to_companies(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    mark_existing_installation(database_file)

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'href="/companies"' in html
    assert ">Companies</a>" in html


def test_companies_page_requires_profile_instead_of_showing_legacy_yaml(tmp_path: Path, monkeypatch) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"
    companies_file = tmp_path / "config" / "target-companies.yaml"

    write_settings_file(settings_file, database_file)
    companies_file.parent.mkdir()
    monkeypatch.chdir(tmp_path)
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
    name: Example Federal Agency
    source_type: usajobs
    enabled: true
    query_params:
      Organization: NN
""",
        encoding="utf-8",
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/companies")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Companies" in html
    assert "Create or select a profile first" in html
    assert "Legacy YAML company files are no longer displayed" in html
    assert 'href="/profile"' in html
    assert "Enabled AI" not in html
    assert str(companies_file) not in html


def test_legacy_company_filters_do_not_restore_yaml_view(tmp_path: Path, monkeypatch) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"
    companies_file = tmp_path / "config" / "target-companies.yaml"

    write_settings_file(settings_file, database_file)
    companies_file.parent.mkdir()
    monkeypatch.chdir(tmp_path)
    companies_file.write_text(
        """
companies:
  - company_key: enabled_ai
    name: Enabled AI
    source_type: greenhouse
    source_slug: enabledai
    enabled: true
  - company_key: disabled_lab
    name: Disabled Lab
    source_type: workday
    source_url: https://example.com/workday/jobs
    enabled: false
  - company_key: nasa_usajobs
    name: Example Federal Agency
    source_type: usajobs
    enabled: true
    query_params:
      Organization: NN
""",
        encoding="utf-8",
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    enabled_response = client.get("/companies?status=enabled")
    enabled_html = enabled_response.get_data(as_text=True)

    assert enabled_response.status_code == 200
    assert "Create or select a profile first" in enabled_html
    assert "Enabled AI" not in enabled_html

    disabled_response = client.get("/companies?status=disabled")
    disabled_html = disabled_response.get_data(as_text=True)

    assert disabled_response.status_code == 200
    assert "Create or select a profile first" in disabled_html

    source_response = client.get("/companies?source_type=greenhouse")
    source_html = source_response.get_data(as_text=True)

    assert source_response.status_code == 200
    assert "Create or select a profile first" in source_html

    search_response = client.get("/companies?q=organization")
    search_html = search_response.get_data(as_text=True)

    assert search_response.status_code == 200
    assert "Create or select a profile first" in search_html

    combined_response = client.get("/companies?status=enabled&source_type=usajobs&q=nn")
    combined_html = combined_response.get_data(as_text=True)

    assert combined_response.status_code == 200
    assert "Create or select a profile first" in combined_html


def test_legacy_company_detail_is_not_exposed_without_profile(tmp_path: Path, monkeypatch) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"
    companies_file = tmp_path / "config" / "target-companies.yaml"

    write_settings_file(settings_file, database_file)
    companies_file.parent.mkdir()
    monkeypatch.chdir(tmp_path)
    companies_file.write_text(
        """
companies:
  - company_key: enabled_ai
    name: Enabled AI
    source_type: greenhouse
    source_slug: enabledai
    enabled: true
    notes: Strong target.
  - company_key: nasa_usajobs
    name: Example Federal Agency
    source_type: usajobs
    enabled: true
    query_params:
      Organization: NN
""",
        encoding="utf-8",
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/companies/enabled_ai")
    assert response.status_code == 404


def test_company_detail_page_returns_404_for_missing_company(tmp_path: Path, monkeypatch) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"
    companies_file = tmp_path / "config" / "target-companies.yaml"

    write_settings_file(settings_file, database_file)
    companies_file.parent.mkdir()
    monkeypatch.chdir(tmp_path)
    companies_file.write_text(
        """
companies:
  - company_key: enabled_ai
    name: Enabled AI
    source_type: greenhouse
    source_slug: enabledai
    enabled: true
""",
        encoding="utf-8",
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/companies/missing_company")

    assert response.status_code == 404


def test_settings_page_shows_read_only_runtime_settings(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"
    reports_path = tmp_path / "reports"
    profile_file = tmp_path / "profile.yaml"

    write_settings_file(settings_file, database_file, reports_path=reports_path)
    settings_file.write_text(
        settings_file.read_text(encoding="utf-8")
        + f"candidate_profile_path: {profile_file}\n",
        encoding="utf-8",
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/settings")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Settings" in html
    assert "Runtime paths remain read-only." in html
    assert "Runtime paths" in html
    assert "Active settings file" in html
    assert f"<code class=\"settings-value\">{settings_file}</code>" in html
    assert "Database path" in html
    assert f"<code class=\"settings-value\">{database_file}</code>" in html
    assert "Reports path" in html
    assert f"<code class=\"settings-value\">{reports_path}</code>" in html
    assert "Logs path" in html
    assert f"<code class=\"settings-value\">{tmp_path}</code>" in html
    assert "Candidate profile path" in html
    assert f"<code class=\"settings-value\">{profile_file}</code>" in html
    assert "GUI scan defaults" in html
    assert "config/target-companies.yaml" in html
    assert "config/scoring.yaml" in html
    assert "reports/target-scan.html" in html
    assert "reports/target-email-preview.txt" in html
    assert "Report history" in html
    assert "Latest scan only" in html
    assert "The latest filenames remain stable." in html
    assert "Manage report and log retention" in html
    assert "report_retention_days" not in html
    assert "raw_capture_enabled" not in html
    assert "Email" in html
    assert "Disabled" in html
    assert "Secrets are not shown on this page." in html
    assert "View diagnostics" in html
    assert "Exit Junior" not in html
    assert "Save" not in html


def test_desktop_settings_requests_clean_shutdown(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"
    write_settings_file(settings_file, database_file)
    app = create_app(settings_path=str(settings_file))
    shutdown_event = threading.Event()
    app.config["JOB_RADAR_DESKTOP_SHUTDOWN_EVENT"] = shutdown_event
    client = app.test_client()

    page = client.get("/settings")
    response = client.post("/settings/shutdown")

    assert "Exit Junior" in page.get_data(as_text=True)
    assert response.status_code == 200
    assert "Junior is closing" in response.get_data(as_text=True)
    assert shutdown_event.is_set()


def test_browser_mode_rejects_desktop_shutdown(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"
    write_settings_file(settings_file, database_file)
    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.post("/settings/shutdown", follow_redirects=True)

    assert "available from the desktop launcher only" in response.get_data(
        as_text=True
    )


def test_diagnostics_page_shows_safe_health_summary(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"
    write_settings_file(settings_file, database_file)
    (tmp_path / "startup-errors.log").write_text(
        "[2026-07-23] sanitized startup entry",
        encoding="utf-8",
    )
    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/settings/diagnostics")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Diagnostics" in html
    assert "Application configuration" in html
    assert "Latest scan" in html
    assert "Company sources" in html
    assert "Email delivery" in html
    assert "Category: Configuration" in html
    assert "Raw exceptions" in html
    assert "No company sources are configured yet." in html
    assert "startup-errors.log" in html
    assert "Copy troubleshooting details" in html
    assert "Open Data Directory" in html
    assert "Junior troubleshooting summary" in html

    log_response = client.get(
        "/settings/diagnostics/logs/startup-errors.log"
    )
    log_html = log_response.get_data(as_text=True)
    assert log_response.status_code == 200
    assert "sanitized startup entry" in log_html

    rejected = client.get("/settings/diagnostics/logs/personal.log")
    assert rejected.status_code == 302


def test_diagnostics_open_data_uses_resolved_runtime_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_file = tmp_path / "config" / "settings.yaml"
    database_file = tmp_path / "data" / "job_radar.sqlite3"
    settings_file.parent.mkdir(parents=True)
    write_settings_file(settings_file, database_file)
    opened: list[Path] = []
    monkeypatch.setattr(
        "job_radar.web_routes.settings.open_data_directory",
        lambda path: opened.append(Path(path)),
    )
    app = create_app(
        settings_path=str(settings_file),
        base_directory=str(tmp_path),
    )
    client = app.test_client()

    response = client.post("/settings/diagnostics/open-data")

    assert response.status_code == 302
    assert opened == [tmp_path]


def test_retention_settings_page_saves_choices(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"
    write_settings_file(settings_file, database_file)
    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    page = client.get("/settings/retention")
    assert page.status_code == 200
    assert "Report and log retention" in page.get_data(as_text=True)

    response = client.post(
        "/settings/retention",
        data={
            "report_policy": "keep_last_n",
            "report_count": "6",
            "log_policy": "latest_plus_previous",
            "log_count": "2",
        },
    )

    assert response.status_code == 302
    saved = load_settings(settings_file)
    assert saved.retention.reports.total_to_keep == 6
    assert saved.retention.logs.total_to_keep == 2


def test_settings_page_shows_email_enabled_without_credential(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    monkeypatch.delenv("JOB_RADAR_SMTP_PASSWORD", raising=False)
    settings_file.write_text(
        settings_file.read_text(encoding="utf-8")
        + """
email:
  enabled: true
  sender: user@example.com
  recipients:
    - user@example.com
  smtp_host: smtp.example.com
  smtp_port: 587
  smtp_username: user@example.com
  smtp_password_env: JOB_RADAR_SMTP_PASSWORD
  smtp_tls_mode: starttls
""",
        encoding="utf-8",
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/settings")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert (
        "Enabled, but credential is unavailable: JOB_RADAR_SMTP_PASSWORD"
        in html
    )


def test_settings_page_shows_email_ready(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    monkeypatch.setenv("JOB_RADAR_SMTP_PASSWORD", "not-a-real-password")
    settings_file.write_text(
        settings_file.read_text(encoding="utf-8")
        + """
email:
  enabled: true
  sender: user@example.com
  recipients:
    - user@example.com
  smtp_host: smtp.example.com
  smtp_port: 587
  smtp_username: user@example.com
  smtp_password_env: JOB_RADAR_SMTP_PASSWORD
  smtp_tls_mode: starttls
""",
        encoding="utf-8",
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/settings")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Ready to send" in html


def test_scan_page_shows_manual_scan_command(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    monkeypatch.chdir(tmp_path)

    app = create_app(settings_path=str(settings_file))
    runtime_paths = app.config["JOB_RADAR_RUNTIME_PATHS"]
    client = app.test_client()

    response = client.get("/scan")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    normalized_html = " ".join(html.split())

    assert "Scan" in html
    assert "Review the current scan settings or start a manual scan." in normalized_html
    assert "<summary>Show technical scan details</summary>" in normalized_html
    assert "<h2>Run scan</h2>" in normalized_html
    assert "Email sending is disabled for manual scans started here." in normalized_html
    assert 'id="scan-submit-button"' in html
    assert "> Run scan </button>" in normalized_html
    assert "Run scan from GUI" not in html
    assert "Scan is running. This may take a few minutes." in normalized_html
    assert "Some company/source errors are temporary." in normalized_html
    assert "After running a scan, use the latest scan links here" in normalized_html
    assert "python -m job_radar scan" in html
    assert f"--config {runtime_paths.company_config_path}" in html
    assert f"--settings {runtime_paths.settings_path}" in html
    assert (
        f"--report {runtime_paths.resolve('reports/target-scan.html')}"
        in html
    )
    assert (
        "--email-preview "
        f"{runtime_paths.resolve('reports/target-email-preview.txt')}"
        in html
    )


def test_scan_page_restores_active_scan_progress(
    tmp_path: Path,
) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)

    app = create_app(settings_path=str(settings_file))
    scan_run_id = start_scan_run(
        database_file,
        requested_at="2026-07-17T12:00:00+00:00",
        companies_requested=64,
        companies_enabled=64,
        current_stage="collection",
    )
    update_scan_run_progress(
        database_file,
        scan_run_id=scan_run_id,
        current_stage="collection",
        companies_scanned=18,
        jobs_found=142,
        collector_errors=1,
    )
    client = app.test_client()

    response = client.get("/scan")
    html = response.get_data(as_text=True)
    normalized_html = " ".join(html.split())

    assert response.status_code == 200
    assert 'id="scan-submit-button"' in html
    assert "disabled" in html
    assert "Scan running..." in normalized_html
    assert "Scanning company job sources" in html
    assert 'value="28"' in html
    assert "18 of 64 company sources scanned." in normalized_html
    assert "142 jobs found." in normalized_html


def test_scan_status_endpoint_returns_durable_progress(
    tmp_path: Path,
) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)

    app = create_app(settings_path=str(settings_file))
    scan_run_id = start_scan_run(
        database_file,
        requested_at="2026-07-17T12:00:00+00:00",
        companies_requested=64,
        companies_enabled=64,
        current_stage="collection",
    )
    update_scan_run_progress(
        database_file,
        scan_run_id=scan_run_id,
        current_stage="collection",
        companies_scanned=32,
        jobs_found=275,
        collector_errors=2,
    )
    client = app.test_client()

    response = client.get("/scan/status")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload == {
        "scan_run_id": scan_run_id,
        "status": "running",
        "is_running": True,
        "stage": "collection",
        "stage_label": "Scanning company job sources",
        "companies_scanned": 32,
        "companies_enabled": 64,
        "progress_percent": 50,
        "progress_determinate": True,
        "jobs_found": 275,
        "collector_errors": 2,
        "has_results": False,
        "failure_summary": None,
    }


def test_scan_status_endpoint_exposes_completed_report_links(
    tmp_path: Path,
) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)

    app = create_app(settings_path=str(settings_file))
    scan_run_id = start_scan_run(
        database_file,
        requested_at="2026-07-17T12:00:00+00:00",
        companies_requested=64,
        companies_enabled=64,
        current_stage="collection",
    )
    complete_scan_run(
        database_file,
        scan_run_id=scan_run_id,
        generated_at="2026-07-17T12:05:00+00:00",
        finished_at="2026-07-17T12:05:00+00:00",
        companies_scanned=64,
        jobs_collected=500,
        actionable_jobs_stored=10,
        jobs_not_actionable=490,
        jobs_new=5,
        jobs_seen=490,
        jobs_changed=5,
        collector_errors=0,
        top_matches_count=2,
        review_needed_count=8,
        report_status="completed",
        email_status="not_requested",
    )
    client = app.test_client()

    status_response = client.get("/scan/status")
    status_payload = status_response.get_json()
    page_response = client.get("/scan")
    page_html = page_response.get_data(as_text=True)

    assert status_response.status_code == 200
    assert status_payload["status"] == "completed"
    assert status_payload["is_running"] is False
    assert status_payload["progress_percent"] == 100
    assert status_payload["has_results"] is True

    assert page_response.status_code == 200
    assert "Latest scan completed." in page_html
    assert "/reports/view/target-scan.html" in page_html
    assert "/reports/view/target-email-preview.txt" in page_html


def test_scan_run_calls_handle_scan_and_redirects(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"
    calls = []
    scan_started = threading.Event()
    release_scan = threading.Event()

    write_settings_file(settings_file, database_file)
    mark_existing_installation(database_file)
    monkeypatch.chdir(tmp_path)

    def fake_handle_scan(**kwargs):
        calls.append(kwargs)
        scan_started.set()
        release_scan.wait(timeout=5)

    monkeypatch.setattr(web_app_module, "handle_scan", fake_handle_scan)

    app = create_app(settings_path=str(settings_file))
    runtime_paths = app.config["JOB_RADAR_RUNTIME_PATHS"]
    client = app.test_client()

    response = client.post("/scan/run")

    assert response.status_code == 202
    assert response.get_json() == {"status": "starting"}
    assert scan_started.wait(timeout=2)
    assert client.get("/").status_code == 200
    assert calls == [
        {
            "config_path": str(runtime_paths.company_config_path),
            "settings_path": str(runtime_paths.settings_path),
            "report_path": str(
                runtime_paths.resolve("reports/target-scan.html")
            ),
            "scoring_path": str(runtime_paths.scoring_config_path),
            "email_preview_path": str(
                runtime_paths.resolve(
                    "reports/target-email-preview.txt"
                )
            ),
            "send_email": False,
            "base_directory": str(runtime_paths.base_directory),
            "trigger_source": "manual",
        }
    ]
    release_scan.set()


def test_scan_run_reports_busy_when_scan_is_already_running(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)

    scan_started = threading.Event()
    release_scan = threading.Event()

    def hold_scan(**kwargs):
        scan_started.set()
        release_scan.wait(timeout=5)

    monkeypatch.setattr(
        web_app_module,
        "handle_scan",
        hold_scan,
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    first_response = client.post("/scan/run")
    assert first_response.status_code == 202
    assert scan_started.wait(timeout=2)

    response = client.post("/scan/run")

    assert response.status_code == 409
    assert response.get_json() == {"status": "busy"}
    release_scan.set()


def test_scan_run_reports_errors(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)

    def fake_handle_scan(**kwargs):
        raise RuntimeError("scan exploded")

    monkeypatch.setattr(web_app_module, "handle_scan", fake_handle_scan)

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.post("/scan/run")

    assert response.status_code == 202

    runner = app.extensions["junior_scan_runner"]
    for _ in range(100):
        if not runner.is_running:
            break
        threading.Event().wait(0.01)

    payload = client.get("/scan/status").get_json()
    assert payload["status"] == "failed"
    assert "could not complete the scan" in payload["failure_summary"]
    assert "scan exploded" not in payload["failure_summary"]


def test_every_page_includes_global_scan_monitor(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"
    write_settings_file(settings_file, database_file)
    mark_existing_installation(database_file)
    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    html = client.get("/").get_data(as_text=True)

    assert 'id="global-scan-status"' in html
    assert 'id="scan-notification"' in html
    assert 'url_for(\'scan_status\')' not in html
    assert 'const statusUrl = "/scan/status"' in html
    assert "junior:scan-status" in html
    assert 'sessionStorage.setItem("juniorAwaitingScanStart", "true")' in html
    assert "watchedScanId = latestObservedScanId" in html
    assert "notification.hidden = true" in html
    assert "window.location.pathname === scanPageUrl" in html


def test_index_page_links_to_reports(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    mark_existing_installation(database_file)

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'href="/reports"' in html
    assert ">Reports</a>" in html


def test_reports_page_lists_only_current_scan_outputs(
    tmp_path: Path,
) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"
    reports_path = tmp_path / "reports"
    reports_path.mkdir()

    (reports_path / "target-scan.html").write_text(
        "<html><body>Target scan</body></html>",
        encoding="utf-8",
    )
    (reports_path / "target-email-preview.txt").write_text(
        "Email preview",
        encoding="utf-8",
    )
    (reports_path / "code-audit.md").write_text(
        "# Code audit",
        encoding="utf-8",
    )
    (reports_path / "job_radar.sqlite3").write_text(
        "not a report",
        encoding="utf-8",
    )

    write_settings_file(settings_file, database_file, reports_path=reports_path)

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/reports")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Reports" in html
    assert f"<code>{reports_path}</code>" in html
    assert "Latest scan results" in html
    assert "target-scan.html" in html
    assert "/reports/view/target-scan.html" in html
    assert "Latest HTML scan report. Open this first." in html
    assert "Latest scan result shortcuts" in html
    assert "primary-output-card" in html
    assert "Open the latest generated scan report and email preview." in html
    assert "Older report sets appear below when retention is enabled." in html
    assert "target-email-preview.txt" in html
    assert "Latest plain-text email preview." in html
    assert "code-audit.md" not in html
    assert "job_radar.sqlite3" not in html
    assert "Additional files" not in html
    assert "Report files shown:" not in html
    assert "It does not start a scan or send email." in html


def test_reports_page_shows_primary_outputs_in_display_order(
    tmp_path: Path,
) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"
    reports_path = tmp_path / "reports"
    reports_path.mkdir()

    html_report = reports_path / "target-scan.html"
    email_preview = reports_path / "target-email-preview.txt"
    html_report.write_text("HTML report", encoding="utf-8")
    email_preview.write_text("Email preview", encoding="utf-8")

    html_timestamp = datetime(2026, 7, 16, 9, 15).timestamp()
    email_timestamp = datetime(2026, 7, 16, 21, 47).timestamp()
    os.utime(
        html_report,
        (html_timestamp, html_timestamp),
    )
    os.utime(
        email_preview,
        (email_timestamp, email_timestamp),
    )

    write_settings_file(
        settings_file,
        database_file,
        reports_path=reports_path,
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/reports")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert datetime.fromtimestamp(html_timestamp).strftime(
        "%Y-%m-%d %I:%M %p"
    ) in html
    assert datetime.fromtimestamp(email_timestamp).strftime(
        "%Y-%m-%d %I:%M %p"
    ) in html
    assert html.index("target-scan.html") < html.index(
        "target-email-preview.txt"
    )


def test_reports_page_handles_missing_reports_directory(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"
    reports_path = tmp_path / "missing-reports"

    write_settings_file(settings_file, database_file, reports_path=reports_path)

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/reports")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "No scan outputs found yet. Run a scan first." in html
    assert "Additional files" not in html
    assert "Report files shown:" not in html


def test_report_view_embeds_report_inside_app_shell(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"
    reports_path = tmp_path / "reports"
    reports_path.mkdir()
    report_file = reports_path / "target-scan.html"
    report_file.write_text("<html><body>Target scan</body></html>", encoding="utf-8")

    write_settings_file(settings_file, database_file, reports_path=reports_path)

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/reports/view/target-scan.html")
    html = response.get_data(as_text=True)

    normalized_html = " ".join(html.split())

    assert response.status_code == 200
    assert "Report Viewer" in html
    assert "Back to Reports" in html
    assert "<code>target-scan.html</code>" in html
    assert "report-shell" in html
    assert "report-content" in html
    assert "Target scan" in html
    assert "<iframe" not in html
    assert 'src="/reports/target-scan.html"' not in html
    assert '<a href="/reports">Back to Reports</a>' in normalized_html


def test_report_view_rejects_non_report_file(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"
    reports_path = tmp_path / "reports"
    reports_path.mkdir()
    (reports_path / "job_radar.sqlite3").write_text("private db", encoding="utf-8")

    write_settings_file(settings_file, database_file, reports_path=reports_path)

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/reports/view/job_radar.sqlite3")

    assert response.status_code == 404


def test_report_file_serves_allowed_report_file(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"
    reports_path = tmp_path / "reports"
    reports_path.mkdir()
    report_file = reports_path / "code-audit.md"
    report_file.write_text("# Code audit", encoding="utf-8")

    write_settings_file(settings_file, database_file, reports_path=reports_path)

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/reports/code-audit.md")

    assert response.status_code == 200
    assert "# Code audit" in response.get_data(as_text=True)


def test_report_file_rejects_non_report_file(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"
    reports_path = tmp_path / "reports"
    reports_path.mkdir()
    (reports_path / "job_radar.sqlite3").write_text("private db", encoding="utf-8")

    write_settings_file(settings_file, database_file, reports_path=reports_path)

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/reports/job_radar.sqlite3")

    assert response.status_code == 404


def test_tracker_page_keeps_long_notes_in_application_workspace(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"
    long_note = (
        "This is a long tracker note with important context. "
        "It should remain available in the application workspace because the notes field often "
        "contains fit concerns, recruiter context, rejection details, and "
        "manual review comments."
    )

    write_settings_file(settings_file, database_file)
    initialize_database(database_file)
    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-notes-12345678",
            company_name="NotesCo",
            role_title="Senior Infrastructure Engineer",
            status="applied",
            notes=long_note,
        ),
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    tracker_response = client.get("/tracker?sort=workflow")
    tracker_html = tracker_response.get_data(as_text=True)

    assert tracker_response.status_code == 200
    assert "NotesCo" in tracker_html
    assert "Show full note" not in tracker_html
    assert long_note not in tracker_html
    assert 'href="/tracker/jr-notes-12345678/edit?filter=all"' in tracker_html

    workspace_response = client.get("/tracker/jr-notes-12345678/edit")
    workspace_html = workspace_response.get_data(as_text=True)

    assert workspace_response.status_code == 200
    assert long_note in workspace_html


def test_tracker_page_sorts_by_workflow_priority(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    initialize_database(database_file)

    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-waiting-12345678",
            company_name="WaitingCo",
            role_title="Cluster Engineer",
            status="applied",
            last_activity_on="2026-07-01",
        ),
    )
    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-action-12345678",
            company_name="ActionCo",
            role_title="SRE",
            status="follow_up_due",
        ),
    )
    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-closed-12345678",
            company_name="ClosedCo",
            role_title="Linux Engineer",
            status="rejected",
        ),
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/tracker?sort=workflow")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert html.index("ActionCo") < html.index("WaitingCo")
    assert html.index("WaitingCo") < html.index("ClosedCo")


def test_tracker_page_defaults_to_applied_date_descending(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    initialize_database(database_file)

    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-old-12345678",
            company_name="OldCo",
            role_title="Linux Engineer",
            status="applied",
            applied_on="2026-05-01",
        ),
    )
    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-new-12345678",
            company_name="NewCo",
            role_title="Platform Engineer",
            status="applied",
            applied_on="2026-07-05",
        ),
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/tracker")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert '<option value="applied_desc" selected>' in html
    assert html.index("NewCo") < html.index("OldCo")


def test_tracker_page_sorts_by_company_status_role_and_outcome(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    initialize_database(database_file)

    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-zeta-12345678",
            company_name="ZetaCo",
            role_title="Linux Engineer",
            status="dormant",
            outcome="Dormant",
        ),
    )
    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-alpha-12345678",
            company_name="AlphaCo",
            role_title="Platform Engineer",
            status="applied",
            outcome="Pending / In Progress",
        ),
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    company_response = client.get("/tracker?sort=company")
    company_html = company_response.get_data(as_text=True)
    assert company_response.status_code == 200
    assert '<option value="company" selected>' in company_html
    assert company_html.index("AlphaCo") < company_html.index("ZetaCo")

    role_response = client.get("/tracker?sort=role")
    role_html = role_response.get_data(as_text=True)
    assert role_response.status_code == 200
    assert '<option value="role" selected>' in role_html
    assert role_html.index("Linux Engineer") < role_html.index("Platform Engineer")

    status_response = client.get("/tracker?sort=status")
    status_html = status_response.get_data(as_text=True)
    assert status_response.status_code == 200
    assert '<option value="status" selected>' in status_html
    assert status_html.index("AlphaCo") < status_html.index("ZetaCo")

    outcome_response = client.get("/tracker?sort=outcome")
    outcome_html = outcome_response.get_data(as_text=True)
    assert outcome_response.status_code == 200
    assert '<option value="outcome" selected>' in outcome_html
    assert outcome_html.index("ZetaCo") < outcome_html.index("AlphaCo")


def test_tracker_page_sorts_by_applied_date_descending(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    initialize_database(database_file)

    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-old-12345678",
            company_name="OldCo",
            role_title="Linux Engineer",
            status="applied",
            applied_on="2026-05-01",
        ),
    )
    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-new-12345678",
            company_name="NewCo",
            role_title="Platform Engineer",
            status="applied",
            applied_on="2026-07-05",
        ),
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/tracker?sort=applied_desc")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Applied date newest first" in html
    assert html.index("NewCo") < html.index("OldCo")


def test_tracker_page_sorts_by_applied_date_ascending(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    initialize_database(database_file)

    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-old-12345678",
            company_name="OldCo",
            role_title="Linux Engineer",
            status="applied",
            applied_on="2026-05-01",
        ),
    )
    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-new-12345678",
            company_name="NewCo",
            role_title="Platform Engineer",
            status="applied",
            applied_on="2026-07-05",
        ),
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/tracker?sort=applied_asc")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Applied date oldest first" in html
    assert html.index("OldCo") < html.index("NewCo")


def test_tracker_page_searches_tracker_text(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    initialize_database(database_file)

    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-hpc-12345678",
            company_name="Example Hosting",
            role_title="HPC Solutions Engineer",
            status="applied",
            notes="GPU, InfiniBand, Slurm, and distributed machine learning.",
        ),
    )
    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-platform-12345678",
            company_name="PlatformCo",
            role_title="Platform Engineer",
            status="applied",
            notes="Generic platform role.",
        ),
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/tracker?q=infiniband")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Applications shown:</strong> 1" in html
    assert "Example Hosting" in html
    assert "PlatformCo" not in html


def test_tracker_filter_links_preserve_search_sort_and_field_filters(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    initialize_database(database_file)
    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-hpc-12345678",
            company_name="Example Hosting",
            role_title="HPC Solutions Engineer",
            status="applied",
            outcome="Pending / In Progress",
            notes="InfiniBand and Slurm fit.",
        ),
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get(
        "/tracker",
        query_string={
            "filter": "needs_review",
            "sort": "company",
            "q": "hpc",
            "status_filter": "Applied",
            "outcome_filter": "Pending / In Progress",
        },
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "filter=all" in html
    assert "filter=active" in html
    assert "tracker-summary-card" in html
    assert "status_filter=Applied" in html
    assert "outcome_filter=Pending+" in html
    assert 'value="hpc"' in html
    assert '<option value="Applied" selected>' in html
    assert '<option value="Pending / In Progress" selected>' in html
    assert '<option value="company" selected>' in html


def test_tracker_page_filters_by_status_and_outcome(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    initialize_database(database_file)

    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-active-12345678",
            company_name="ActiveCo",
            role_title="Platform Engineer",
            status="applied",
            outcome="Pending / In Progress",
        ),
    )
    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-rejected-12345678",
            company_name="RejectedCo",
            role_title="Linux Engineer",
            status="rejected",
            outcome="Rejected - No Interview",
        ),
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get(
        "/tracker",
        query_string={
            "status_filter": "Applied",
            "outcome_filter": "Pending / In Progress",
        },
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Applications shown:</strong> 1" in html
    assert "ActiveCo" in html
    assert "RejectedCo" not in html
    assert '<option value="Applied" selected>' in html
    assert '<option value="Pending / In Progress" selected>' in html
    assert '<option value="Passed"' in html
    assert '<option value="Withdrawn"' in html
    assert '<option value="Revisit"' in html
    assert '<option value="N/A"' in html
    outcome_filter = html.split(
        '<select id="tracker-outcome-filter"',
        maxsplit=1,
    )[1].split("</select>", maxsplit=1)[0]
    assert '<option value="Rejected - No Interview"' not in outcome_filter
    assert '<option value="Rejected - After Interview"' not in outcome_filter
    assert '<option value="Closed Before Application"' not in outcome_filter
    assert "Alive Until Declared Dead" not in html
    assert "Clear search/field filters/sort" in html


def test_tracker_page_rejects_unknown_sort(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/tracker?sort=unknown")

    assert response.status_code == 404


def test_tracker_page_filters_to_needs_action(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    initialize_database(database_file)

    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-action-12345678",
            company_name="ActionCo",
            role_title="SRE",
            status="follow_up_due",
        ),
    )
    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-waiting-12345678",
            company_name="WaitingCo",
            role_title="Cluster Engineer",
            status="applied",
            last_activity_on="2026-07-01",
        ),
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/tracker?filter=needs_action")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Applications shown:</strong> 1" in html
    assert "ActionCo" in html
    assert "WaitingCo" not in html


def test_tracker_page_filters_to_needs_review(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    initialize_database(database_file)

    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-stale-12345678",
            company_name="StaleCo",
            role_title="Platform Engineer",
            status="applied",
            last_activity_on="2026-03-01",
        ),
    )
    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-waiting-12345678",
            company_name="WaitingCo",
            role_title="Cluster Engineer",
            status="applied",
            last_activity_on="2026-07-01",
        ),
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/tracker?filter=needs_review")
    html = response.get_data(as_text=True)
    normalized_html = " ".join(html.split())

    assert response.status_code == 200
    assert "Applications shown:</strong> 1" in html
    assert "Needs review queue" in html
    assert "Review these applications for stale dates, dormant status, presumed closure, or invalid date fields." in html
    assert "Open a record to refresh dates" in html
    assert 'href="/tracker/jr-stale-12345678/edit?filter=needs_review"' in normalized_html
    assert ">Review</a>" in normalized_html
    assert "workflow-badge workflow-stale" in html
    assert "Stale" in html
    assert "StaleCo" in html
    assert "WaitingCo" not in html


def test_tracker_edit_page_shows_application_form(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    initialize_database(database_file)
    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-example-mobility-12345678",
            company_name="Example Mobility",
            role_title="Senior Site Reliability Engineer",
            source_url="https://example.com/jobs/example-mobility-sre",
            status="Applied",
            follow_up_on="2099-07-10",
            applied_on="2026-07-03",
            last_activity_on="2026-07-05",
            outcome="Interview Scheduled",
            notes="Applied through company site.",
        ),
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/tracker/jr-example-mobility-12345678/edit?filter=needs_action")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Application details" in html
    assert "Example Mobility" in html
    assert "Senior Site Reliability Engineer" in html
    assert "Job Radar ID" in html
    assert "jr-example-mobility-12345678" in html
    assert "application-header" in html
    assert "quick-action-grid" in html
    assert "date-grid" in html
    assert "Waiting" in html
    assert "overflow-wrap: anywhere;" in html
    assert "word-break: break-word;" in html
    assert 'name="return_filter" value="needs_action"' in html
    assert '<option value="Applied" selected>' in html
    assert 'id="follow_up_on" name="follow_up_on" type="date" value="2099-07-10"' in html
    assert 'id="applied_on" name="applied_on" type="date" value="2026-07-03"' in html
    assert 'id="last_activity_on" name="last_activity_on" type="date" value="2026-07-05"' in html
    assert '<option value="Interview Scheduled" selected>' in html
    assert "Refresh activity today" in html
    assert "Schedule follow-up next week" in html
    assert "Applied through company site." in html
    assert "Next action" in html
    assert "Last activity was recorded on July 5, 2026." in html
    assert "Keep interview or recruiter notes current and record the next follow-up date." in html
    assert 'href="/tracker?filter=needs_action">Back to Active Applications</a>' in html
    assert 'target="_blank" rel="noopener noreferrer"' in html


def test_tracker_edit_page_shows_follow_up_due_next_action(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    initialize_database(database_file)
    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-due-12345678",
            company_name="DueCo",
            role_title="SRE",
            status="Applied",
            follow_up_on="2026-01-01",
            applied_on="2026-01-01",
            outcome="Pending / In Progress",
        ),
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/tracker/jr-due-12345678/edit")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Next action" in html
    assert "Follow-up was due on January 1, 2026." in html
    assert "Refresh activity today or schedule the next follow-up." in html


def test_tracker_edit_page_shows_missing_follow_up_next_action(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    initialize_database(database_file)
    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-missing-follow-up-12345678",
            company_name="MissingCo",
            role_title="Platform Engineer",
            status="Applied",
            applied_on=date.today().isoformat(),
            last_activity_on=date.today().isoformat(),
            outcome="Pending / In Progress",
        ),
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/tracker/jr-missing-follow-up-12345678/edit")
    html = response.get_data(as_text=True)

    expected_date = f"{date.today().strftime('%B')} {date.today().day}, {date.today().year}"

    assert response.status_code == 200
    assert "Next action" in html
    assert f"Waiting for an update since {expected_date}." in html
    assert "Record the next follow-up date when appropriate." in html


def test_tracker_edit_page_shows_date_review_next_action(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    initialize_database(database_file)
    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-date-review-12345678",
            company_name="DateReviewCo",
            role_title="Infrastructure Engineer",
            status="Applied",
            follow_up_on="not-a-date",
            applied_on="2026-07-01",
            outcome="Pending / In Progress",
        ),
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/tracker/jr-date-review-12345678/edit")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Next action" in html
    assert "The follow-up date needs review. Use the date picker or a quick action to repair it." in html


def test_tracker_edit_page_shows_stale_next_action(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    initialize_database(database_file)
    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-stale-12345678",
            company_name="StaleCo",
            role_title="Linux Engineer",
            status="Applied",
            last_activity_on="2026-03-01",
            outcome="Pending / In Progress",
        ),
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/tracker/jr-stale-12345678/edit")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Next action" in html
    assert "No activity has been recorded since March 1, 2026." in html
    assert "Refresh activity, schedule follow-up, or move it to history if it is effectively closed." in html


def test_tracker_edit_page_shows_dormant_next_action(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    initialize_database(database_file)
    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-dormant-12345678",
            company_name="DormantCo",
            role_title="Systems Engineer",
            status="Applied",
            outcome="Dormant",
        ),
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/tracker/jr-dormant-12345678/edit")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Next action" in html
    assert "This application is dormant. Decide whether to revive it, leave it dormant, or move it to history." in html


def test_tracker_edit_page_moves_terminal_outcome_to_history_and_redirects(
    tmp_path: Path,
) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    initialize_database(database_file)
    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-example-mobility-12345678",
            company_name="Example Mobility",
            role_title="Senior Site Reliability Engineer",
            source_url="https://example.com/jobs/example-mobility-sre",
            status="Applied",
            follow_up_on="2099-07-10",
            applied_on="2026-07-03",
            last_activity_on="2026-07-05",
            outcome="Interview Scheduled",
            notes="Applied through company site.",
        ),
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.post(
        "/tracker/jr-example-mobility-12345678/edit",
        data={
            "return_filter": "needs_action",
            "status": "Applied",
            "follow_up_on": "2026-07-20",
            "applied_on": "2026-07-03",
            "last_activity_on": "2026-07-12",
            "outcome": "Rejected - No Interview",
            "notes": "Rejected by email.",
        },
    )

    application = get_application(database_file, "jr-example-mobility-12345678")
    history_records = fetch_included_job_history_records(database_file)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/tracker?filter=needs_action")
    assert application is None
    assert len(history_records) == 1

    history_record = history_records[0]

    assert history_record.company == "Example Mobility"
    assert history_record.role == "Senior Site Reliability Engineer"
    assert history_record.source == "Job Radar Tracker"
    assert history_record.event_date == "2026-07-12"
    assert history_record.status == "Applied"
    assert history_record.outcome_category == "Rejected - No Interview"
    assert history_record.import_key == "job-radar-id:jr-example-mobility-12345678"
    assert history_record.notes == "Rejected by email."
    assert history_record.applied_on == "2026-07-03"
    assert history_record.last_activity_on == "2026-07-12"
    assert history_record.follow_up_on == "2026-07-20"


def test_tracker_bulk_update_moves_selected_applications_to_history(
    tmp_path: Path,
) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    initialize_database(database_file)
    for suffix, company in (
        ("11111111", "Example Bakery"),
        ("22222222", "Example Hotel"),
    ):
        upsert_application(
            database_file,
            ApplicationRecord(
                job_radar_id=f"jr-bulk-{suffix}",
                company_name=company,
                role_title="Cook",
                status="Applied",
                outcome="Dormant",
            ),
        )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    page_html = client.get("/tracker").get_data(as_text=True)
    assert 'id="select-all-applications"' in page_html
    assert 'id="bulk-outcome"' in page_html
    assert 'id="bulk-update-button"' in page_html
    assert 'id="bulk-confirmation-dialog"' in page_html
    assert "Move applications to History?" in page_html
    assert "window.confirm" not in page_html

    response = client.post(
        "/tracker/bulk-update",
        data={
            "return_filter": "needs_review",
            "job_radar_id": [
                "jr-bulk-11111111",
                "jr-bulk-22222222",
            ],
            "bulk_outcome": "Rejected - No Interview",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert (
        "Moved 2 applications to History as Rejected - No Interview."
        in response.get_data(as_text=True)
    )
    assert list_applications(database_file) == []
    history = fetch_included_job_history_records(database_file)
    assert len(history) == 2
    assert {record.company for record in history} == {
        "Example Bakery",
        "Example Hotel",
    }
    assert {record.outcome_category for record in history} == {
        "Rejected - No Interview"
    }


def test_tracker_edit_quick_action_marks_application_dormant(
    tmp_path: Path,
) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    initialize_database(database_file)
    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-example-mobility-12345678",
            company_name="Example Mobility",
            role_title="Senior Site Reliability Engineer",
            status="Applied",
            outcome="Pending / In Progress",
            notes="Applied through company site.",
        ),
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.post(
        "/tracker/jr-example-mobility-12345678/edit",
        data={
            "return_filter": "needs_review",
            "status": "Applied",
            "follow_up_on": "",
            "applied_on": "",
            "last_activity_on": "2026-07-12",
            "outcome": "Pending / In Progress",
            "notes": "Marked dormant.",
            "quick_action": "dormant",
        },
    )

    application = get_application(database_file, "jr-example-mobility-12345678")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/tracker?filter=needs_review")
    assert application is not None
    assert application.status == "Applied"
    assert application.last_activity_on == "2026-07-12"
    assert application.outcome == "Dormant"
    assert application.notes == "Marked dormant."


def test_tracker_edit_quick_action_refreshes_activity_today(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    class FixedDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 7, 20)

    monkeypatch.setattr(web_app_module, "date", FixedDate)

    write_settings_file(settings_file, database_file)
    initialize_database(database_file)
    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-refresh-12345678",
            company_name="RefreshCo",
            role_title="Platform Engineer",
            status="Applied",
            applied_on="2026-01-01",
            last_activity_on="2026-01-01",
            outcome="Pending / In Progress",
            notes="Needs refresh.",
        ),
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.post(
        "/tracker/jr-refresh-12345678/edit",
        data={
            "return_filter": "needs_review",
            "status": "Applied",
            "follow_up_on": "",
            "applied_on": "2026-01-01",
            "last_activity_on": "2026-01-01",
            "outcome": "Pending / In Progress",
            "notes": "Needs refresh.",
            "quick_action": "refresh_activity_today",
        },
    )

    application = get_application(database_file, "jr-refresh-12345678")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/tracker?filter=needs_review")
    assert application is not None
    assert application.status == "Applied"
    assert application.outcome == "Pending / In Progress"
    assert application.applied_on == "2026-01-01"
    assert application.last_activity_on == "2026-07-20"
    assert application.follow_up_on is None
    assert application.notes == "Needs refresh."


def test_tracker_edit_quick_action_schedules_follow_up_next_week(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    class FixedDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 7, 20)

    monkeypatch.setattr(web_app_module, "date", FixedDate)

    write_settings_file(settings_file, database_file)
    initialize_database(database_file)
    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-followup-12345678",
            company_name="FollowUpCo",
            role_title="Infrastructure Engineer",
            status="Applied",
            applied_on="2026-01-01",
            last_activity_on="2026-01-01",
            outcome="Pending / In Progress",
            notes="Needs follow-up.",
        ),
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.post(
        "/tracker/jr-followup-12345678/edit",
        data={
            "return_filter": "needs_review",
            "status": "Applied",
            "follow_up_on": "",
            "applied_on": "2026-01-01",
            "last_activity_on": "2026-01-01",
            "outcome": "Pending / In Progress",
            "notes": "Needs follow-up.",
            "quick_action": "follow_up_next_week",
        },
    )

    application = get_application(database_file, "jr-followup-12345678")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/tracker?filter=needs_review")
    assert application is not None
    assert application.status == "Applied"
    assert application.outcome == "Pending / In Progress"
    assert application.applied_on == "2026-01-01"
    assert application.last_activity_on == "2026-07-20"
    assert application.follow_up_on == "2026-07-27"
    assert application.notes == "Needs follow-up."


def test_tracker_page_links_to_add_application(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/tracker")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert '<a href="/tracker/add">Add application</a>' in html


def test_tracker_add_page_shows_application_form(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/tracker/add")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Add Application" in html
    assert "junior assigns the ID when one is not already linked from a scan result." in html
    assert 'id="job_radar_id" name="job_radar_id" value="" readonly' in html
    assert 'name="company_name"' in html
    assert 'name="role_title"' in html
    assert 'name="source_url"' in html
    assert '<option value="Applied" selected>' in html
    assert '<option value="Pending / In Progress" selected>' in html
    assert 'name="follow_up_on"' in html
    assert 'name="applied_on"' in html
    assert 'name="last_activity_on"' in html
    assert 'name="notes"' in html


def test_tracker_add_page_saves_application_and_redirects(
    tmp_path: Path,
) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.post(
        "/tracker/add",
        data={
            "company_name": "ManualCo",
            "role_title": "Senior Infrastructure Engineer",
            "source_url": "https://example.com/jobs/manual",
            "status": "Applied",
            "follow_up_on": "2026-07-15",
            "applied_on": "2026-07-05",
            "last_activity_on": "2026-07-05",
            "outcome": "Pending / In Progress",
            "notes": "Added manually from GUI.",
        },
    )

    applications = list_applications(database_file)

    assert response.status_code == 302
    assert "/tracker/jr_manual_manualco_senior_infrastructure_engineer_" in response.headers["Location"]
    assert response.headers["Location"].endswith("/edit?filter=all&tracked=created")
    assert len(applications) == 1

    application = applications[0]

    assert application.job_radar_id.startswith("jr_manual_manualco_senior_infrastructure_engineer_")
    assert application.source_url == "https://example.com/jobs/manual"
    assert application.company_name == "ManualCo"
    assert application.role_title == "Senior Infrastructure Engineer"
    assert application.source_url == "https://example.com/jobs/manual"
    assert application.status == "Applied"
    assert application.follow_up_on == "2026-07-15"
    assert application.applied_on == "2026-07-05"
    assert application.last_activity_on == "2026-07-05"
    assert application.outcome == "Pending / In Progress"
    assert application.notes == "Added manually from GUI."

    edit_response = client.get(response.headers["Location"])
    edit_html = edit_response.get_data(as_text=True)

    assert edit_response.status_code == 200
    assert "Application tracked" in edit_html
    assert "Next action" in edit_html


def test_tracker_edit_page_deletes_application_and_redirects(
    tmp_path: Path,
) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    initialize_database(database_file)
    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-delete-me-12345678",
            company_name="DeleteCo",
            role_title="Temporary Tracker Row",
            status="Applied",
            outcome="Pending / In Progress",
        ),
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.post(
        "/tracker/jr-delete-me-12345678/edit",
        data={
            "return_filter": "needs_action",
            "action": "delete",
        },
    )

    application = get_application(database_file, "jr-delete-me-12345678")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/tracker?filter=all")
    assert application is None


def test_tracker_edit_page_repairs_path_style_job_radar_ids(
    tmp_path: Path,
) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    initialize_database(database_file)
    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="posting-url:https://example.com/jobs/hydra",
            company_name="Example Hosting",
            role_title="HPC Solutions Engineer",
            source_url="https://example.com/jobs/hydra",
            status="Applied",
            outcome="Pending / In Progress",
        ),
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    repaired_application = list_applications(database_file)[0]

    old_id_response = client.get("/tracker/posting-url:https://example.com/jobs/hydra/edit")
    repaired_id_response = client.get(
        f"/tracker/{repaired_application.job_radar_id}/edit"
    )
    repaired_html = repaired_id_response.get_data(as_text=True)

    assert repaired_application.job_radar_id.startswith(
        "jr_manual_example_hosting_hpc_solutions_engineer_"
    )
    assert not repaired_application.job_radar_id.startswith("posting-url:")
    assert old_id_response.status_code == 404
    assert repaired_id_response.status_code == 200
    assert "Example Hosting" in repaired_html
    assert "posting-url:https://example.com/jobs/hydra" not in repaired_html


def test_history_page_links_to_history_edit(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    initialize_database(database_file)
    upsert_job_history_record(
        database_file,
        JobHistoryRecord(
            history_type="Pipeline",
            company="ReopenCo",
            role="Senior SRE",
            source="Job Radar Tracker",
            ats_platform=None,
            work_arrangement=None,
            location=None,
            comp_range=None,
            event_date="2026-07-01",
            status="Applied",
            outcome_category="Rejected - No Interview",
            recruiter_contact=None,
            technical_match=None,
            hiring_probability=None,
            skills_signals=None,
            primary_blocker=None,
            secondary_blocker=None,
            revisit=None,
            include_in_job_radar=True,
            import_key="job-radar-id:jr-reopenco-senior-sre",
            notes="Previously rejected.",
        ),
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/history")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "/history/job-radar-id:jr-reopenco-senior-sre/edit" in html


def test_history_edit_page_restores_record_with_quick_action(
    tmp_path: Path,
) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    initialize_database(database_file)
    upsert_job_history_record(
        database_file,
        JobHistoryRecord(
            history_type="Pipeline",
            company="ReopenCo",
            role="Senior SRE",
            source="Job Radar Tracker",
            ats_platform=None,
            work_arrangement=None,
            location=None,
            comp_range=None,
            event_date="2026-07-01",
            status="Applied",
            outcome_category="Rejected - No Interview",
            recruiter_contact="Recruiter",
            technical_match=None,
            hiring_probability=None,
            skills_signals=None,
            primary_blocker=None,
            secondary_blocker=None,
            revisit=None,
            include_in_job_radar=True,
            import_key="job-radar-id:jr-reopenco-senior-sre",
            notes="Opportunity reopened.",
            applied_on="2026-06-20",
            last_activity_on="2026-07-01",
            follow_up_on="2026-07-08",
        ),
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()
    history_edit_url = "/history/job-radar-id:jr-reopenco-senior-sre/edit"

    page_response = client.get(history_edit_url)
    page_html = page_response.get_data(as_text=True)

    assert page_response.status_code == 200
    assert "Quick actions" in page_html
    assert "Restore to Active Applications" in page_html
    assert 'name="quick_action" value="restore_to_tracker"' in page_html

    invalid_response = client.post(
        history_edit_url,
        data={
            "company": "ReopenCo",
            "role": "Senior SRE",
            "event_date": "2026-07-15",
            "status": "Applied",
            "outcome": "Rejected - No Interview",
            "source": "Recruiter",
            "recruiter_contact": "Recruiter",
            "notes": "Opportunity reopened.",
            "quick_action": "unknown_history_action",
        },
    )

    assert invalid_response.status_code == 400
    assert get_application(database_file, "jr-reopenco-senior-sre") is None
    assert len(fetch_included_job_history_records(database_file)) == 1

    response = client.post(
        history_edit_url,
        data={
            "company": "ReopenCo",
            "role": "Senior SRE",
            "event_date": "2026-07-15",
            "status": "Applied",
            "outcome": "Rejected - No Interview",
            "source": "Recruiter",
            "recruiter_contact": "Recruiter",
            "notes": "Opportunity reopened.",
            "quick_action": "restore_to_tracker",
        },
    )

    application = get_application(database_file, "jr-reopenco-senior-sre")
    history_records = fetch_included_job_history_records(database_file)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/tracker?filter=all")
    assert application is not None
    assert application.company_name == "ReopenCo"
    assert application.role_title == "Senior SRE"
    assert application.status == "Applied"
    assert application.outcome == "Pending / In Progress"
    assert application.notes == "Opportunity reopened."
    assert application.applied_on == "2026-06-20"
    assert application.last_activity_on == "2026-07-01"
    assert application.follow_up_on == "2026-07-08"
    assert history_records == []


def test_history_edit_page_deletes_history_record(
    tmp_path: Path,
) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    initialize_database(database_file)
    upsert_job_history_record(
        database_file,
        JobHistoryRecord(
            history_type="Reviewed",
            company="DeleteHistoryCo",
            role="Linux Engineer",
            source="LinkedIn",
            ats_platform=None,
            work_arrangement=None,
            location=None,
            comp_range=None,
            event_date="2026-07-01",
            status="Passed",
            outcome_category="N/A",
            recruiter_contact=None,
            technical_match=None,
            hiring_probability=None,
            skills_signals=None,
            primary_blocker=None,
            secondary_blocker=None,
            revisit=None,
            include_in_job_radar=True,
            import_key="manual:delete-history-co:linux-engineer",
            notes="Delete test row.",
        ),
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.post(
        "/history/manual:delete-history-co:linux-engineer/edit",
        data={
            "action": "delete",
        },
    )

    history_records = fetch_included_job_history_records(database_file)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/history")
    assert history_records == []


def test_index_page_links_to_profile(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    mark_existing_installation(database_file)

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'href="/profile"' in html
    assert ">Profile / Resume</a>" in html


def test_profile_page_shows_candidate_profile_and_resume_summary(
    tmp_path: Path,
) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"
    profile_file = tmp_path / "profile.yaml"
    resume_file = tmp_path / "resume.md"
    normalized_resume_file = tmp_path / "resume.normalized.txt"

    write_settings_file(settings_file, database_file)
    settings_file.write_text(
        settings_file.read_text(encoding="utf-8")
        + f"\ncandidate_profile_path: {profile_file}\n",
        encoding="utf-8",
    )
    resume_file.write_text(
        "# Example Candidate\n\nLarge-scale Linux and HPC operations.",
        encoding="utf-8",
    )
    normalized_resume_file.write_text(
        "large-scale linux and hpc operations\n",
        encoding="utf-8",
    )
    profile_file.write_text(
        f"""
candidate:
  name: Example Candidate
  compensation_floor_usd: 160000
  preferred_base_usd: 185000
  resume:
    source_path: {resume_file}
    normalized_text_path: {normalized_resume_file}
  core_strengths:
    - Linux infrastructure
    - HPC operations
  credible_adjacent:
    - SRE
  learning_or_gap:
    - production Kubernetes ownership
  avoid:
    - frontend
""",
        encoding="utf-8",
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/profile")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Profile / Resume" in html
    assert "Confirm the candidate profile and resume junior currently uses" in html
    assert "Active candidate" in html
    assert "Compensation floor" in html
    assert "Preferred base" in html
    assert "Active resume" in html
    assert "Profile and resume available" in html
    assert "Job fit" in html
    assert "Strengths" in html
    assert "Adjacent capabilities" in html
    assert "Experience gaps" in html
    assert "Roles to avoid" in html
    assert "<h2>Résumé</h2>" in html
    assert "Advanced technical details" in html
    assert "File paths and internal status used only for troubleshooting" in html
    assert str(settings_file) in html
    assert str(profile_file) in html
    assert str(resume_file) in html
    assert str(normalized_resume_file) in html
    assert "Example Candidate" in html
    assert "$160,000" in html
    assert "$185,000" in html
    assert "Linux infrastructure" in html
    assert "HPC operations" in html
    assert "SRE" in html
    assert "production Kubernetes ownership" in html
    assert "frontend" in html
    assert "Large-scale Linux and HPC operations." in html


def test_search_preferences_page_can_create_a_managed_profile(
    tmp_path: Path,
) -> None:
    settings_file = tmp_path / "config" / "settings.yaml"
    database_file = tmp_path / "data" / "job_radar.sqlite3"
    scoring_file = tmp_path / "config" / "scoring.yaml"
    settings_file.parent.mkdir(parents=True)
    write_settings_file(settings_file, database_file)
    scoring_file.write_text(
        """
positive_keywords:
  linux: 10
negative_keywords:
  sales: -15
location_preferences:
  allowed:
    remote: 100
    northern colorado: 100
  conditional:
    denver: -25
  skipped:
    new york: -100
top_matches:
  min_score: 120
  excluded_title_keywords:
    - sales
  strong_signals:
    - title:linux
review_needed:
  min_score: 100
  excluded_location_statuses:
    - skipped
    - unknown
  strong_signals:
    - body:linux
""",
        encoding="utf-8",
    )

    app = create_app(
        settings_path=str(settings_file),
        base_directory=str(tmp_path),
    )
    client = app.test_client()
    response = client.get("/preferences")

    assert response.status_code == 302
    assert response.headers["Location"] == "/profile"

    html = client.get("/profile/new").get_data(as_text=True)
    assert "Create profile" in html
    assert "Back to profile summary" in html
    assert "Cancel" in html
    assert 'name="display_name"' in html
    assert "Create profile" in html
    assert "You are not running a job-board search from this page" in html
    assert "during company scans" in html
    assert "Find an occupation" in html
    assert "Job requirements" in html
    assert 'id="add-occupation"' not in html
    assert 'id="add-location"' not in html
    assert 'aria-live="polite"' in html
    assert "enter your own wording" in html
    assert "Workplace arrangements" in html
    assert "City, state, or ZIP" in html
    assert "Your profile at a glance" in html
    assert "Strengths" in html
    assert "Jobs must pay at least" in html
    assert "junior will place it in Needs Review" in html
    assert "How recommendations should be explained" not in html
    assert "Roles included in this search" in html
    assert "Entry-level" in html
    assert "Mid-level" in html
    assert "Senior" in html
    assert "Executive" in html
    assert "Employment types to include" in html
    assert "Choose job levels" in html
    assert "Choose employment types" in html
    assert "Choose workplace arrangements" in html
    assert "checklist-select" in html
    assert 'name="employment-type" type="checkbox" value="Full-time"' in html
    assert 'name="employment-type" type="checkbox" value="Contract"' in html
    assert 'name="workplace-arrangement" type="checkbox" value="Remote"' in html
    assert 'value="Remote" checked' not in html
    assert "If arrangement or location is unclear" not in html
    assert "Add a location" in html
    assert "Select every arrangement you are willing to accept" in html
    assert "approximate straight-line distance" in html
    assert "genuinely plan to move" in html
    assert "junior will mark it Do Not Apply and explain why" in html
    assert "workplace-arrangement" in html
    assert "additional_cities" in html
    assert "more major communities" in html


def test_profile_page_guides_first_time_user_without_creating_data(
    tmp_path: Path,
) -> None:
    settings_file = tmp_path / "config" / "settings.yaml"
    database_file = tmp_path / "data" / "job_radar.sqlite3"
    settings_file.parent.mkdir(parents=True)
    write_settings_file(settings_file, database_file)
    app = create_app(settings_path=str(settings_file), base_directory=str(tmp_path))
    client = app.test_client()

    summary = client.get("/profile")
    create_page = client.get("/profile/new")

    assert summary.status_code == 200
    assert "Create your first profile" in summary.get_data(as_text=True)
    assert 'href="/profile/new"' in summary.get_data(as_text=True)
    assert "Unknown candidate" not in summary.get_data(as_text=True)
    assert create_page.status_code == 200
    assert "Back to profile summary" in create_page.get_data(as_text=True)
    assert "Cancel" in create_page.get_data(as_text=True)
    assert list_profiles(database_file, include_archived=True) == []


def test_profile_summary_and_edit_page_have_separate_jobs(tmp_path: Path) -> None:
    settings_file = tmp_path / "config" / "settings.yaml"
    database_file = tmp_path / "data" / "job_radar.sqlite3"
    settings_file.parent.mkdir(parents=True)
    write_settings_file(settings_file, database_file)
    app = create_app(settings_path=str(settings_file), base_directory=str(tmp_path))
    client = app.test_client()
    client.post("/profile/create", data={"display_name": "Kitchen Work"})
    profile = get_active_profile(database_file)

    assert profile is not None
    summary_html = client.get("/profile").get_data(as_text=True)
    edit_html = client.get(f"/profile/{profile.profile_id}/edit").get_data(
        as_text=True
    )

    assert "What junior will scan for" in summary_html
    assert "Companies" in summary_html
    assert "No companies configured" in summary_html
    assert 'href="/companies"' in summary_html
    assert "Manage companies" in summary_html
    assert f'href="/profile/{profile.profile_id}/edit"' in summary_html
    assert 'name="occupation_selections_json"' not in summary_html
    assert "Edit profile" in edit_html
    assert "Back to profile summary" in edit_html
    assert "Cancel" in edit_html
    assert 'name="occupation_selections_json"' in edit_html
    assert "Save changes" in edit_html


def test_search_preferences_creates_profile_and_guides_resume_upload(
    tmp_path: Path,
) -> None:
    settings_file = tmp_path / "config" / "settings.yaml"
    database_file = tmp_path / "data" / "job_radar.sqlite3"
    settings_file.parent.mkdir(parents=True)
    write_settings_file(settings_file, database_file)
    app = create_app(settings_path=str(settings_file), base_directory=str(tmp_path))
    client = app.test_client()

    response = client.post(
        "/preferences",
        data={
            "profile_mode": "create",
            "display_name": "Colorado Kitchen Work",
            "occupation_selections_json": json.dumps(
                [{"value": "35-2014.00", "label": "Cooks, Restaurant"}]
            ),
            "location_selections_json": "[]",
            "responsibility-level": ["Entry-level", "Mid-level"],
            "employment-type": ["Full-time", "Part-time"],
            "workplace-arrangement": ["On-site"],
            "schedule_preference": "Day shift",
            "on_call_preference": "Not willing to participate",
            "clearance_preference": "Review each job",
            "compensation_floor_usd": "60000",
            "travel_percentage": "10",
        },
    )

    assert response.status_code == 302
    assert "profile_result=created" in response.headers["Location"]
    profile = get_active_profile(database_file)
    assert profile is not None
    assert profile.display_name == "Colorado Kitchen Work"
    assert profile.preferences.target_roles == ("Cooks, Restaurant",)
    assert profile.preferences.on_call_preference == "Not willing to participate"
    assert profile.preferences.clearance_preference == "Review each job"

    handoff_page = client.get(response.headers["Location"]).get_data(as_text=True)
    assert "Profile created." in handoff_page
    assert "Choose Edit profile to add a résumé or make changes." in handoff_page


def test_search_preferences_rejects_duplicate_profile_name_without_partial_create(
    tmp_path: Path,
) -> None:
    settings_file = tmp_path / "config" / "settings.yaml"
    database_file = tmp_path / "data" / "job_radar.sqlite3"
    settings_file.parent.mkdir(parents=True)
    write_settings_file(settings_file, database_file)
    app = create_app(settings_path=str(settings_file), base_directory=str(tmp_path))
    client = app.test_client()
    client.post("/profile/create", data={"display_name": "Existing Search"})

    response = client.post(
        "/preferences",
        data={
            "profile_mode": "create",
            "display_name": "existing search",
            "occupation_selections_json": "[]",
            "location_selections_json": "[]",
            "schedule_preference": "Any schedule",
            "travel_percentage": "0",
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"].startswith("/profile/new?")
    assert len(list_profiles(database_file, include_archived=True)) == 1
    error_page = client.get(response.headers["Location"]).get_data(as_text=True)
    assert "A profile with that name already exists" in error_page


def test_search_preferences_save_normalized_profile_data(tmp_path: Path) -> None:
    settings_file = tmp_path / "config" / "settings.yaml"
    database_file = tmp_path / "data" / "job_radar.sqlite3"
    settings_file.parent.mkdir(parents=True)
    write_settings_file(settings_file, database_file)
    app = create_app(settings_path=str(settings_file), base_directory=str(tmp_path))
    client = app.test_client()
    client.post("/profile/create", data={"display_name": "Baker Search"})

    response = client.post(
        "/preferences",
        data={
            "profile_mode": "edit",
            "display_name": "Baker Search",
            "occupation_selections_json": json.dumps(
                [{"value": "51-3011.00", "label": "Bakers"}]
            ),
            "location_selections_json": json.dumps(
                [
                    {
                        "value": "place:0827425",
                        "label": "Fort Collins, Colorado",
                        "latitude": 40.5853,
                        "longitude": -105.0844,
                        "radius": 25,
                    }
                ]
            ),
            "responsibility-level": ["Entry-level", "Mid-level"],
            "employment-type": ["Full-time", "Part-time"],
            "workplace-arrangement": ["Hybrid", "On-site"],
            "schedule_preference": "Day shift",
            "on_call_preference": "Not willing to participate",
            "clearance_preference": "Review each job",
            "compensation_floor_usd": "60000",
            "travel_percentage": "10",
        },
    )

    assert response.status_code == 302
    assert "profile_result=preferences_saved" in response.headers["Location"]
    profile = get_active_profile(database_file)
    assert profile is not None
    assert profile.preferences.target_roles == ("Bakers",)
    assert profile.preferences.seniority_levels == ("Entry-level", "Mid-level")
    assert profile.preferences.employment_types == ("Full-time", "Part-time")
    assert profile.preferences.work_arrangements == ("Hybrid", "On-site")
    assert profile.preferences.schedule_preference == "Day shift"
    assert profile.preferences.compensation_floor_usd == 60000
    assert profile.preferences.travel_tolerance == "10"
    assert profile.preferences.occupation_selections[0].value == "51-3011.00"
    assert profile.preferences.location_selections[0].radius_miles == 25

    saved_page = client.get(response.headers["Location"]).get_data(as_text=True)
    assert "Profile saved" in saved_page
    assert "Fort Collins, Colorado" in saved_page


def test_search_preferences_reject_invalid_values_without_changing_profile(
    tmp_path: Path,
) -> None:
    settings_file = tmp_path / "config" / "settings.yaml"
    database_file = tmp_path / "data" / "job_radar.sqlite3"
    settings_file.parent.mkdir(parents=True)
    write_settings_file(settings_file, database_file)
    app = create_app(settings_path=str(settings_file), base_directory=str(tmp_path))
    client = app.test_client()
    client.post("/profile/create", data={"display_name": "Safe Search"})
    original = get_active_profile(database_file)

    response = client.post(
        "/preferences",
        data={
            "profile_mode": "edit",
            "display_name": "Safe Search",
            "occupation_selections_json": "[]",
            "location_selections_json": "[]",
            "responsibility-level": "Invented level",
            "schedule_preference": "Any schedule",
            "travel_percentage": "250",
        },
    )

    assert response.status_code == 302
    assert "preference_error=" in response.headers["Location"]
    assert get_active_profile(database_file) == original


def test_search_preferences_suggests_cross_industry_occupations(
    tmp_path: Path,
) -> None:
    settings_file = tmp_path / "config" / "settings.yaml"
    database_file = tmp_path / "data" / "job_radar.sqlite3"
    settings_file.parent.mkdir(parents=True)
    write_settings_file(settings_file, database_file)
    app = create_app(settings_path=str(settings_file), base_directory=str(tmp_path))
    client = app.test_client()

    baker_results = client.get(
        "/preferences/occupation-suggestions?q=baker"
    ).get_json()
    cook_results = client.get(
        "/preferences/occupation-suggestions?q=head+cook"
    ).get_json()
    platform_results = client.get(
        "/preferences/occupation-suggestions?q=platform+engineer"
    ).get_json()
    catering_results = client.get(
        "/preferences/occupation-suggestions?q=catering+coordinator"
    ).get_json()

    assert any("Baker" in item["label"] for item in baker_results)
    assert any("Cook" in item["label"] for item in cook_results)
    assert any("Platform Engineer" in item["label"] for item in platform_results)
    assert any("Catering Coordinator" in item["label"] for item in catering_results)


def test_search_preferences_normalizes_location_suggestions(
    tmp_path: Path,
) -> None:
    settings_file = tmp_path / "config" / "settings.yaml"
    database_file = tmp_path / "data" / "job_radar.sqlite3"
    settings_file.parent.mkdir(parents=True)
    write_settings_file(settings_file, database_file)
    app = create_app(settings_path=str(settings_file), base_directory=str(tmp_path))
    client = app.test_client()

    abbreviated = client.get(
        "/preferences/location-suggestions?q=Ft+Collins+CO"
    ).get_json()
    spelled_out = client.get(
        "/preferences/location-suggestions?q=Fort+Collins+Colorado"
    ).get_json()
    zip_results = client.get(
        "/preferences/location-suggestions?q=80525"
    ).get_json()

    assert abbreviated[0]["label"] == "Fort Collins, Colorado"
    assert spelled_out[0]["label"] == "Fort Collins, Colorado"
    assert zip_results[0]["label"] == "ZIP 80525 — Fort Collins, Colorado"

    radius_result = client.get(
        "/preferences/location-radius"
        "?latitude=40.5383&longitude=-105.0563&miles=25"
    ).get_json()
    assert radius_result["center_city"] == "Fort Collins, Colorado"
    featured_labels = [item["label"] for item in radius_result["featured_cities"]]
    assert "Fort Collins, Colorado" in featured_labels
    assert "Loveland, Colorado" in featured_labels
    assert radius_result["covered_community_count"] > len(featured_labels)
    assert not set(featured_labels) & {
        item["label"] for item in radius_result["additional_cities"]
    }

    wide_radius = client.get(
        "/preferences/location-radius"
        "?latitude=40.5383&longitude=-105.0563&miles=100"
    ).get_json()
    wide_featured = [item["label"] for item in wide_radius["featured_cities"]]
    wide_additional = [item["label"] for item in wide_radius["additional_cities"]]
    assert len(wide_featured) == 10
    assert "Boulder, Colorado" in wide_featured
    assert "Denver, Colorado" in wide_featured
    assert not set(wide_featured) & set(wide_additional)


def test_profile_page_resolves_relative_paths_from_runtime_base(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repository_root = tmp_path / "repository"
    user_data_root = tmp_path / "user-data"
    settings_file = user_data_root / "config" / "settings.yaml"
    profile_file = user_data_root / "profiles" / "example" / "profile.yaml"
    resume_file = user_data_root / "profiles" / "example" / "resume.md"
    normalized_resume_file = (
        user_data_root
        / "profiles"
        / "example"
        / "resume.normalized.txt"
    )

    repository_root.mkdir()
    settings_file.parent.mkdir(parents=True)
    profile_file.parent.mkdir(parents=True)
    monkeypatch.chdir(repository_root)

    settings_file.write_text(
        """
database_path: data/job_radar.sqlite3
reports_path: reports
logs_path: logs
candidate_profile_path: profiles/example/profile.yaml

""",
        encoding="utf-8",
    )
    profile_file.write_text(
        """
candidate:
  name: Example Candidate
  resume:
    source_path: profiles/example/resume.md
    normalized_text_path: profiles/example/resume.normalized.txt
  core_strengths:
    - Linux infrastructure
  credible_adjacent: []
  learning_or_gap: []
  avoid: []
""",
        encoding="utf-8",
    )
    resume_file.write_text(
        "# Example Candidate\n\nLinux infrastructure",
        encoding="utf-8",
    )
    normalized_resume_file.write_text(
        "example candidate linux infrastructure\n",
        encoding="utf-8",
    )

    app = create_app(
        settings_path=str(settings_file),
        base_directory=str(user_data_root),
    )
    client = app.test_client()

    response = client.get("/profile")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Example Candidate" in html
    assert "Profile and resume available" in html
    assert "Linux infrastructure" in html
    assert str(profile_file) in html
    assert str(resume_file) in html
    assert str(normalized_resume_file) in html
    assert str(repository_root / "profiles") not in html


def test_main_pages_share_full_navigation(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"
    profile_file = tmp_path / "profile.yaml"
    resume_file = tmp_path / "resume.md"

    write_settings_file(settings_file, database_file)
    settings_file.write_text(
        settings_file.read_text(encoding="utf-8")
        + f"\ncandidate_profile_path: {profile_file}\n",
        encoding="utf-8",
    )
    resume_file.write_text(
        "# Example Candidate\n\nLarge-scale Linux and HPC operations.",
        encoding="utf-8",
    )
    profile_file.write_text(
        f"""
candidate:
  name: Example Candidate
  resume:
    source_path: {resume_file}
  core_strengths: []
  credible_adjacent: []
  learning_or_gap: []
  avoid: []
""",
        encoding="utf-8",
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    for route in [
        "/tracker",
        "/history",
        "/profile",
        "/reports",
        "/scan",
    ]:
        response = client.get(route)
        html = response.get_data(as_text=True)

        normalized_html = " ".join(html.split())

        assert response.status_code == 200
        assert 'href="/"' in normalized_html
        assert ">Home</a>" in normalized_html
        assert 'href="/tracker"' in normalized_html
        assert ">Active Applications</a>" in normalized_html
        assert 'href="/history"' in normalized_html
        assert ">Application History</a>" in normalized_html
        assert 'href="/profile"' in normalized_html
        assert ">Profile / Resume</a>" in normalized_html
        assert ">Search Preferences</a>" not in normalized_html
        assert 'href="/reports"' in normalized_html
        assert ">Reports</a>" in normalized_html
        assert 'href="/scan"' in normalized_html
        assert ">Scan</a>" in normalized_html
        assert "active-nav" in normalized_html


def test_navigation_marks_current_page_active(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"
    profile_file = tmp_path / "profile.yaml"
    resume_file = tmp_path / "resume.md"

    write_settings_file(settings_file, database_file)
    settings_file.write_text(
        settings_file.read_text(encoding="utf-8")
        + f"\ncandidate_profile_path: {profile_file}\n",
        encoding="utf-8",
    )
    resume_file.write_text(
        "# Example Candidate\n\nLarge-scale Linux and HPC operations.",
        encoding="utf-8",
    )
    profile_file.write_text(
        f"""
candidate:
  name: Example Candidate
  resume:
    source_path: {resume_file}
  core_strengths: []
  credible_adjacent: []
  learning_or_gap: []
  avoid: []
""",
        encoding="utf-8",
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    expected_active_links = {
        "/": '<a class="active-nav" href="/" aria-current="page">Home</a>',
        "/tracker": (
            '<a class="active-nav" href="/tracker" '
            'aria-current="page">Active Applications</a>'
        ),
        "/history": (
            '<a class="active-nav" href="/history" '
            'aria-current="page">Application History</a>'
        ),
        "/profile": (
            '<a class="active-nav" href="/profile" '
            'aria-current="page">Profile / Resume</a>'
        ),
        "/reports": (
            '<a class="active-nav" href="/reports" '
            'aria-current="page">Reports</a>'
        ),
        "/scan": (
            '<a class="active-nav" href="/scan" '
            'aria-current="page">Scan</a>'
        ),
        "/settings/about": (
            '<a class="active-nav" href="/settings" '
            'aria-current="page">Settings</a>'
        ),
        "/settings/diagnostics": (
            '<a class="active-nav" href="/settings" '
            'aria-current="page">Settings</a>'
        ),
        "/settings/email": (
            '<a class="active-nav" href="/settings" '
            'aria-current="page">Settings</a>'
        ),
        "/settings/retention": (
            '<a class="active-nav" href="/settings" '
            'aria-current="page">Settings</a>'
        ),
        "/settings/schedule": (
            '<a class="active-nav" href="/settings" '
            'aria-current="page">Settings</a>'
        ),
    }

    for route, expected_link in expected_active_links.items():
        response = client.get(route)
        normalized_html = " ".join(response.get_data(as_text=True).split())

        assert response.status_code == 200
        assert expected_link in normalized_html

    compatibility_response = client.get("/preferences")
    assert compatibility_response.status_code == 302
    assert compatibility_response.headers["Location"] == "/profile"


def test_shared_page_shell_supports_keyboard_and_scaled_views(
    tmp_path: Path,
) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"
    write_settings_file(settings_file, database_file)
    mark_existing_installation(database_file)
    app = create_app(settings_path=str(settings_file))

    html = app.test_client().get("/").get_data(as_text=True)

    assert 'name="viewport" content="width=device-width, initial-scale=1"' in html
    assert 'class="skip-link" href="#main-content"' in html
    assert '<main id="main-content" class="page" tabindex="-1">' in html
    assert ":focus-visible" in html
    assert "@media (max-width: 800px)" in html
    assert "@media (forced-colors: active)" in html


def test_supported_job_platforms_are_visible_without_employers(
    tmp_path: Path,
) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"
    write_settings_file(settings_file, database_file)

    app = create_app(settings_path=str(settings_file), base_directory=tmp_path)
    client = app.test_client()

    settings_html = client.get("/settings").get_data(as_text=True)
    response = client.get("/settings/job-platforms")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "View Collector Catalog" in settings_html
    assert "Collector Catalog" in html
    assert "separate from the" in html
    assert "global Employer Catalog" in html
    assert "Greenhouse" in html
    assert "ADP Workforce Now" in html
    assert "Workday" in html
    assert "USAJOBS" in html
    assert "Standard public careers page" in html
    with connect_database(database_file) as connection:
        employer_count = connection.execute(
            "SELECT COUNT(*) FROM employer_sources"
        ).fetchone()
    assert employer_count is not None and employer_count[0] == 0


def test_web_startup_imports_pending_legacy_companies(
    tmp_path: Path,
) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"
    company_file = tmp_path / "config" / "target-companies.yaml"
    company_file.parent.mkdir(parents=True)
    write_settings_file(settings_file, database_file)
    company_file.write_text(
        """
companies:
  - company_key: example_bakery
    name: Example Bakery
    source_type: html
    enabled: true
    source_url: https://example.invalid/careers
""",
        encoding="utf-8",
    )
    profile = ManagedProfile(
        profile_id="profile_aaaaaaaa",
        display_name="Example User",
    )
    create_profile(database_file, profile)
    set_active_profile(database_file, profile.profile_id)
    with connect_database(database_file) as connection:
        connection.execute(
            """
            UPDATE profiles
            SET legacy_company_import_pending = 1
            WHERE profile_id = ?
            """,
            (profile.profile_id,),
        )

    app = create_app(
        settings_path=str(settings_file),
        base_directory=tmp_path,
    )
    response = app.test_client().get("/companies")

    assert response.status_code == 200
    assert "Example Bakery" in response.get_data(as_text=True)
    with connect_database(database_file) as connection:
        pending = connection.execute(
            """
            SELECT legacy_company_import_pending
            FROM profiles
            WHERE profile_id = ?
            """,
            (profile.profile_id,),
        ).fetchone()
        employer_count = connection.execute(
            "SELECT COUNT(*) FROM employer_sources"
        ).fetchone()
        association_count = connection.execute(
            "SELECT COUNT(*) FROM profile_company_associations"
        ).fetchone()
    assert pending is not None and pending[0] == 0
    assert employer_count is not None and employer_count[0] == 1
    assert association_count is not None and association_count[0] == 1
