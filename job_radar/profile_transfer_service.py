"""Export and import profile configuration without moving résumé or activity data."""

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import secrets

from job_radar.config import ConfigError
from job_radar.employer_storage import (
    list_employer_sources,
    list_profile_employer_assignments,
)
from job_radar.profile_management import MAX_MANAGED_PROFILES
from job_radar.profile_models import (
    FIT_SIGNAL_CATEGORIES,
    PROFILE_SCHEMA_VERSION,
    FitSignal,
    LocationPreference,
    ManagedProfile,
    OccupationPreference,
    ProfilePreferences,
)
from job_radar.profile_storage import (
    create_imported_profile,
    list_profiles,
)


TRANSFER_FORMAT = "junior-profile-configuration"
TRANSFER_SCHEMA_VERSION = 1
MAX_TRANSFER_BYTES = 1_000_000
MAX_LIST_ITEMS = 500
MAX_TEXT_LENGTH = 2_000


@dataclass(frozen=True)
class ProfileImportResult:
    """Describe the inactive profile created from a validated transfer file."""

    profile: ManagedProfile
    imported_company_count: int
    unavailable_companies: tuple[str, ...]


def export_profile(
    database_path: str | Path,
    profile_id: str,
) -> tuple[str, bytes]:
    """Serialize only portable configuration owned by a selected profile."""

    from job_radar.profile_storage import get_profile

    profile = get_profile(database_path, profile_id)
    if profile is None:
        raise ConfigError("Choose an available saved profile to export.")

    employer_names = {
        employer.employer_id: employer.name
        for employer in list_employer_sources(database_path)
    }
    assignments = list_profile_employer_assignments(
        database_path,
        profile.profile_id,
    )
    payload = {
        "format": TRANSFER_FORMAT,
        "transfer_schema_version": TRANSFER_SCHEMA_VERSION,
        "profile_schema_version": PROFILE_SCHEMA_VERSION,
        "profile": {
            "display_name": profile.display_name,
            "preferences": _preferences_payload(profile.preferences),
            "fit_signals": [
                {
                    "term": signal.term,
                    "category": signal.category,
                    "user_overridden": signal.user_overridden,
                }
                for signal in profile.fit_signals
            ],
            "scoring_config": _scoring_config(profile.scoring_config),
            "report_settings": _report_settings(profile.report_settings),
            "companies": [
                {
                    "employer_id": assignment.employer_id,
                    "name": employer_names.get(
                        assignment.employer_id,
                        assignment.employer_id,
                    ),
                    "scanning": assignment.enabled,
                }
                for assignment in assignments
            ],
        },
        "excluded": [
            "resume files and resume text",
            "applications and application history",
            "saved, passed, and reviewed jobs",
            "scan results, reports, logs, and notes",
            "credentials, local paths, and internal profile identity",
        ],
    }
    content = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
    filename = "junior-profile-configuration.json"
    return filename, content


