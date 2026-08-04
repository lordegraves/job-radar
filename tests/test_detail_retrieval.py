from job_radar.candidate_profile import CandidateProfile
from job_radar.detail_retrieval import build_detail_retrieval_planner


def _profile() -> CandidateProfile:
    return CandidateProfile(
        name="Infrastructure candidate",
        compensation_floor_usd=None,
        preferred_base_usd=None,
        resume=None,
        core_strengths=["Linux infrastructure", "HPC operations", "networking"],
        credible_adjacent=["technical consulting"],
        learning_or_gap=[],
        avoid=["security engineering", "software development"],
        target_roles=["Platform Engineer", "Infrastructure Engineer", "HPC Engineer"],
    )


def test_retrieval_planner_skips_clear_unrelated_title() -> None:
    planner, _signature = build_detail_retrieval_planner(
        _profile(),
        {"positive_keywords": {}, "negative_keywords": {}, "top_matches": {}},
    )

    decision = planner("Senior Tax Accountant", "Houston, Texas")

    assert decision.retrieve is False
    assert "not ambiguous" in decision.reason


def test_retrieval_planner_keeps_ambiguous_and_related_titles() -> None:
    planner, _signature = build_detail_retrieval_planner(
        _profile(),
        {"positive_keywords": {}, "negative_keywords": {}, "top_matches": {}},
    )

    assert planner("Systems Engineer", None).retrieve is True
    assert planner("HPC Technical Consultant", None).retrieve is True
    assert planner("Platform Reliability Engineer", None).retrieve is True


def test_retrieval_planner_applies_explicit_profile_exclusion() -> None:
    planner, _signature = build_detail_retrieval_planner(
        _profile(),
        {"positive_keywords": {}, "negative_keywords": {}, "top_matches": {}},
    )

    decision = planner("Principal Security Engineering Lead", None)

    assert decision.retrieve is False
    assert "profile exclusion" in decision.reason
