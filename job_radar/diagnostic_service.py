"""Build safe, plain-language health information without exposing raw failures."""

from dataclasses import dataclass
from pathlib import Path

import requests

from job_radar.collectors.greenhouse import CollectorError
from job_radar.config import load_settings
from job_radar.database import connect_database
from job_radar.email_sender import get_email_readiness
from job_radar.storage import fetch_latest_scan_run, initialize_database


@dataclass(frozen=True)
class DiagnosticOutcome:
    category: str
    category_label: str
    message: str
    next_step: str
    failure_stage: str | None = None
    failure_stage_label: str = "Job collection (stage not recorded)"


@dataclass(frozen=True)
class HealthCard:
    title: str
    state: str
    tone: str
    category: str
    summary: str
    next_step: str
    endpoint: str | None = None
    action_label: str = "View details"


@dataclass(frozen=True)
class DiagnosticsView:
    cards: tuple[HealthCard, ...]


def classify_collector_failure(error: CollectorError) -> DiagnosticOutcome:
    """Classify a collector failure by safe exception type, never its text."""
    failure_stage = _safe_failure_stage(error)
    cause: BaseException | None = error
    while cause is not None:
        if isinstance(cause, (requests.Timeout, requests.ConnectionError)):
            return _outcome(
                "network",
                "Junior could not reach this company job source.",
                "Check the network connection and try the source again.",
                failure_stage=failure_stage,
            )
        if isinstance(cause, requests.HTTPError):
            status_code = (
                cause.response.status_code if cause.response is not None else None
            )
            if status_code in {401, 403}:
                return _outcome(
                    "collector",
                    "The company job source denied Junior's public request.",
                    "The recruiting platform may be blocking automated access. "
                    "Test the source again later or review its collector setup.",
                    failure_stage=failure_stage,
                )
            if status_code == 404:
                return _outcome(
                    "collector",
                    "The configured company job-source address was not found.",
                    "Review the public careers address and collector setup.",
                    failure_stage=failure_stage,
                )
            if status_code == 429:
                message = _rate_limit_message(failure_stage)
                return _outcome(
                    "network",
                    message,
                    "Wait before testing or scanning this source again.",
                    failure_stage=failure_stage,
                )
            if status_code is not None and status_code >= 500:
                return _outcome(
                    "network",
                    "The company recruiting service reported a temporary problem.",
                    "Try the source again later.",
                    failure_stage=failure_stage,
                )
            return _outcome(
                "collector",
                "The company job source rejected or could not complete the request.",
                "Verify the public source address and try again later.",
                failure_stage=failure_stage,
            )
        cause = cause.__cause__
    return _outcome(
        "collector",
        "Junior reached this company source but could not read its job list.",
        "Review the company's source type and settings, then try again.",
        failure_stage=failure_stage,
    )


def classify_scan_failure(stage: str) -> DiagnosticOutcome:
    """Classify a failed scan from its owned stage, not private exception text."""
    if stage in {"configuration", "history_import"}:
        return _outcome(
            "configuration",
            "Junior could not load valid scan settings or profile information.",
            "Review Settings and the active profile, then run the scan again.",
        )
    if stage == "collection":
        return _outcome(
            "collector",
            "Junior could not complete company-source collection.",
            "Review Company source health, then run the scan again.",
        )
    if stage == "email_delivery":
        return _outcome(
            "email",
            "The report was created, but Junior could not complete email delivery.",
            "Review Email Setup, use Test Connection, then try again.",
        )
    return _outcome(
        "application",
        "Junior encountered an unexpected application problem during the scan.",
        "Try the scan again. If it continues, open About for support guidance.",
    )


def build_diagnostics_view(
    database_path: str | Path,
    settings_path: str | Path,
) -> DiagnosticsView:
    """Summarize current health from already-sanitized local state."""
    settings = load_settings(settings_path)
    db_path = initialize_database(database_path)
    return DiagnosticsView(
        cards=(
            HealthCard(
                title="Application configuration",
                state="Ready",
                tone="success",
                category="Configuration",
                summary="Junior loaded the current settings successfully.",
                next_step="No action is needed.",
            ),
            _scan_health_card(db_path),
            _source_health_card(db_path),
            _email_health_card(settings.email),
        )
    )