def import_profile(
    database_path: str | Path,
    content: bytes,
) -> ProfileImportResult:
    """Create a new inactive profile from a bounded, validated transfer file."""

    if not content:
        raise ConfigError("The selected profile file is empty.")
    if len(content) > MAX_TRANSFER_BYTES:
        raise ConfigError("The profile file is larger than Junior supports.")
    try:
        payload = json.loads(content.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ConfigError("The selected file is not a valid Junior profile file.") from error

    root = _mapping(payload, "profile file")
    _exact_keys(
        root,
        {
            "format",
            "transfer_schema_version",
            "profile_schema_version",
            "profile",
            "excluded",
        },
        "profile file",
    )
    if root["format"] != TRANSFER_FORMAT:
        raise ConfigError("The selected file is not a Junior profile configuration.")
    if root["transfer_schema_version"] != TRANSFER_SCHEMA_VERSION:
        raise ConfigError("This profile file uses an unsupported transfer version.")
    if root["profile_schema_version"] != PROFILE_SCHEMA_VERSION:
        raise ConfigError("This profile file uses an unsupported profile version.")

    existing = list_profiles(database_path, include_archived=True)
    if len(existing) >= MAX_MANAGED_PROFILES:
        raise ConfigError(
            f"Junior supports up to {MAX_MANAGED_PROFILES} profiles. "
            "Delete a profile before importing another one."
        )

    data = _mapping(root["profile"], "profile")
    _exact_keys(
        data,
        {
            "display_name",
            "preferences",
            "fit_signals",
            "scoring_config",
            "report_settings",
            "companies",
        },
        "profile",
    )
    display_name = _unique_display_name(
        _text(data["display_name"], "profile name"),
        {profile.display_name.casefold() for profile in existing},
    )
    preferences = _preferences_from_payload(data["preferences"])
    fit_signals = _fit_signals(data["fit_signals"])
    scoring_config = _scoring_config(data["scoring_config"])
    report_settings = _report_settings(data["report_settings"])

    available = {
        employer.employer_id: employer
        for employer in list_employer_sources(database_path)
    }
    company_states: dict[str, bool] = {}
    unavailable: list[str] = []
    for item in _list(data["companies"], "companies"):
        company = _mapping(item, "company")
        _exact_keys(company, {"employer_id", "name", "scanning"}, "company")
        employer_id = _text(company["employer_id"], "company ID")
        name = _text(company["name"], "company name")
        scanning = _boolean(company["scanning"], "company scanning state")
        if employer_id in available:
            company_states[employer_id] = scanning
        else:
            unavailable.append(name)

    profile = ManagedProfile(
        profile_id=f"profile_{secrets.token_hex(8)}",
        display_name=display_name,
        preferences=preferences,
        resume=None,
        company_ids=tuple(sorted(company_states)),
        scoring_config=scoring_config,
        fit_signals=fit_signals,
        report_settings=report_settings,
        archived=False,
    )
    create_imported_profile(
        database_path,
        profile,
        company_enabled=company_states,
    )
    return ProfileImportResult(
        profile=profile,
        imported_company_count=len(company_states),
        unavailable_companies=tuple(sorted(set(unavailable), key=str.casefold)),
    )


def _preferences_payload(preferences: ProfilePreferences) -> dict[str, object]:
    result = asdict(preferences)
    result["occupation_selections"] = [
        asdict(item) for item in preferences.occupation_selections
    ]
    result["location_selections"] = [
        asdict(item) for item in preferences.location_selections
    ]
    return result


def _preferences_from_payload(value: object) -> ProfilePreferences:
    data = _mapping(value, "preferences")
    expected = set(ProfilePreferences.__dataclass_fields__)
    _exact_keys(data, expected, "preferences")
    list_fields = {
        "target_roles",
        "seniority_levels",
        "core_strengths",
        "credible_adjacent",
        "learning_or_gap",
        "exclusions",
        "preferred_locations",
        "work_arrangements",
        "employment_types",
    }
    values: dict[str, object] = {
        field: _string_tuple(data[field], field.replace("_", " "))
        for field in list_fields
    }
    values.update(
        {
            "schedule_preference": _optional_text(data["schedule_preference"], "schedule preference"),
            "compensation_floor_usd": _optional_integer(data["compensation_floor_usd"], "minimum compensation"),
            "compensation_target_usd": _optional_integer(data["compensation_target_usd"], "target compensation"),
            "travel_tolerance": _optional_text(data["travel_tolerance"], "travel tolerance"),
            "on_call_preference": _text(data["on_call_preference"], "on-call preference"),
            "clearance_preference": _text(data["clearance_preference"], "clearance preference"),
            "include_strong_location_outliers": _boolean(data["include_strong_location_outliers"], "outside-area setting"),
            "occupation_selections": tuple(
                OccupationPreference(**_typed_record(item, {"value", "label"}, "occupation"))
                for item in _list(data["occupation_selections"], "occupations")
            ),
            "location_selections": tuple(
                LocationPreference(**_typed_record(item, {"value", "label", "radius_miles", "latitude", "longitude"}, "location"))
                for item in _list(data["location_selections"], "locations")
            ),
        }
    )
    try:
        return ProfilePreferences(**values)
    except (TypeError, ValueError) as error:
        raise ConfigError(f"The imported profile preferences are invalid: {error}") from error


def _fit_signals(value: object) -> tuple[FitSignal, ...]:
    signals: list[FitSignal] = []
    for item in _list(value, "fit signals"):
        data = _mapping(item, "fit signal")
        _exact_keys(data, {"term", "category", "user_overridden"}, "fit signal")
        category = _text(data["category"], "fit category")
        if category not in FIT_SIGNAL_CATEGORIES:
            raise ConfigError("The profile file contains an unsupported fit category.")
        signals.append(
            FitSignal(
                term=_text(data["term"], "fit term"),
                category=category,
                explanation="Imported profile preference",
                evidence_source="profile_import",
                user_overridden=_boolean(data["user_overridden"], "fit override"),
            )
        )
    return tuple(signals)


def _scoring_config(value: object) -> dict[str, object] | None:
    if value is None:
        return None
    data = _mapping(value, "scoring settings")
    _exact_keys(
        data,
        {
            "positive_keywords",
            "negative_keywords",
            "location_preferences",
            "top_matches",
            "review_needed",
        },
        "scoring settings",
    )
    positive = _score_mapping(data["positive_keywords"], "positive keywords")
    negative = _score_mapping(data["negative_keywords"], "negative keywords")
    locations = _mapping(data["location_preferences"], "location scoring")
    _exact_keys(locations, {"allowed", "conditional", "skipped"}, "location scoring")
    top = _mapping(data["top_matches"], "Top Match settings")
    # Older managed profiles legitimately omit review_signals because the
    # scoring loader has always treated it as an optional empty list. Preserve
    # that compatibility during export while still rejecting unknown fields.
    _required_and_optional_keys(
        top,
        {"min_score", "excluded_title_keywords", "strong_signals"},
        {"review_signals"},
        "Top Match settings",
    )
    review = _mapping(data["review_needed"], "Needs Review settings")
    _exact_keys(
        review,
        {"min_score", "excluded_location_statuses", "strong_signals"},
        "Needs Review settings",
    )
    return {
        "positive_keywords": positive,
        "negative_keywords": negative,
        "location_preferences": {
            key: _score_mapping(locations[key], f"{key} location scoring")
            for key in ("allowed", "conditional", "skipped")
        },
        "top_matches": {
            "min_score": _integer(top["min_score"], "Top Match threshold"),
            "excluded_title_keywords": list(_string_tuple(top["excluded_title_keywords"], "excluded titles")),
            "strong_signals": list(_string_tuple(top["strong_signals"], "Top Match signals")),
            "review_signals": list(
                _string_tuple(top.get("review_signals", []), "review signals")
            ),
        },
        "review_needed": {
            "min_score": _integer(review["min_score"], "Needs Review threshold"),
            "excluded_location_statuses": list(_string_tuple(review["excluded_location_statuses"], "excluded location statuses")),
            "strong_signals": list(_string_tuple(review["strong_signals"], "Needs Review signals")),
        },
    }


def _score_mapping(value: object, label: str) -> dict[str, int]:
    data = _mapping(value, label)
    if len(data) > MAX_LIST_ITEMS:
        raise ConfigError(f"The imported {label} contains too many entries.")
    return {
        _text(key, label): _integer(points, label)
        for key, points in data.items()
    }


def _report_settings(value: object) -> dict[str, object]:
    data = _mapping(value, "report settings")
    if not set(data).issubset({"retention"}):
        raise ConfigError("The imported report settings contain unsupported fields.")
    return {
        key: _text(item, "report retention")
        for key, item in data.items()
    }


def _unique_display_name(name: str, existing: set[str]) -> str:
    if name.casefold() not in existing:
        return name
    base = f"{name} (Imported)"
    candidate = base
    number = 2
    while candidate.casefold() in existing:
        candidate = f"{base} {number}"
        number += 1
    return candidate


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ConfigError(f"The imported {label} must be a data object.")
    return value


def _list(value: object, label: str) -> list[object]:
    if not isinstance(value, list) or len(value) > MAX_LIST_ITEMS:
        raise ConfigError(f"The imported {label} list is invalid or too large.")
    return value


def _string_tuple(value: object, label: str) -> tuple[str, ...]:
    return tuple(_text(item, label) for item in _list(value, label))


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_TEXT_LENGTH:
        raise ConfigError(f"The imported {label} is invalid.")
    return value.strip()


def _optional_text(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _text(value, label)


def _optional_integer(value: object, label: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ConfigError(f"The imported {label} is invalid.")
    return value


def _integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ConfigError(f"The imported {label} is invalid.")
    return value


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigError(f"The imported {label} is invalid.")
    return value


def _exact_keys(data: dict[str, object], expected: set[str], label: str) -> None:
    if set(data) != expected:
        raise ConfigError(f"The imported {label} has missing or unsupported fields.")


def _required_and_optional_keys(
    data: dict[str, object],
    required: set[str],
    optional: set[str],
    label: str,
) -> None:
    keys = set(data)
    if not required.issubset(keys) or not keys.issubset(required | optional):
        raise ConfigError(f"The imported {label} has missing or unsupported fields.")


def _typed_record(value: object, keys: set[str], label: str) -> dict[str, object]:
    data = _mapping(value, label)
    _exact_keys(data, keys, label)
    return data
