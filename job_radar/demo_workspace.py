"""Build a deterministic fictional workspace for documentation and release QA.

The generator never reads an existing Junior workspace. It builds beside the
requested destination and publishes the result only after every record has
been created successfully.
"""

from pathlib import Path
import gc
import json
import shutil
import time
from uuid import uuid4

from job_radar.employer_models import EmployerSource
from job_radar.employer_storage import upsert_employer_source
from job_radar.history_models import JobHistoryRecord
from job_radar.models import JobPosting
from job_radar.profile_models import (
    FitSignal,
    LocationPreference,
    ManagedProfile,
    ManagedResume,
    OccupationPreference,
    ProfilePreferences,
)
from job_radar.profile_storage import create_and_select_profile
from job_radar.runtime_paths import UserDataPaths
from job_radar.storage import (
    complete_scan_run,
    initialize_database,
    start_scan_run,
    upsert_job_history_record,
    upsert_job_posting,
)
from job_radar.tracker.tracker_models import ApplicationRecord
from job_radar.tracker.tracker_storage import upsert_application
from job_radar.user_data_bootstrap import bootstrap_packaged_user_configuration


DEMO_PROFILE_ID = "profile_demo1234"


class DemoWorkspaceError(RuntimeError):
    """Raised when a safe fictional workspace cannot be created."""


def create_demo_workspace(destination: str | Path) -> UserDataPaths:
    """Create one complete fictional workspace without overwriting any path."""

    destination_path = Path(destination).expanduser().resolve()
    if destination_path.exists():
        raise DemoWorkspaceError(
            f"Demo destination already exists: {destination_path}"
        )

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    build_path = destination_path.with_name(
        f".{destination_path.name}.building-{uuid4().hex}"
    )
    paths = UserDataPaths.from_root(build_path)

    try:
        bootstrap_packaged_user_configuration(user_data_paths=paths)
        database_path = initialize_database(
            paths.data / "job_radar.sqlite3"
        )
        _seed_employers(database_path)
        _seed_profile(database_path, paths)
        _seed_scan(database_path)
        _seed_report(paths)
        _seed_applications(database_path)
        _seed_history(database_path)
        _publish_completed_build(build_path, destination_path)
    except Exception:
        _remove_failed_build(build_path)
        raise

    return UserDataPaths.from_root(destination_path)


def _publish_completed_build(build_path: Path, destination_path: Path) -> None:
    """Atomically expose a complete build after SQLite releases its handles."""

    for attempt in range(3):
        gc.collect()
        try:
            build_path.replace(destination_path)
            return
        except PermissionError:
            if attempt == 2:
                raise
            time.sleep(0.05)


def _remove_failed_build(build_path: Path) -> None:
    """Remove only this generator's private build directory after a failure."""

    if not build_path.exists():
        return

    # SQLite objects referenced by an active traceback can hold a Windows file
    # handle briefly. A bounded retry prevents that handle from hiding the real
    # generation error or leaving an abandoned private build directory.
    for attempt in range(3):
        gc.collect()
        try:
            shutil.rmtree(build_path)
            return
        except PermissionError:
            if attempt == 2:
                raise
            time.sleep(0.05)


def _seed_employers(database_path: Path) -> None:
    for employer in (
        EmployerSource(
            employer_id="northstar_foods",
            name="Northstar Foods",
            source_type="html",
            source_config={
                "source_url": "https://northstar-foods.invalid/careers",
                "tags": ["baker", "food production"],
            },
            notes="Fictional employer for Junior demonstrations.",
        ),
        EmployerSource(
            employer_id="harborview_university",
            name="Harborview University",
            source_type="html",
            source_config={
                "source_url": "https://harborview-university.invalid/jobs",
                "tags": ["cook", "catering"],
            },
            notes="Fictional employer for Junior demonstrations.",
        ),
        EmployerSource(
            employer_id="meadow_market",
            name="Meadow Market",
            source_type="html",
            source_config={
                "source_url": "https://meadow-market.invalid/work-with-us",
                "tags": ["baker", "prepared foods"],
            },
            notes="Fictional employer for Junior demonstrations.",
        ),
    ):
        upsert_employer_source(database_path, employer)


