"""Serve manual scan controls and progress updates for the web interface."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request

from job_radar.runtime_paths import (
    DEFAULT_EMAIL_PREVIEW_PATH,
    DEFAULT_REPORT_PATH,
    RuntimePaths,
)
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
        settings_path = str(runtime_paths.settings_path)
        company_config_path = str(runtime_paths.company_config_path)
        scoring_config_path = str(runtime_paths.scoring_config_path)
        report_path = str(runtime_paths.resolve(DEFAULT_REPORT_PATH))
        email_preview_path = str(
            runtime_paths.resolve(DEFAULT_EMAIL_PREVIEW_PATH)
        )
        scan_command = (
            "python -m job_radar scan "
            f"--config {company_config_path} "
            f"--settings {settings_path} "
            f"--report {report_path} "
            f"--email-preview {email_preview_path}"
        )

        scan_status = _build_scan_status_payload(
            runtime_paths.database_path
        )

        return render_template(
            "scan.html",
            scan_command=scan_command,
            scan_config_path=company_config_path,
            scan_settings_path=settings_path,
            scan_scoring_path=scoring_config_path,
            scan_report_path=report_path,
            scan_email_preview_path=email_preview_path,
            scan_result=request.args.get("scan_result"),
            scan_error=request.args.get("scan_error", "").strip(),
            scan_status=scan_status,
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
        )

        if not started:
            return jsonify({"status": "busy"}), 409

        return jsonify({"status": "starting"}), 202


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
