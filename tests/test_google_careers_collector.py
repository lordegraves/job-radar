import json

import pytest

from job_radar.collectors.google_careers import (
    _extract_jobs_payload,
    collect_google_careers_jobs,
)
from job_radar.collectors.greenhouse import CollectorError


def _job(job_id: str, title: str, location: str = "Remote, US") -> list[object]:
    fields: list[object] = [None] * 21
    fields[0] = job_id
    fields[1] = title
    fields[3] = [None, "<h3>Responsibilities</h3><ul><li>Operate systems.</li></ul>"]
    fields[4] = [
        None,
        "<h3>Minimum qualifications:</h3><ul><li>Five years of Linux experience.</li></ul>"
        "<h3>Preferred qualifications:</h3><ul><li>Kubernetes experience.</li></ul>",
    ]
    fields[9] = [[location, [location], "Remote", None, None, "US"]]
    fields[10] = [None, "<h3>About the job</h3><p>Build reliable infrastructure. " * 12 + "</p>"]
    fields[19] = [None, "<ul><li>Five years of Linux experience.</li></ul>"]
    return fields


def _page(jobs: object, total: int, size: int = 20) -> str:
    payload = json.dumps([jobs, None, total, size])
    return f"<script>AF_initDataCallback({{key: 'ds:1', hash: '2', data:{payload}, sideChannel: {{}}}});</script>"


def test_google_collector_reads_complete_job_and_remote_region(monkeypatch) -> None:
    class Response:
        text = _page([_job("123", "Senior Platform Engineer")], 1)

    monkeypatch.setattr(
        "job_radar.collectors.google_careers.get_response",
        lambda *args, **kwargs: Response(),
    )
    jobs = collect_google_careers_jobs(
        {
            "company_key": "google",
            "name": "Google",
            "source_url": "https://www.google.com/about/careers/applications/jobs/results",
        }
    )

    assert len(jobs) == 1
    posting = jobs[0]
    assert posting.source_job_id == "123"
    assert posting.source_url.endswith("/123-senior-platform-engineer")
    assert posting.location == "Remote, US"
    assert posting.remote_status == "Remote"
    assert "Minimum qualifications:" in posting.description
    assert "Five years of Linux experience." in posting.description
    assert "Preferred qualifications:" in posting.description
    assert "Build reliable infrastructure." in posting.description


def test_google_collector_reads_all_reported_pages_concurrently(monkeypatch) -> None:
    pages = {
        1: _page([_job("1", "First Role")], 3, 1),
        2: _page([_job("2", "Second Role")], 3, 1),
        3: _page([_job("3", "Third Role")], 3, 1),
    }

    class Response:
        def __init__(self, text: str) -> None:
            self.text = text

    def fake_get(url, **kwargs):
        page = int(url.rsplit("page=", 1)[1]) if "page=" in url else 1
        return Response(pages[page])

    monkeypatch.setattr(
        "job_radar.collectors.google_careers.get_response", fake_get
    )
    jobs = collect_google_careers_jobs(
        {
            "company_key": "google",
            "name": "Google",
            "source_url": "https://www.google.com/about/careers/applications/jobs/results",
        }
    )

    assert [job.source_job_id for job in jobs] == ["1", "2", "3"]


def test_google_connection_test_honors_one_page_limit(monkeypatch) -> None:
    class Response:
        text = _page([_job("1", "First Role")], 200, 20)

    calls: list[str] = []

    def fake_get(url, **kwargs):
        calls.append(url)
        return Response()

    monkeypatch.setattr(
        "job_radar.collectors.google_careers.get_response", fake_get
    )
    jobs = collect_google_careers_jobs(
        {
            "company_key": "google",
            "name": "Google",
            "source_url": "https://www.google.com/about/careers/applications/jobs/results",
            "max_pages": 1,
        }
    )

    assert len(jobs) == 1
    assert len(calls) == 1


def test_google_collector_rejects_missing_or_truncated_payload() -> None:
    with pytest.raises(CollectorError, match="did not provide"):
        _extract_jobs_payload("<html></html>")
    with pytest.raises(CollectorError, match="truncated"):
        _extract_jobs_payload("<script>key: 'ds:1', data:[[</script>")
