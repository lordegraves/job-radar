"""Verify Eightfold public search results become normalized Junior jobs."""

from job_radar.collectors.eightfold import collect_eightfold_jobs


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def test_eightfold_collector_fetches_search_and_detail(monkeypatch) -> None:
    calls = []

    def fake_get_response(url, **kwargs):
        calls.append((url, kwargs))
        if url.endswith("/api/pcsx/search"):
            return _Response(
                {
                    "data": {
                        "count": 1,
                        "positions": [
                            {
                                "id": 123,
                                "displayJobId": "JR-123",
                                "name": "Platform Engineer",
                                "locations": ["Colorado, United States"],
                                "positionUrl": "/careers/job/123",
                            }
                        ],
                    }
                }
            )
        return _Response(
            {
                "data": {
                    "displayJobId": "JR-123",
                    "locations": ["Colorado, United States"],
                    "jobDescription": "<p>Operate reliable systems.</p>",
                    "workLocationOption": "hybrid",
                }
            }
        )

    monkeypatch.setattr(
        "job_radar.collectors.eightfold.get_response",
        fake_get_response,
    )
    jobs = collect_eightfold_jobs(
        {
            "company_key": "example",
            "name": "Example",
            "source_type": "eightfold",
            "source_url": "https://apply.example.com",
            "domain": "example.com",
        }
    )

    assert len(jobs) == 1
    assert jobs[0].title == "Platform Engineer"
    assert jobs[0].description == "Operate reliable systems."
    assert jobs[0].remote_status == "hybrid"
    assert jobs[0].source_url == "https://apply.example.com/careers/job/123"
    assert calls[0][1]["params"]["domain"] == "example.com"
    assert calls[1][1]["params"]["position_id"] == "123"


def test_microsoft_url_detects_eightfold_source() -> None:
    from job_radar.employer_resolution_service import detect_employer_source

    result = detect_employer_source(
        "https://careers.microsoft.com/v2/global/en/home.html"
    )

    assert result.scan_ready is True
    assert result.source_type == "eightfold"
    assert result.source_config["source_url"] == (
        "https://apply.careers.microsoft.com"
    )
    assert result.source_config["display_name"] == "Microsoft"
