"""Verify background source tests report bounded progress without importing jobs."""

import time

from job_radar.source_test_runner import SourceTestRunner


class _Health:
    def __init__(self, state: str) -> None:
        self.state = state


def test_source_test_runner_reports_completion_and_failures() -> None:
    tested: list[str] = []

    def run_test(employer_id: str) -> _Health:
        tested.append(employer_id)
        return _Health("error" if employer_id == "broken" else "success")

    runner = SourceTestRunner(run_test)

    assert runner.start(["working", "broken"]) is True
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
    }