def _seed_profile(database_path: Path, paths: UserDataPaths) -> None:
    resume_directory = paths.resumes / DEMO_PROFILE_ID
    resume_directory.mkdir(parents=True, exist_ok=True)
    resume_text = (
        "# Jordan Rivera\n\n"
        "Food-service professional with experience in scratch baking, "
        "high-volume kitchen preparation, inventory rotation, food safety, "
        "and coordinating catered events.\n"
    )
    (resume_directory / "resume.md").write_text(
        resume_text,
        encoding="utf-8",
    )
    (resume_directory / "resume.normalized.txt").write_text(
        resume_text,
        encoding="utf-8",
    )

    create_and_select_profile(
        database_path,
        ManagedProfile(
            profile_id=DEMO_PROFILE_ID,
            display_name="Jordan Rivera",
            resume=ManagedResume(source_file_name="resume.md"),
            company_ids=(
                "northstar_foods",
                "harborview_university",
                "meadow_market",
            ),
            preferences=ProfilePreferences(
                target_roles=(
                    "Baker",
                    "Catering Coordinator",
                    "Head Cook",
                ),
                seniority_levels=("Mid-level", "Senior"),
                core_strengths=(
                    "scratch baking",
                    "food safety",
                    "high-volume preparation",
                ),
                credible_adjacent=(
                    "catering coordination",
                    "prepared-food operations",
                ),
                learning_or_gap=("large-team scheduling",),
                exclusions=("commission-only sales",),
                preferred_locations=("Madison, Wisconsin",),
                work_arrangements=("On-site", "Hybrid"),
                employment_types=("Full-time", "Contract"),
                schedule_preference="Day shift",
                occupation_selections=(
                    OccupationPreference(
                        value="51-3011.00",
                        label="Bakers",
                    ),
                    OccupationPreference(
                        value="35-1011.00",
                        label="Chefs and Head Cooks",
                    ),
                ),
                location_selections=(
                    LocationPreference(
                        value="place:5548000",
                        label="Madison, Wisconsin",
                        radius_miles=25,
                        latitude=43.0731,
                        longitude=-89.4012,
                    ),
                ),
                compensation_floor_usd=52000,
                travel_tolerance="10",
                on_call_preference="Not willing to participate",
            ),
            fit_signals=(
                FitSignal(
                    term="scratch baking",
                    category="strong",
                    explanation="Demonstrated in the fictional résumé.",
                    evidence_source="resume",
                ),
                FitSignal(
                    term="food safety",
                    category="strong",
                    explanation="Demonstrated in the fictional résumé.",
                    evidence_source="resume",
                ),
                FitSignal(
                    term="large-team scheduling",
                    category="review",
                    explanation="Experience is not yet clear.",
                    evidence_source="profile",
                ),
                FitSignal(
                    term="commission-only sales",
                    category="avoid",
                    explanation="The fictional profile excludes this work.",
                    evidence_source="profile",
                ),
            ),
        ),
    )