def _scan_health_card(database_path: Path) -> HealthCard:
    row = fetch_latest_scan_run(database_path)
    if row is None:
        return HealthCard(
            title="Latest scan",
            state="Not run yet",
            tone="neutral",
            category="Scan",
            summary="Junior has no completed or failed scan to review.",
            next_step="Run a scan when the profile and company sources are ready.",
            endpoint="settings_scan_diagnostics",
            action_label="Review latest scan",
        )

    status = str(row["status"])
    if status == "failed":
        category = _latest_scan_error_category(database_path, int(row["id"]))
        return HealthCard(
            title="Latest scan",
            state="Needs attention",
            tone="error",
            category=_category_label(category),
            summary=(
                str(row["failure_summary"])
                if row["failure_summary"]
                else "Junior could not complete the latest scan."
            ),
            next_step=_next_step_for_category(category),
            endpoint="settings_scan_diagnostics",
            action_label="Review latest scan",
        )
    if status == "completed_with_warnings":
        categories = _scan_error_categories(database_path, int(row["id"]))
        category = "network" if "network" in categories else "collector"
        return HealthCard(
            title="Latest scan",
            state="Completed with source warnings",
            tone="warning",
            category=_category_label(category),
            summary=(
                f"The scan completed, but {int(row['collector_errors'] or 0)} "
                "company source warning(s) need review."
            ),
            next_step="Open scan details to review the affected companies.",
            endpoint="settings_scan_diagnostics",
            action_label="Review latest scan warnings",
        )

    email_status = str(row["email_status"] or "not_requested")
    if email_status == "failed":
        return HealthCard(
            title="Latest scan",
            state="Report ready; email failed",
            tone="warning",
            category="Email",
            summary="The latest report completed, but email was not delivered.",
            next_step="Review Email Setup and use Test Connection.",
            endpoint="settings_scan_diagnostics",
            action_label="Review latest scan",
        )
    return HealthCard(
        title="Latest scan",
        state="Healthy",
        tone="success",
        category="Scan",
        summary="The latest scan completed successfully.",
        next_step="No action is needed.",
        endpoint="settings_scan_diagnostics",
        action_label="Review latest scan",
    )


