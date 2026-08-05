"""Verify company catalog transfer appends safely without profile changes."""

from pathlib import Path

from job_radar.company_transfer_service import export_company_catalog, import_company_catalog
from job_radar.employer_models import EmployerSource
from job_radar.employer_storage import get_employer_source, list_employer_sources, upsert_employer_source
from job_radar.profile_models import ManagedProfile
from job_radar.profile_storage import create_profile, get_profile


def test_company_import_appends_missing_and_never_overwrites(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite3"
    destination = tmp_path / "destination.sqlite3"
    upsert_employer_source(
        source,
        EmployerSource(
            employer_id="existing_company",
            name="Existing Company",
            source_type="greenhouse",
            source_config={"source_slug": "source-version"},
            notes="Private source note",
        ),
    )
    upsert_employer_source(
        source,
        EmployerSource(
            employer_id="new_company",
            name="New Company",
            source_type="html",
            source_config={"source_url": "https://new.invalid/jobs"},
        ),
    )
    original = EmployerSource(
        employer_id="existing_company",
        name="Existing Company",
        source_type="greenhouse",
        source_config={"source_slug": "destination-version"},
    )
    upsert_employer_source(destination, original)
    profile = ManagedProfile(
        profile_id="profile_11111111",
        display_name="Current Profile",
        company_ids=("existing_company",),
    )
    create_profile(destination, profile)

    _, content = export_company_catalog(source)
    result = import_company_catalog(destination, content)

    assert result.added == 1
    assert result.skipped_duplicates == 1
    assert get_employer_source(destination, "existing_company") == original
    assert get_employer_source(destination, "new_company") is not None
    assert get_profile(destination, profile.profile_id).company_ids == (
        "existing_company",
    )
    assert len(list_employer_sources(destination)) == 2
    assert b"Private source note" not in content

