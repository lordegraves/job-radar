"""Verify recommendation administration is guarded, bounded, and audited."""

from pathlib import Path

import pytest

from job_radar.company_recommendation_models import NOT_RELEVANT
from job_radar.company_recommendation_service import (
    build_company_recommendations_for_profile,
)
from job_radar.company_recommendation_storage import set_feedback
from job_radar.employer_models import EmployerSource
from job_radar.employer_storage import upsert_employer_source
from job_radar.profile_models import ManagedProfile, ProfilePreferences
from job_radar.profile_storage import create_profile
from job_radar.recommendation_admin_service import (
    RecommendationAdminError,
    list_recommendation_audit,
    load_recommendation_diagnostic,
    rebuild_recommendations,
    reset_recommendation_feedback,
    update_recommendation_metadata,
)
from job_radar.web_app import create_app


def _profile(profile_id: str, role: str) -> ManagedProfile:
    return ManagedProfile(
        profile_id=profile_id,
        display_name="Test User",
        preferences=ProfilePreferences(target_roles=(role,)),
    )


def _employer(employer_id: str) -> EmployerSource:
    return EmployerSource(
        employer_id=employer_id,
        name="Example Foods",
        source_type="html",
        enabled=True,
        source_config={
            "source_url": "https://example.invalid/jobs",
        },
    )


def _build_app(tmp_path: Path):
    settings_path = tmp_path / "config" / "settings.yaml"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(
        (
            f"database_path: {tmp_path / 'data' / 'junior.sqlite3'}\n"
            f"reports_path: {tmp_path / 'reports'}\n"
            f"logs_path: {tmp_path / 'logs'}\n"
        ),
        encoding="utf-8",
    )
    return create_app(settings_path=settings_path, base_directory=tmp_path)


def test_metadata_changes_future_recommendations_and_global_exclusion(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    profile = _profile("profile_aaaaaaaa", "cake decorator")
    employer = _employer("example_foods")
    create_profile(database_path, profile)
    upsert_employer_source(database_path, employer)

    assert build_company_recommendations_for_profile(
        database_path, profile.profile_id
    ) == ()

    metadata = update_recommendation_metadata(
        database_path,
        employer.employer_id,
        aliases="Example Bakery",
        industries="Food service",
        occupation_families="Cake decorator\nBaker",
        employer_type="Private company",
        geographic_presence="Colorado",
        remote_hiring_metadata="Not applicable",
        eligibility="eligible",
    )
    results = build_company_recommendations_for_profile(
        database_path, profile.profile_id
    )

    assert metadata.aliases == ("Example Bakery",)
    assert [item.employer_id for item in results] == [employer.employer_id]

    update_recommendation_metadata(
        database_path,
        employer.employer_id,
        aliases="Example Bakery",
        industries="Food service",
        occupation_families="Cake decorator\nBaker",
        employer_type="Private company",
        geographic_presence="Colorado",
        remote_hiring_metadata="Not applicable",
        eligibility="excluded",
    )
    assert build_company_recommendations_for_profile(
        database_path, profile.profile_id
    ) == ()


def test_feedback_reset_is_profile_owned_guarded_and_audited(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    first = _profile("profile_aaaaaaaa", "cook")
    second = _profile("profile_bbbbbbbb", "cook")
    employer = _employer("example_foods")
    create_profile(database_path, first)
    create_profile(database_path, second)
    upsert_employer_source(database_path, employer)
    update_recommendation_metadata(
        database_path,
        employer.employer_id,
        aliases="",
        industries="Food",
        occupation_families="Cook",
        employer_type="",
        geographic_presence="",
        remote_hiring_metadata="",
        eligibility="eligible",
    )
    for profile in (first, second):
        build_company_recommendations_for_profile(
            database_path, profile.profile_id
        )
        set_feedback(
            database_path,
            profile_id=profile.profile_id,
            employer_id=employer.employer_id,
            state=NOT_RELEVANT,
        )

    with pytest.raises(RecommendationAdminError, match="RESET"):
        reset_recommendation_feedback(
            database_path,
            first.profile_id,
            employer.employer_id,
            confirmation="reset",
        )
    reset_recommendation_feedback(
        database_path,
        first.profile_id,
        employer.employer_id,
        confirmation="RESET",
    )

    first_diagnostic = load_recommendation_diagnostic(
        database_path, first.profile_id, employer.employer_id
    )
    second_diagnostic = load_recommendation_diagnostic(
        database_path, second.profile_id, employer.employer_id
    )
    assert first_diagnostic.feedback_state == "NEW"
    assert second_diagnostic.feedback_state == NOT_RELEVANT
    assert list_recommendation_audit(
        database_path, employer.employer_id
    )[0]["operation"] == "reset_feedback"


def test_rebuild_scope_requires_confirmation_and_stays_bounded(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    first = _profile("profile_aaaaaaaa", "cook")
    second = _profile("profile_bbbbbbbb", "baker")
    employer = _employer("example_foods")
    create_profile(database_path, first)
    create_profile(database_path, second)
    upsert_employer_source(database_path, employer)
    update_recommendation_metadata(
        database_path,
        employer.employer_id,
        aliases="",
        industries="Food",
        occupation_families="Cook\nBaker",
        employer_type="",
        geographic_presence="",
        remote_hiring_metadata="",
        eligibility="eligible",
    )

    assert rebuild_recommendations(
        database_path,
        profile_id=first.profile_id,
    ) == 1
    assert load_recommendation_diagnostic(
        database_path, first.profile_id, employer.employer_id
    ).score is not None
    assert load_recommendation_diagnostic(
        database_path, second.profile_id, employer.employer_id
    ).score is None

    with pytest.raises(RecommendationAdminError, match="REBUILD ALL"):
        rebuild_recommendations(database_path)
    assert rebuild_recommendations(
        database_path,
        all_profiles_confirmation="REBUILD ALL",
    ) == 2


def test_recommendation_admin_route_requires_unlock_and_renders(
    tmp_path: Path,
) -> None:
    app = _build_app(tmp_path)
    database_path = tmp_path / "data" / "junior.sqlite3"
    create_profile(
        database_path,
        _profile("profile_aaaaaaaa", "cook"),
    )
    upsert_employer_source(database_path, _employer("example_foods"))
    client = app.test_client()

    assert client.get("/administration/recommendations").status_code == 302
    client.post("/administration/unlock", data={"confirmation": "ADMIN"})
    response = client.get("/administration/recommendations")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Recommendation Administration" in html
    assert "Example Foods" in html
    assert 'name="_csrf_token"' in html
