"""Verify role discovery requires evidence, approval, and profile isolation."""

from pathlib import Path

import pytest

from job_radar.config import ConfigError
from job_radar.database import connect_database
from job_radar.profile_models import (
    ManagedProfile,
    ManagedResume,
    OccupationPreference,
    ProfilePreferences,
    get_managed_resume_directory,
)
from job_radar.profile_storage import create_profile
from job_radar.role_discovery_service import (
    approved_role_mappings,
    list_role_suggestions,
    record_role_feedback,
    refresh_role_suggestions,
)


def _profile(profile_id: str, *, code: str = "15-1244.00") -> ManagedProfile:
    return ManagedProfile(
        profile_id=profile_id,
        display_name="Fictional Profile",
        preferences=ProfilePreferences(
            target_roles=("Network and Computer Systems Administrators",),
            occupation_selections=(
                OccupationPreference(
                    value=code,
                    label="Network and Computer Systems Administrators",
                ),
            ),
        ),
        resume=ManagedResume(source_file_name="resume.txt"),
    )


def _write_resume(root: Path, profile: ManagedProfile, text: str) -> None:
    directory = root / get_managed_resume_directory(profile.profile_id)
    directory.mkdir(parents=True)
    (directory / "resume.txt").write_text(text, encoding="utf-8")


def test_catalog_suggestions_require_resume_evidence_and_explicit_feedback(
    tmp_path: Path,
) -> None:
    database = tmp_path / "junior.sqlite3"
    profile = _profile("profile_aaaaaaaa")
    create_profile(database, profile)
    _write_resume(
        tmp_path,
        profile,
        (
            "Configured and maintained computer networks, operating systems, "
            "servers, security, and system performance."
        ),
    )

    suggestions = refresh_role_suggestions(
        database,
        profile_id=profile.profile_id,
        base_directory=tmp_path,
    )

    assert suggestions
    assert all("E-Mail" not in item.suggested_title for item in suggestions)
    assert all(
        "Artificial Intelligence" not in item.suggested_title
        for item in suggestions
    )
    assert all(
        "Application Security" not in item.suggested_title
        for item in suggestions
    )
    assert all("Manager" not in item.suggested_title for item in suggestions)
    assert any("Network" in item.suggested_title for item in suggestions)
    assert all("computer" not in item.evidence for item in suggestions)
    suggestion = suggestions[0]
    assert suggestion.feedback_state == "pending"
    assert suggestion.evidence
    assert "not assuming the titles are synonyms" in suggestion.explanation
    assert approved_role_mappings(
        database, profile_id=profile.profile_id
    ) == ()

    reviewed = record_role_feedback(
        database,
        profile_id=profile.profile_id,
        suggestion_id=suggestion.suggestion_id,
        feedback_state="relevant",
    )
    assert reviewed.feedback_state == "relevant"
    assert approved_role_mappings(
        database, profile_id=profile.profile_id
    ) == (suggestion.suggested_title,)


def test_different_discipline_feedback_survives_refresh(tmp_path: Path) -> None:
    database = tmp_path / "junior.sqlite3"
    profile = _profile("profile_bbbbbbbb")
    create_profile(database, profile)
    _write_resume(
        tmp_path,
        profile,
        (
            "Configured and maintained computer networks, operating systems, "
            "servers, security, and system performance."
        ),
    )
    suggestion = refresh_role_suggestions(
        database,
        profile_id=profile.profile_id,
        base_directory=tmp_path,
    )[0]
    record_role_feedback(
        database,
        profile_id=profile.profile_id,
        suggestion_id=suggestion.suggestion_id,
        feedback_state="different_discipline",
    )

    refreshed = refresh_role_suggestions(
        database,
        profile_id=profile.profile_id,
        base_directory=tmp_path,
    )
    stored = next(
        item for item in refreshed if item.suggestion_id == suggestion.suggestion_id
    )
    assert stored.feedback_state == "different_discipline"


