"""Verify public Avature RSS job-feed collection."""

from __future__ import annotations

import requests

from job_radar.collectors.avature import collect_avature_jobs


class FakeResponse:
    def __init__(self, content: bytes, status_code: int = 200) -> None:
        self.content = content
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


def test_avature_collector_reads_official_rss_items(monkeypatch) -> None:
    xml = b"""<?xml version="1.0"?>
    <rss><channel>
      <item>
        <title>Platform Engineer</title>
        <description>Operate reliable infrastructure.</description>
        <link>https://careers.example.test/careers/JobDetail/Platform-Engineer/44217</link>
      </item>
    </channel></rss>
    """
    monkeypatch.setattr(
        requests,
        "get",
        lambda *_args, **_kwargs: FakeResponse(xml),
    )

    jobs = collect_avature_jobs(
        {
            "company_key": "example",
            "name": "Example",
            "source_type": "avature",
            "source_url": "https://example.avature.net/en_US/careers/SearchJobs/feed/",
        }
    )

    assert len(jobs) == 1
    assert jobs[0].title == "Platform Engineer"
    assert jobs[0].source_job_id == "44217"
    assert jobs[0].detail_retrieval_state == "summary_only"
