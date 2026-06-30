import pytest

from job_radar.candidate_profile import load_candidate_profile
from job_radar.config import ConfigError


def test_load_candidate_profile_reads_candidate_fields(tmp_path) -> None:
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(
        """
candidate:
  name: Clayton Graves
  compensation_floor_usd: 160000
  preferred_base_usd: 185000
  resume:
    source_path: profiles/clayton/resume.md
    normalized_text_path: profiles/clayton/resume.normalized.txt
  core_strengths:
    - Linux infrastructure
    - HPC operations
  credible_adjacent:
    - SRE
  learning_or_gap:
    - production Kubernetes ownership
  avoid:
    - frontend
""",
        encoding="utf-8",
    )

    profile = load_candidate_profile(profile_path)

    assert profile.name == "Clayton Graves"
    assert profile.compensation_floor_usd == 160000
    assert profile.preferred_base_usd == 185000
    assert profile.resume is not None
    assert profile.resume.source_path == "profiles/clayton/resume.md"
    assert profile.resume.normalized_text_path == "profiles/clayton/resume.normalized.txt"
    assert profile.core_strengths == ["Linux infrastructure", "HPC operations"]
    assert profile.credible_adjacent == ["SRE"]
    assert profile.learning_or_gap == ["production Kubernetes ownership"]
    assert profile.avoid == ["frontend"]


def test_load_candidate_profile_rejects_missing_candidate_mapping(tmp_path) -> None:
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text("name: Clayton Graves\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="top-level candidate mapping"):
        load_candidate_profile(profile_path)