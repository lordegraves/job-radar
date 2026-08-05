"""Verify per-job troubleshooting traces explain decisions without documents."""

import json
from pathlib import Path

from job_radar.evaluation_audit import write_evaluation_trace_log
from job_radar.models import JobPosting
from job_radar.resume_match import ResumeMatchResult
from job_radar.scored_posting import ScoredPosting


def test_evaluation_trace_records_normalized_decision_and_bounded_gaps(
    tmp_path: Path,
) -> None:
    posting = JobPosting(
        company_key="example",
        company_name="Example Company",
        source_type="workday",
        source_job_id="job-1",
        source_url="https://example.invalid/job/1?private=parameter",
        title="Platform Engineer",
        location="Remote, United States",
        description="private full job description",
        remote_status="remote",
        normalization_state="complete",
    )
    scored = ScoredPosting(
        posting=posting,
        score=110,
        score_reasons=["+30 title:platform"],
        location_status="allowed",
        review_needed_eligible=True,
        resume_match=ResumeMatchResult(
            label="Partial",
            evidence=["private resume evidence"],
            gaps=["No large-scale Kubernetes operations experience"],
            requirements_reviewed=["private full qualification"],
            supported_requirements=["private supported qualification"],
        ),
    )

    path = write_evaluation_trace_log(
        tmp_path,
        [scored],
        scan_run_id=42,
        generated_at="2026-08-05T12:00:00+00:00",
    )

    assert path is not None
    assert path.name.startswith("junior-evaluation-run-42-")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["application_version"]
    assert payload["application_build"]
    assert payload["normalization_state"] == "complete"
    assert payload["requirements_reviewed"] == 1
    assert payload["material_gaps"] == [
        "No large-scale Kubernetes operations experience"
    ]
    assert payload["final_outcome"] == "needs review"
    assert payload["public_posting"] == "https://example.invalid/job/1"
    content = path.read_text(encoding="utf-8")
    assert "private full job description" not in content
    assert "private resume evidence" not in content
    assert "private full qualification" not in content