def _source_health_card(database_path: Path) -> HealthCard:
    with connect_database(database_path) as connection:
        row = connection.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN enabled = 1 THEN 1 ELSE 0 END) AS enabled,
                SUM(CASE WHEN last_connection_state = 'success' THEN 1 ELSE 0 END)
                    AS healthy,
                SUM(CASE WHEN last_connection_state = 'error' THEN 1 ELSE 0 END)
                    AS failing,
                SUM(CASE WHEN last_connection_state = 'not_tested' THEN 1 ELSE 0 END)
                    AS untested
            FROM employer_sources
            """
        ).fetchone()
        categories = {
            str(item[0])
            for item in connection.execute(
                """
                SELECT DISTINCT last_connection_category
                FROM employer_sources
                WHERE last_connection_state = 'error'
                AND last_connection_category IS NOT NULL
                """
            ).fetchall()
        }

    total = int(row[0] or 0)
    enabled = int(row[1] or 0)
    healthy = int(row[2] or 0)
    failing = int(row[3] or 0)
    untested = int(row[4] or 0)
    if total == 0:
        return HealthCard(
            title="Company sources",
            state="Not configured",
            tone="neutral",
            category="Configuration",
            summary="No company sources are configured yet.",
            next_step="Add companies before running a targeted scan.",
            endpoint="companies",
            action_label="Open Companies",
        )
    if failing:
        category = "network" if "network" in categories else "collector"
        return HealthCard(
            title="Company sources",
            state="Needs attention",
            tone="error",
            category=_category_label(category),
            summary=(
                f"{failing} of {total} company source(s) have a failed "
                "connection test."
            ),
            next_step="Open source health and review the affected companies.",
            endpoint="companies",
            action_label="Open Companies",
        )
    tone = "success" if healthy else "warning"
    state = "Healthy" if healthy and not untested else "Testing incomplete"
    return HealthCard(
        title="Company sources",
        state=state,
        tone=tone,
        category="Collector",
        summary=(
            f"{enabled} source(s) are enabled, {healthy} tested successfully, "
            f"and {untested} have not been tested."
        ),
        next_step=(
            "No action is needed."
            if tone == "success"
            else "Test enabled company sources before relying on scheduled scans."
        ),
        endpoint="companies",
        action_label="Open Companies",
    )


def _email_health_card(email_settings) -> HealthCard:
    readiness = get_email_readiness(email_settings)
    if not email_settings.enabled:
        return HealthCard(
            title="Email delivery",
            state="Not configured",
            tone="neutral",
            category="Email",
            summary="Email delivery is turned off.",
            next_step="No action is needed unless reports should be emailed.",
        )
    return HealthCard(
        title="Email delivery",
        state="Ready" if readiness.ready else "Needs attention",
        tone="success" if readiness.ready else "warning",
        category="Email",
        summary=readiness.message,
        next_step=(
            "No action is needed."
            if readiness.ready
            else "Open Email Setup, verify the credential, and use Test Connection."
        ),
    )


def _latest_scan_error_category(database_path: Path, scan_run_id: int) -> str:
    categories = _scan_error_categories(database_path, scan_run_id)
    for category in ("configuration", "network", "collector", "email", "application"):
        if category in categories:
            return category
    return "application"


def _scan_error_categories(
    database_path: Path,
    scan_run_id: int,
) -> set[str]:
    with connect_database(database_path) as connection:
        rows = connection.execute(
            "SELECT error_type FROM scan_errors WHERE scan_run_id = ?",
            (scan_run_id,),
        ).fetchall()
    return {
        str(row[0]).removesuffix("_failure").split("_", maxsplit=1)[0]
        for row in rows
    }


def _outcome(
    category: str,
    message: str,
    next_step: str,
    *,
    failure_stage: str | None = None,
) -> DiagnosticOutcome:
    return DiagnosticOutcome(
        category=category,
        category_label=_category_label(category),
        message=message,
        next_step=next_step,
        failure_stage=failure_stage,
        failure_stage_label=_failure_stage_label(failure_stage),
    )


def _safe_failure_stage(error: CollectorError) -> str | None:
    stage = getattr(error, "failure_stage", None)
    if stage in {
        "initial_search_request",
        "initial_search_response",
        "results_pagination_request",
        "results_pagination_response",
    }:
        return stage
    return None


def _failure_stage_label(stage: str | None) -> str:
    return {
        "initial_search_request": "Initial job-search request",
        "initial_search_response": "Initial search response",
        "results_pagination_request": "Later results-page request",
        "results_pagination_response": "Later results-page response",
    }.get(stage, "Job collection (stage not recorded)")


def _rate_limit_message(stage: str | None) -> str:
    if stage == "initial_search_request":
        return (
            "Junior reached the recruiting service, but the initial job-search "
            "request was rate-limited (HTTP 429) before a usable results page "
            "was received."
        )
    if stage == "results_pagination_request":
        return (
            "Junior received an earlier job-results page, but a later page "
            "request was rate-limited (HTTP 429) before collection finished."
        )
    return "The company job source temporarily limited Junior's requests (HTTP 429)."


def _category_label(category: str) -> str:
    return {
        "configuration": "Configuration",
        "collector": "Collector",
        "network": "Network",
        "email": "Email",
        "application": "Application",
    }.get(category, "Application")


def _next_step_for_category(category: str) -> str:
    return {
        "configuration": "Review Settings and the active profile, then try again.",
        "collector": "Review Company source health, then try again.",
        "network": "Check the network connection and retry the affected sources.",
        "email": "Review Email Setup and use Test Connection.",
        "application": "Try again. If it continues, open About for support guidance.",
    }.get(category, "Open About for support guidance.")
