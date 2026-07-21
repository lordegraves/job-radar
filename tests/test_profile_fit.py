"""Verify conservative initialization of the job-fit preference board."""

from job_radar.profile_fit import build_initial_fit_signals
from job_radar.profile_models import FitSignal, ManagedProfile, ProfilePreferences


def test_profile_evidence_overrides_generic_scoring_categories() -> None:
    profile = ManagedProfile(
        profile_id="profile_1a2b3c4d",
        display_name="Infrastructure Search",
        preferences=ProfilePreferences(
            core_strengths=("Linux",),
            credible_adjacent=("Kubernetes",),
            learning_or_gap=("Product marketing",),
            exclusions=("Sales",),
        ),
        scoring_config={
            "positive_keywords": {
                "linux": 10,
                "kubernetes": 8,
                "slurm": 10,
            },
            "negative_keywords": {
                "sales": -15,
            },
            "top_matches": {
                "strong_signals": [
                    "title:kubernetes",
                    "title:slurm",
                ],
            },
            "review_needed": {
                "strong_signals": [
                    "body:kubernetes",
                ],
            },
        },
    )

    signals = build_initial_fit_signals(profile)
    categories = {signal.term.casefold(): signal.category for signal in signals}

    assert categories["linux"] == "strong"
    assert categories["kubernetes"] == "review"
    assert categories["product marketing"] == "review"
    assert categories["sales"] == "avoid"
    assert categories["slurm"] == "strong"


def test_saved_fit_signals_are_not_rebuilt_or_overwritten() -> None:
    saved_signals = (
        FitSignal(
            term="Kubernetes",
            category="avoid",
            explanation="The user manually moved this signal.",
            evidence_source="user",
            user_overridden=True,
        ),
    )
    profile = ManagedProfile(
        profile_id="profile_1a2b3c4d",
        display_name="Infrastructure Search",
        fit_signals=saved_signals,
        scoring_config={
            "positive_keywords": {
                "kubernetes": 8,
            },
        },
    )

    assert build_initial_fit_signals(profile) is saved_signals


def test_inferred_signals_are_deduplicated_case_insensitively() -> None:
    profile = ManagedProfile(
        profile_id="profile_1a2b3c4d",
        display_name="Infrastructure Search",
        preferences=ProfilePreferences(
            core_strengths=("Linux",),
        ),
        scoring_config={
            "positive_keywords": {
                "linux": 10,
                "LINUX": 5,
            },
            "top_matches": {
                "strong_signals": [
                    "title:linux",
                ],
            },
        },
    )

    signals = build_initial_fit_signals(profile)

    assert [signal.term.casefold() for signal in signals].count("linux") == 1
    assert signals[0].category == "strong"
    assert signals[0].evidence_source == "profile"
