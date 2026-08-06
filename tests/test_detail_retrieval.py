from job_radar.candidate_profile import CandidateProfile
from job_radar.detail_retrieval import build_detail_retrieval_planner


def make_profile(**overrides) -> CandidateProfile:
    values = {
        "name": "Test Candidate",
        "compensation_floor_usd": None,
        "preferred_base_usd": None,
        "resume": None,
        "core_strengths": [],
        "credible_adjacent": [],
        "learning_or_gap": [],
        "avoid": [],
        "target_roles": [],
    }
    values.update(overrides)
    return CandidateProfile(**values)


def test_analytics_and_insights_titles_retrieve_detail_before_rejection() -> None:
    profile = make_profile(
        target_roles=["Data Analyst"],
        core_strengths=["customer insights"],
    )
    planner, _signature = build_detail_retrieval_planner(profile, {})

    decision = planner("Director, Consumer & Brand Insights", None)

    assert decision.retrieve is True
    assert "related work evidence" in decision.reason.lower()


def test_clearly_unrelated_title_can_still_skip_detail() -> None:
    profile = make_profile(target_roles=["Data Analyst"])
    planner, _signature = build_detail_retrieval_planner(profile, {})

    decision = planner("Restaurant Line Cook", None)

    assert decision.retrieve is False
