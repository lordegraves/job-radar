import io
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from job_radar.application_info_service import build_application_info
from job_radar.diagnostic_service import build_diagnostics_view
from job_radar.profile_models import ManagedProfile, ProfilePreferences
from job_radar.profile_storage import create_profile
from job_radar.runtime_paths import RuntimePaths
from job_radar.storage import complete_scan_run, initialize_database, start_scan_run
from job_radar.support_bundle_service import build_support_bundle


def test_support_bundle_contains_safe_reproduction_data_only(tmp_path: Path) -> None:
    database = tmp_path / "data" / "job_radar.sqlite3"
    reports = tmp_path / "reports"
    logs = tmp_path / "logs"
    resumes = tmp_path / "resumes"
    for directory in (database.parent, reports, logs, resumes):
        directory.mkdir(parents=True)
    initialize_database(database)
    profile = ManagedProfile(
        profile_id="profile_1234abcd",
        display_name="Support Profile",
        preferences=ProfilePreferences(target_roles=("Analyst",)),
    )
    create_profile(database, profile)
    settings = tmp_path / "settings.yaml"
    settings.write_text(
        f"database_path: {database}\n"
        f"reports_path: {reports}\n"
        f"logs_path: {logs}\n",
        encoding="utf-8",
    )
    (reports / "target-scan.json").write_text('{"summary": {}}', encoding="utf-8")
    (reports / "target-scan-raw.zip").write_bytes(b"private raw scan")
    (logs / "junior-diagnostics.log").write_text("safe log", encoding="utf-8")
    (logs / "junior-application.log").write_text(
        '{"event":"company_discovery","attempt_id":"safe-123"}\n',
        encoding="utf-8",
    )
    (logs / "arbitrary.log").write_text("not allowlisted", encoding="utf-8")
    (resumes / "resume.pdf").write_bytes(b"resume contents")
    runtime = RuntimePaths.from_settings(settings, base_directory=tmp_path)
    application_info = build_application_info(
        database_path=database,
        user_data_location=tmp_path,
    )
    diagnostics = build_diagnostics_view(database, settings)

    bundle = build_support_bundle(
        runtime,
        application_info,
        diagnostics,
        profile.profile_id,
        now=datetime(2026, 8, 5, 12, 30, tzinfo=UTC),
    )

    assert bundle.filename == "junior-troubleshooting-20260805-123000.zip"
    with zipfile.ZipFile(io.BytesIO(bundle.content)) as archive:
        names = set(archive.namelist())
        assert "configuration/junior-profile-configuration.json" in names
        assert "configuration/junior-company-catalog.json" in names
        assert "logs/junior-diagnostics.log" in names
        assert "logs/junior-application.log" in names
        assert b"safe-123" in archive.read("logs/junior-application.log")
        assert "manifest.json" in names
        assert "README.txt" in names
        assert not any("resume" in name.casefold() for name in names)
        assert "latest-scan/target-scan-raw.zip" not in names
        assert "logs/arbitrary.log" not in names
        assert not any(name.endswith(".sqlite3") for name in names)
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["selected_profile"] == "Support Profile"
        assert manifest["matching_scan_included"] is False

    scan_id = start_scan_run(
        database,
        requested_at="2026-08-05T12:00:00+00:00",
        companies_requested=1,
        companies_enabled=1,
        profile_id=profile.profile_id,
    )
    complete_scan_run(
        database,
        scan_run_id=scan_id,
        generated_at="2026-08-05T12:01:00+00:00",
        finished_at="2026-08-05T12:01:00+00:00",
        companies_scanned=1,
        jobs_collected=0,
        actionable_jobs_stored=0,
        jobs_not_actionable=0,
        jobs_new=0,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=0,
        top_matches_count=0,
        review_needed_count=0,
        report_status="completed",
        email_status="disabled",
    )
    matching_bundle = build_support_bundle(
        runtime,
        application_info,
        diagnostics,
        profile.profile_id,
        now=datetime(2026, 8, 5, 12, 31, tzinfo=UTC),
    )
    with zipfile.ZipFile(io.BytesIO(matching_bundle.content)) as archive:
        matching_names = set(archive.namelist())
        matching_manifest = json.loads(archive.read("manifest.json"))
    assert "latest-scan/target-scan.json" in matching_names
    assert matching_manifest["matching_scan_included"] is True
