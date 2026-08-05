"""Build a privacy-safe profile configuration report for user-directed support."""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from job_radar import __build__, __version__
from job_radar.company_workspace_service import build_company_workspace
from job_radar.profile_fit import build_initial_fit_signals
from job_radar.profile_models import ManagedProfile
from job_radar.profile_storage import get_active_profile
from job_radar.scoring_preferences import (
    ScoringPreferencesView,
    build_effective_scoring_preferences_view,
)


REPORT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ProfileConfigurationReport:
    """Contain only fields deliberately approved for the support report."""

    generated_at: str
    version: str
    build_label: str
    report_schema_version: int
    profile_schema_version: int
    sections: tuple[tuple[str, tuple[tuple[str, str], ...]], ...]
    companies: tuple[tuple[str, str, str], ...]
    fit_signals: tuple[tuple[str, str], ...]
    scoring: tuple[tuple[str, str], ...]
    excluded_fields: tuple[str, ...]


def build_profile_configuration_report(
    database_path: str | Path,
    scoring_path: str | Path,
    *,
    now: datetime | None = None,
) -> ProfileConfigurationReport | None:
    """Build an inspectable snapshot without serializing the raw profile."""

    profile = get_active_profile(database_path)
    if profile is None:
        return None

    preferences = profile.preferences
    workspace = build_company_workspace(database_path)
    scoring = build_effective_scoring_preferences_view(
        database_path,
        scoring_path,
    )
    generated_at = (now or datetime.now(UTC)).astimezone().strftime(
        "%Y-%m-%d %H:%M:%S %Z"
    )

    return ProfileConfigurationReport(
        generated_at=generated_at,
        version=__version__,
        build_label=__build__,
        report_schema_version=REPORT_SCHEMA_VERSION,
        profile_schema_version=profile.schema_version,
        sections=(
            (
                "Target work",
                (
                    ("Job titles", _list(preferences.target_roles)),
                    ("Job levels", _list(preferences.seniority_levels)),
                    ("Employment types", _list(preferences.employment_types)),
                ),
            ),
            (
                "Workplace and eligibility",
                (
                    ("Workplace arrangements", _list(preferences.work_arrangements)),
                    ("Locations", _locations(profile)),
                    ("Schedule", _value(preferences.schedule_preference)),
                    ("Travel", _value(preferences.travel_tolerance)),
                    ("On-call", preferences.on_call_preference),
                    ("Security clearance", preferences.clearance_preference),
                    (
                        "Exceptional matches outside selected locations",
                        "Enabled"
                        if preferences.include_strong_location_outliers
                        else "Disabled",
                    ),
                ),
            ),
            (
                "Compensation",
                (
                    ("Minimum annual compensation", _money(preferences.compensation_floor_usd)),
                    ("Preferred annual compensation", _money(preferences.compensation_target_usd)),
                ),
            ),
            (
                "Skills and fit preferences",
                (
                    ("Demonstrated strengths", _list(preferences.core_strengths)),
                    ("Related experience", _list(preferences.credible_adjacent)),
                    ("Learning areas or known gaps", _list(preferences.learning_or_gap)),
                    ("Work to exclude", _list(preferences.exclusions)),
                ),
            ),
        ),
        companies=tuple(
            (
                company.name,
                company.source_label,
                "Scanning" if company.scanning else "Paused",
            )
            for company in workspace.companies
        ),
        fit_signals=tuple(
            (signal.term, signal.category.title())
            for signal in build_initial_fit_signals(profile)
        ),
        scoring=_scoring_rows(scoring),
        excluded_fields=(
            "Name, email address, phone number, and street address",
            "Résumé text, résumé file, and work-history details",
            "Applications, saved jobs, passed jobs, and personal review notes",
            "Local file paths, database identifiers, and internal profile identifiers",
            "Passwords, API keys, access tokens, and credential references",
            "Private employer-source URLs and raw diagnostic errors",
        ),
    )


def _list(values: tuple[str, ...]) -> str:
    return ", ".join(values) if values else "None configured"


def _value(value: str | None) -> str:
    return value or "Not configured"


def _money(value: int | None) -> str:
    return f"${value:,}" if value is not None else "Not configured"


def _locations(profile: ManagedProfile) -> str:
    structured = profile.preferences.location_selections
    if structured:
        return "; ".join(
            f"{location.label} ({location.radius_miles}-mile radius)"
            for location in structured
        )
    return _list(profile.preferences.preferred_locations)


def _scoring_rows(view: ScoringPreferencesView) -> tuple[tuple[str, str], ...]:
    if view.load_error:
        return (("Scoring configuration", "Unavailable"),)
    return (
        ("Top Match threshold", _value_number(view.top_match_min_score)),
        ("Needs Review threshold", _value_number(view.review_needed_min_score)),
        ("Positive terms", _weighted(view.positive_keywords)),
        ("Negative terms", _weighted(view.negative_keywords)),
        ("Excluded title terms", _list(view.excluded_title_keywords)),
        ("Top Match evidence", _list(view.top_match_signals)),
        ("Needs Review evidence", _list(view.review_needed_signals)),
    )


def _value_number(value: int | None) -> str:
    return str(value) if value is not None else "Not configured"


def _weighted(values: tuple[object, ...]) -> str:
    return ", ".join(
        f"{item.term} ({item.points:+d})" for item in values
    ) or "None configured"
