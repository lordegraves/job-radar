"""Verify background source tests report bounded progress without importing jobs."""

import time

from job_radar.source_test_runner import SourceTestRunner


class _Health:
    def __init__(self, state: str, message: str, job_count: int | None) -> None:
        self.state = state
        self.message = message
        self.job_count = job_count
        self.tested_at = "2026-07-27 15:00:00"


def test_source_test_runner_reports_completion_and_failures() -> None:
    tested: list[str] = []

    def run_test(employer_id: str) -> _Health:
        tested.append(employer_id)
        if employer_id == "broken":
            return _Health("error", "The source rejected the request.", None)
        return _Health("success", "Connection succeeded and returned 12 jobs.", 12)

    runner = SourceTestRunner(run_test)

    assert runner.start(
        ["working", "broken"],
        labels={"working": "Working Company", "broken": "Broken Company"},
    ) is True
    for _ in range(100):
        if not runner.status()["running"]:
            break
        time.sleep(0.001)

    assert tested == ["working", "broken"]
    assert runner.status() == {
        "running": False,
        "completed": 2,
        "total": 2,
        "failed": 1,
        "current": None,
        "current_label": None,
        "current_step": "Testing finished with source failures.",
        "results": (
            {
                "employer_id": "working",
                "employer_name": "Working Company",
                "state": "success",
                "message": "Connection succeeded and returned 12 jobs.",
                "job_count": 12,
                "tested_at": "2026-07-27 15:00:00",
            },
            {
                "employer_id": "broken",
                "employer_name": "Broken Company",
                "state": "failed",
                "message": "The source rejected the request.",
                "job_count": None,
                "tested_at": "2026-07-27 15:00:00",
            },
        ),
    }


def test_source_test_runner_records_safe_unexpected_failure() -> None:
    recorded: list[tuple[str, str]] = []

    def fail_test(_employer_id: str) -> _Health:
        raise RuntimeError("private response details must not be displayed")

    runner = SourceTestRunner(
        fail_test,
        record_unexpected_failure=lambda employer_id, error_type: recorded.append(
            (employer_id, error_type)
        ),
    )
    assert runner.start(["broken"], labels={"broken": "Broken Company"}) is True
    for _ in range(100):
        if not runner.status()["running"]:
            break
        time.sleep(0.001)

    result = runner.status()["results"][0]
    assert recorded == [("broken", "RuntimeError")]
    assert result["state"] == "failed"
    assert "no source-health conclusion was reached" in str(result["message"])
    assert "private response details" not in str(result["message"])
