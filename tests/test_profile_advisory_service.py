from job_radar.profile_advisory_service import build_profile_advisories
from job_radar.profile_models import ManagedProfile, ProfilePreferences


def test_detailed_consistent_profile_has_no_conflict_warning() -> None:
    profile = ManagedProfile(
        profile_id="profile_detailed1",
        display_name="Detailed",
        preferences=ProfilePreferences(
            target_roles=("Site Reliability Engineer",),
            seniority_levels=("Senior",),
            exclusions=("Sales",),
        ),
    )
    assert build_profile_advisories(profile) == ()


def test_simplified_profile_is_valid_and_unrestricted() -> None:
    profile = ManagedProfile(profile_id="profile_sparse01", display_name="Sparse")
    assert build_profile_advisories(profile) == ()


def test_conflicting_target_and_level_are_explained() -> None:
    profile = ManagedProfile(
        profile_id="profile_warning1",
        display_name="Warning",
        preferences=ProfilePreferences(
            target_roles=("Director of Professional Services",),
            seniority_levels=("Senior",),
            exclusions=("Director of Professional Services",),
        ),
    )
    codes = {item.code for item in build_profile_advisories(profile)}
    assert codes == {"target_role_excluded", "leadership_level_conflict"}
