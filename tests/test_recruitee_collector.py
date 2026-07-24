"""Verify Recruitee public jobs become normalized Junior postings."""

from __future__ import annotations

import requests

from job_radar.collectors.recruitee import collect_recruitee_jobs


class FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self):
        return {
            "offers": [
                {
                    "id": 42,
                    "title": "Head Baker",
                    "careers_url": "https://example.recruitee.com/o/head-baker",
                    "locations": [{"name": "Fort Collins, Colorado"}],
                    "description": "<p>Lead the bakery team.</p>",
                }
            ]
        }


def test_collect_recruitee_jobs_uses_public_offers_api(monkeypatch) -> None:
    def fake_get(url, **kwargs):
        assert url == "https://example.recruitee.com/api/offers/"
        assert kwargs["headers"]["Accept"] == "application/json"
        return FakeResponse()

    monkeypatch.setattr(requests, "get", fake_get)
    jobs = collect_recruitee_jobs(
        {
            "company_key": "example-bakery",
            "name": "Example Bakery",
            "source_type": "recruitee",
            "source_url": "https://example.recruitee.com/api/offers/",
        }
    )

    assert len(jobs) == 1
    assert jobs[0].title == "Head Baker"
    assert jobs[0].location == "Fort Collins, Colorado"
    assert jobs[0].source_job_id == "42"
    assert jobs[0].source_type == "recruitee"