def _seed_scan(database_path: Path) -> None:
    scan_run_id = start_scan_run(
        database_path,
        requested_at="2026-07-20T13:00:00+00:00",
        companies_requested=3,
        companies_enabled=3,
        profile_id=DEMO_PROFILE_ID,
    )
    postings = (
        JobPosting(
            company_key="northstar_foods",
            company_name="Northstar Foods",
            source_type="html",
            source_job_id="demo-101",
            source_url="https://northstar-foods.invalid/jobs/demo-101",
            title="Production Baker",
            location="Madison, Wisconsin",
            remote_status="On-site",
            salary_text="$55,000 - $62,000",
            description=(
                "Prepare scratch breads and pastries, maintain food-safety "
                "records, and coordinate daily production."
            ),
            canonical_key="northstar-foods:production-baker:madison-wisconsin",
            content_hash="demo-northstar-production-baker-v1",
        ),
        JobPosting(
            company_key="harborview_university",
            company_name="Harborview University",
            source_type="html",
            source_job_id="demo-202",
            source_url="https://harborview-university.invalid/jobs/demo-202",
            title="Catering Coordinator",
            location="Madison, Wisconsin",
            remote_status="Hybrid",
            salary_text="$58,000 - $66,000",
            description=(
                "Coordinate campus catering events, production schedules, "
                "inventory, and client details."
            ),
            canonical_key=(
                "harborview-university:catering-coordinator:madison-wisconsin"
            ),
            content_hash="demo-harborview-catering-coordinator-v1",
        ),
        JobPosting(
            company_key="meadow_market",
            company_name="Meadow Market",
            source_type="html",
            source_job_id="demo-303",
            source_url="https://meadow-market.invalid/jobs/demo-303",
            title="Bakery Team Lead",
            location="Middleton, Wisconsin",
            remote_status="On-site",
            salary_text="$27 - $31 per hour",
            description=(
                "Lead bakery production, coach a small team, rotate stock, "
                "and maintain sanitation standards."
            ),
            canonical_key="meadow-market:bakery-team-lead:middleton-wisconsin",
            content_hash="demo-meadow-bakery-team-lead-v1",
        ),
    )
    for posting in postings:
        upsert_job_posting(
            database_path,
            posting,
            scan_run_id=scan_run_id,
        )

    complete_scan_run(
        database_path,
        scan_run_id=scan_run_id,
        generated_at="2026-07-20T13:04:00+00:00",
        finished_at="2026-07-20T13:04:00+00:00",
        companies_scanned=3,
        jobs_collected=3,
        actionable_jobs_stored=3,
        jobs_not_actionable=0,
        jobs_new=3,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=0,
        top_matches_count=2,
        review_needed_count=1,
        report_status="not_requested",
        email_status="not_requested",
    )


def _seed_report(paths: UserDataPaths) -> None:
    """Create the fictional report snapshot used by GUI release checks."""

    def job(
        *,
        title: str,
        company: str,
        location: str,
        compensation: str,
        job_id: str,
        action: str,
        rationale: str,
        match: str,
        risks: str,
        eligibility: str,
        eligibility_reasons: list[str],
    ) -> dict[str, object]:
        return {
            "title": title,
            "url": f"https://{company.lower().replace(' ', '-')}.invalid/jobs/{job_id}",
            "company": company,
            "location": location,
            "compensation": compensation,
            "hiring_probability": "Medium",
            "recommended_action": action,
            "action_rationale": rationale,
            "why_matched": match,
            "technical_match": "Strong",
            "resume_match": "Strong",
            "resume_evidence": match,
            "resume_gaps": "None identified from the fictional résumé.",
            "hiring_risks": risks,
            "history_context": "No earlier decision is recorded.",
            "history_risk": None,
            "job_radar_id": job_id,
            "eligibility_status": eligibility,
            "eligibility_reasons": eligibility_reasons,
        }

    top_match = job(
        title="Production Baker",
        company="Northstar Foods",
        location="Madison, Wisconsin",
        compensation="$55,000 - $62,000",
        job_id="jr-demo-report-101",
        action="Apply",
        rationale=(
            "The role matches demonstrated baking and food-safety work, "
            "and its practical requirements fit this profile."
        ),
        match="scratch baking, food safety, production planning",
        risks="No major concerns identified.",
        eligibility="Eligible",
        eligibility_reasons=[
            "The on-site location is inside the selected commuting area.",
            "The listed compensation meets the profile minimum.",
        ],
    )
    review_job = job(
        title="Catering Operations Coordinator",
        company="Harborview University",
        location="Madison, Wisconsin",
        compensation="Not listed",
        job_id="jr-demo-report-202",
        action="Review",
        rationale=(
            "The work looks relevant, but the posting does not provide enough "
            "schedule or compensation detail for a final decision."
        ),
        match="catering coordination, inventory, event preparation",
        risks="Schedule and compensation need confirmation.",
        eligibility="Needs Review",
        eligibility_reasons=[
            "The posting does not list usable compensation.",
            "The work schedule is unclear.",
        ],
    )
    passed_job = job(
        title="Commission Bakery Sales Representative",
        company="Meadow Market",
        location="Remote",
        compensation="Commission only",
        job_id="jr-demo-report-303",
        action="Pass",
        rationale=(
            "The role is primarily commission sales, which this profile "
            "explicitly excludes."
        ),
        match="food-service industry knowledge",
        risks="The primary duties conflict with the profile.",
        eligibility="Not Eligible",
        eligibility_reasons=[
            "Commission-only sales is excluded by this profile."
        ],
    )
    snapshot = {
        "schema_version": 2,
        "summary": {
            "generated_at": "2026-07-20T13:04:00+00:00",
            "top_matches": 1,
            "review_needed": 1,
            "tracked_applications": 0,
            "new_jobs": 2,
            "collector_errors": 0,
        },
        "top_matches": [top_match],
        "review_needed": [review_job],
        "tracked_applications": [],
        "new_jobs": [top_match, review_job],
        "passed_not_recommended": [passed_job],
        "collector_errors": [],
    }
    paths.reports.mkdir(parents=True, exist_ok=True)
    (paths.reports / "target-scan.json").write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (paths.reports / "target-scan.html").write_text(
        "<!doctype html><html><body><h1>Fictional Junior scan</h1>"
        "<p>This report contains demonstration data only.</p></body></html>\n",
        encoding="utf-8",
    )