def test_suggestions_and_feedback_are_profile_owned(tmp_path: Path) -> None:
    database = tmp_path / "junior.sqlite3"
    first = _profile("profile_cccccccc")
    second = _profile("profile_dddddddd")
    create_profile(database, first)
    create_profile(database, second)
    _write_resume(
        tmp_path,
        first,
        (
            "Configured and maintained computer networks, operating systems, "
            "servers, security, and system performance."
        ),
    )
    _write_resume(
        tmp_path,
        second,
        "Prepared bread, pastries, dough, ovens, and commercial baked goods.",
    )

    suggestions = refresh_role_suggestions(
        database,
        profile_id=first.profile_id,
        base_directory=tmp_path,
    )
    assert suggestions
    assert list_role_suggestions(
        database, profile_id=second.profile_id
    ) == ()
    with pytest.raises(ConfigError, match="no longer available"):
        record_role_feedback(
            database,
            profile_id=second.profile_id,
            suggestion_id=suggestions[0].suggestion_id,
            feedback_state="relevant",
        )


def test_missing_resume_is_explained_without_generating_suggestions(
    tmp_path: Path,
) -> None:
    database = tmp_path / "junior.sqlite3"
    profile = ManagedProfile(
        profile_id="profile_eeeeeeee",
        display_name="No Resume",
    )
    create_profile(database, profile)

    with pytest.raises(ConfigError, match="Upload a résumé"):
        refresh_role_suggestions(
            database,
            profile_id=profile.profile_id,
            base_directory=tmp_path,
        )


def test_company_specific_title_feedback_does_not_leak_to_another_company(
    tmp_path: Path,
) -> None:
    database = tmp_path / "junior.sqlite3"
    profile = _profile("profile_ffffffff")
    create_profile(database, profile)
    with connect_database(database) as connection:
        connection.execute(
            """
            INSERT INTO role_discovery_suggestions (
                profile_id,
                suggested_title,
                normalized_title,
                employer_context,
                context_key,
                source_type,
                explanation,
                evidence_json,
                feedback_state
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                profile.profile_id,
                "Platform Engineer",
                "platform engineer",
                "Example Hardware Company",
                "employer:hardware",
                "observed_posting",
                "The observed responsibilities matched this profile.",
                '["integration", "hardware", "testing", "systems"]',
                "relevant",
            ),
        )

    assert approved_role_mappings(
        database,
        profile_id=profile.profile_id,
        employer_context="hardware",
    ) == ("Platform Engineer",)
    assert approved_role_mappings(
        database,
        profile_id=profile.profile_id,
        employer_context="unrelated",
    ) == ()


def test_observed_posting_keeps_company_context(tmp_path: Path) -> None:
    database = tmp_path / "junior.sqlite3"
    profile = _profile("profile_gggggggg")
    create_profile(database, profile)
    _write_resume(
        tmp_path,
        profile,
        (
            "Configured computer networks, operating systems, servers, security, "
            "performance testing, hardware integration, and system validation."
        ),
    )
    with connect_database(database) as connection:
        connection.execute(
            """
            INSERT INTO companies (company_key, name, source_type)
            VALUES ('example_hardware', 'Example Hardware', 'greenhouse')
            """
        )
        run_id = connection.execute(
            """
            INSERT INTO scan_runs (profile_id, status)
            VALUES (?, 'completed')
            """,
            (profile.profile_id,),
        ).lastrowid
        posting_id = connection.execute(
            """
            INSERT INTO job_postings (
                company_key,
                source_type,
                source_url,
                title,
                description,
                canonical_key,
                content_hash
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "example_hardware",
                "greenhouse",
                "https://example.invalid/jobs/validation",
                "Platform Validation Engineer",
                (
                    "Own system validation, hardware integration, performance "
                    "testing, server systems, and network interoperability."
                ),
                "example-validation",
                "hash-example-validation",
            ),
        ).lastrowid
        connection.execute(
            """
            INSERT INTO job_seen_events (
                job_posting_id, scan_run_id, event_type
            )
            VALUES (?, ?, 'new')
            """,
            (posting_id, run_id),
        )

    suggestions = refresh_role_suggestions(
        database,
        profile_id=profile.profile_id,
        base_directory=tmp_path,
    )
    observed = next(
        item
        for item in suggestions
        if item.suggested_title == "Platform Validation Engineer"
    )
    assert observed.source_type == "observed_posting"
    assert observed.employer_context == "Example Hardware"
    assert "company context" in observed.explanation
