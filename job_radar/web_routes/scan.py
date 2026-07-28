"""Serve manual scan controls and progress updates for the web interface."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from flask import Flask, flash, jsonify, redirect, render_template, request, url_for

from job_radar.runtime_paths import (
    DEFAULT_EMAIL_PREVIEW_PATH,
    DEFAULT_REPORT_PATH,
    RuntimePaths,
)
from job_radar.company_workspace_service import build_company_workspace
from job_radar.report_snapshot import load_report_snapshot
from job_radar.scan_task_runner import ScanTaskRunner
from job_radar.storage import fetch_active_scan_run, fetch_latest_scan_run


def register_scan_routes(
    app: Flask,
    *,
    get_runtime_paths: Callable[[], RuntimePaths],
    handle_scan_func: Callable[..., Any],
) -> None:
    """Register manual scan execution and progress routes."""
    scan_runner = ScanTaskRunner(handle_scan_func)
    app.extensions["junior_scan_runner"] = scan_runner

    @app.get("/scan")
    def scan() -> str:
        runtime_paths = get_runtime_paths()
        scan_status = _build_scan_status_payload(
            runtime_paths.database_path
        )
        snapshot_name = (
            "targeted-scan.json"
            if scan_status.get("trigger_source") == "manual:selected"
            else "target-scan.json"
        )
        scan_summary = _build_latest_scan_summary(
            runtime_paths.reports_path / snapshot_name,
            scan_status=scan_status,
        )

        return render_template(
            "scan.html",
            scan_result=request.args.get("scan_result"),
            scan_error=request.args.get("scan_error", "").strip(),
            scan_status=scan_status,
            scan_summary=scan_summary,
            company_workspace=build_company_workspace(
                runtime_paths.database_path
            ),
        )

    @app.get("/scan/status")
    def scan_status():
        runtime_paths = get_runtime_paths()

        return jsonify(
            _build_scan_status_payload(
                runtime_paths.database_path,
                scan_runner=scan_runner,
            )
        )

    @app.post("/scan/run")
    def run_scan():
        runtime_paths = get_runtime_paths()

        if fetch_active_scan_run(runtime_paths.database_path) is not None:
            return jsonify({"status": "busy"}), 409

        started = scan_runner.start(
            config_path=str(runtime_paths.company_config_path),
            settings_path=str(runtime_paths.settings_path),
            report_path=str(runtime_paths.resolve(DEFAULT_REPORT_PATH)),
            scoring_path=str(runtime_paths.scoring_config_path),
            email_preview_path=str(
                runtime_paths.resolve(DEFAULT_EMAIL_PREVIEW_PATH)
            ),
            send_email=False,
            base_directory=str(runtime_paths.base_directory),
            trigger_source="manual",
        )

        if not started:
            return jsonify({"status": "busy"}), 409

        return jsonify({"status": "starting"}), 202

    @app.post("/scan/run-selected")
    def run_selected_scan():
        runtime_paths = get_runtime_paths()
        selected = tuple(
            dict.fromkeys(
                item.strip()
                for item in request.form.getlist("employer_id")
                if item.strip()
            )
        )
        if not selected:
            if request.accept_mimetypes.best == "application/json":
                return jsonify(
                    {
                        "status": "error",
                        "message": "Select at least one company to scan.",
                    }
                ), 400
            flash("Select at least one company to scan.", "error")
            return redirect(url_for("scan"))
        if len(selected) > 25:
            if request.accept_mimetypes.best == "application/json":
                return jsonify(
                    {
                        "status": "error",
                        "message": "Select no more than 25 companies.",
                    }
                ), 400
            flash(
                "Select no more than 25 companies for one targeted scan.",
                "error",
            )
            return redirect(url_for("scan"))
        if fetch_active_scan_run(runtime_paths.database_path) is not None:
            if request.accept_mimetypes.best == "application/json":
                return jsonify({"status": "busy"}), 409
            flash("A scan is already running.", "error")
            return redirect(url_for("scan"))

        targeted_report = runtime_paths.reports_path / "targeted-scan.html"
        targeted_email = runtime_paths.reports_path / "targeted-email-preview.txt"
        started = scan_runner.start(
            config_path=str(runtime_paths.company_config_path),
            settings_path=str(runtime_paths.settings_path),
            report_path=str(targeted_report),
            scoring_path=str(runtime_paths.scoring_config_path),
            email_preview_path=str(targeted_email),
            send_email=False,
            base_directory=str(runtime_paths.base_directory),
            trigger_source="manual:selected",
            selected_employer_ids=list(selected),
        )
        if started:
            flash(
                f"Scanning {len(selected)} selected company source(s). "
                "The latest full-scan report will not be replaced.",
                "success",
            )
        else:
            flash("A scan is already running.", "error")
        if request.accept_mimetypes.best == "application/json":
            return (
                jsonify(
                    {
                        "status": "starting" if started else "busy",
                        "scan_type": "selected",
                    }
                ),
                202 if started else 409,
            )
        return redirect(
            url_for(
                "scan",
                targeted_scan="started" if started else "busy",
            )
        )


def _build_latest_scan_summary(
    snapshot_path: str | Path,
    *,
    scan_status: dict[str, object],
) -> dict[str, object]:
    """Build a safe, plain-language summary from the latest full scan."""
    path = Path(snapshot_path)
    if not path.is_file():
        return {
            "available": False,
            "generated_at": None,
            "jobs_found": int(scan_status.get("jobs_found") or 0),
            "errors": [],
        }

    try:
        snapshot = load_report_snapshot(path)
    except (KeyError, OSError, TypeError, ValueError):
        # A damaged or older snapshot must not break the Scan page.
        return {
            "available": False,
            "generated_at": None,
            "jobs_found": int(scan_status.get("jobs_found") or 0),
            "errors": [],
        }

    return {
        "available": True,
        "generated_at": snapshot.summary.generated_at,
        "jobs_found": int(scan_status.get("jobs_found") or 0),
        "top_matches": snapshot.summary.top_matches,
        "potential_top_matches": snapshot.summary.potential_top_matches,
        "review_needed": snapshot.summary.review_needed,
        "new_jobs": snapshot.summary.new_jobs,
        "errors": [
            {
                "company_name": error.company_name,
                "source_type": error.source_type,
                "message": error.message,
            }
            for error in snapshot.collector_errors
        ],
    }


def _build_scan_status_payload(
    database_path: str | Path,
    *,
    scan_runner: ScanTaskRunner | None = None,
) -> dict[str, object]:
    active_scan_run = fetch_active_scan_run(database_path)
    scan_run = active_scan_run or fetch_latest_scan_run(database_path)

    if scan_run is None:
        if scan_runner is not None and scan_runner.is_running:
            return _build_starting_scan_payload()

        if scan_runner is not None and scan_runner.failed:
            return _build_worker_failure_payload()

        return {
            "scan_run_id": None,
            "status": "idle",
            "is_running": False,
            "stage": None,
            "stage_label": "No scan is currently running.",
            "companies_scanned": 0,
            "companies_enabled": 0,
            "progress_percent": 0,
            "progress_determinate": False,
            "jobs_found": 0,
            "collector_errors": 0,
            "has_results": False,
            "failure_summary": None,
        }

    status = str(scan_run["status"])
    stage = str(scan_run["current_stage"] or "")
    companies_scanned = int(scan_run["companies_scanned"] or 0)
    companies_enabled = int(scan_run["companies_enabled"] or 0)

    stage_labels = {
        "configuration": "Loading configuration and candidate profile",
        "history_import": "Preparing application history",
        "collection": "Scanning company job sources",
        "scoring": "Scoring collected jobs",
        "storage": "Saving actionable results",
        "report_generation": "Generating reports",
        "email_delivery": "Sending email report",
        "completed": "Scan completed",
    }
    stage_label = stage_labels.get(
        stage,
        stage.replace("_", " ").strip().title() or "Scan is running",
    )

    progress_determinate = (
        companies_enabled > 0
        and (
            stage
            in {
                "collection",
                "scoring",
                "storage",
                "report_generation",
                "email_delivery",
                "completed",
            }
            or status != "running"
        )
    )
    progress_percent = (
        min(
            100,
            round((companies_scanned / companies_enabled) * 100),
        )
        if progress_determinate
        else 0
    )

    has_results = (
        status in {"completed", "completed_with_warnings"}
        and scan_run["report_status"] == "completed"
    )

    return {
        "scan_run_id": int(scan_run["id"]),
        "status": status,
        "is_running": status == "running",
        "stage": stage or None,
        "stage_label": stage_label,
        "companies_scanned": companies_scanned,
        "companies_enabled": companies_enabled,
        "progress_percent": progress_percent,
        "progress_determinate": progress_determinate,
        "jobs_found": int(scan_run["jobs_found"] or 0),
        "collector_errors": int(scan_run["collector_errors"] or 0),
        "has_results": has_results,
        "failure_summary": scan_run["failure_summary"],
        "trigger_source": scan_run["trigger_source"],
    }


def _build_starting_scan_payload() -> dict[str, object]:
    return {
        "scan_run_id": None,
        "status": "running",
        "is_running": True,
        "stage": "starting",
        "stage_label": "Starting scan",
        "companies_scanned": 0,
        "companies_enabled": 0,
        "progress_percent": 0,
        "progress_determinate": False,
        "jobs_found": 0,
        "collector_errors": 0,
        "has_results": False,
        "failure_summary": None,
    }


def _build_worker_failure_payload() -> dict[str, object]:
    return {
        "scan_run_id": None,
        "status": "failed",
        "is_running": False,
        "stage": None,
        "stage_label": "Scan failed",
        "companies_scanned": 0,
        "companies_enabled": 0,
        "progress_percent": 0,
        "progress_determinate": False,
        "jobs_found": 0,
        "collector_errors": 0,
        "has_results": False,
        "failure_summary": (
            "junior could not complete the scan. Open the Scan page for details."
        ),
    }