def _seed_applications(database_path: Path) -> None:
    for application in (
        ApplicationRecord(
            job_radar_id="jr-demo-northstar",
            company_name="Northstar Foods",
            role_title="Production Baker",
            source_url="https://northstar-foods.invalid/jobs/demo-101",
            status="Applied",
            follow_up_on="2026-07-27",
            outcome="Pending / In Progress",
            notes="Application submitted through the fictional careers page.",
            applied_on="2026-07-20",
            last_activity_on="2026-07-20",
        ),
        ApplicationRecord(
            job_radar_id="jr-demo-harborview",
            company_name="Harborview University",
            role_title="Catering Coordinator",
            source_url="https://harborview-university.invalid/jobs/demo-202",
            status="Applied",
            follow_up_on="2026-07-25",
            outcome="Interview Scheduled",
            notes="First interview scheduled with the fictional hiring team.",
            applied_on="2026-07-18",
            last_activity_on="2026-07-22",
        ),
        ApplicationRecord(
            job_radar_id="jr-demo-meadow",
            company_name="Meadow Market",
            role_title="Bakery Team Lead",
            source_url="https://meadow-market.invalid/jobs/demo-303",
            status="Applied",
            outcome="Pending / In Progress",
            notes="Review schedule and team-lead responsibilities.",
            last_activity_on="2026-07-21",
        ),
    ):
        upsert_application(
            database_path,
            application,
            profile_id=DEMO_PROFILE_ID,
        )


def _seed_history(database_path: Path) -> None:
    for record in (
        JobHistoryRecord(
            history_type="Application",
            company="Lakeview Hotel",
            role="Pastry Cook",
            source="Fictional careers page",
            ats_platform="html",
            work_arrangement="On-site",
            location="Madison, Wisconsin",
            comp_range="$50,000 - $56,000",
            event_date="2026-06-15",
            status="Rejected",
            outcome_category="Not selected",
            recruiter_contact=None,
            technical_match="Strong",
            hiring_probability=None,
            skills_signals="scratch baking; food safety",
            primary_blocker="Another candidate was selected.",
            secondary_blocker=None,
            revisit="Yes",
            include_in_job_radar=True,
            import_key="demo-history-lakeview",
            notes="Fictional historical application.",
        ),
        JobHistoryRecord(
            history_type="Application",
            company="Capitol Catering",
            role="Event Cook",
            source="Fictional careers page",
            ats_platform="html",
            work_arrangement="On-site",
            location="Madison, Wisconsin",
            comp_range="$24 - $27 per hour",
            event_date="2026-05-09",
            status="Withdrawn",
            outcome_category="Withdrawn",
            recruiter_contact=None,
            technical_match="Medium",
            hiring_probability=None,
            skills_signals="event preparation; inventory",
            primary_blocker="Schedule did not fit the profile.",
            secondary_blocker=None,
            revisit="No",
            include_in_job_radar=True,
            import_key="demo-history-capitol",
            notes="Fictional historical application.",
        ),
    ):
        upsert_job_history_record(
            database_path,
            record,
            profile_id=DEMO_PROFILE_ID,
        )
