"""Tests TalentBrew pagination, deduplication, and safe stopping."""

import pytest

from job_radar.collectors.greenhouse import CollectorError
from job_radar.collectors.talentbrew import (
    _build_page_url,
    collect_talentbrew_jobs,
)
from job_radar.models import JobPosting


def _config(**overrides):
    config = {
        "company_key": "ford",
        "name": "Ford",
        "source_type": "talentbrew",
        "source_url": "https://www.careers.ford.com/search-jobs",
    }
    config.update(overrides)
    return config


def _posting(job_id: str) -> JobPosting:
    return JobPosting(
        company_key="ford",
        company_name="Ford",
        source_type="talentbrew",
        source_job_id=job_id,
        source_url=f"https://www.careers.ford.com/job/{job_id}",
        title=f"Infrastructure Engineer {job_id}",
        location="United States",
        description=None,
    )


def test_talentbrew_collects_pages_until_an_empty_page(monkeypatch) -> None:
    requested_urls = []
    pages = {
        1: [_posting("1"), _posting("2")],
        2: [_posting("3")],
        3: [],
    }

    def fake_collect(config, url):
        del config
        requested_urls.append(url)
        page = int(url.rsplit("=", 1)[-1]) if "?p=" in url else 1
        return pages[page]

    monkeypatch.setattr(
        "job_radar.collectors.talentbrew.collect_html_jobs_page",
        fake_collect,
    )

    postings = collect_talentbrew_jobs(_config())

    assert [posting.source_job_id for posting in postings] == ["1", "2", "3"]
    assert requested_urls == [
        "https://www.careers.ford.com/search-jobs",
        "https://www.careers.ford.com/search-jobs?p=2",
        "https://www.careers.ford.com/search-jobs?p=3",
    ]


def test_talentbrew_stops_when_a_page_repeats(monkeypatch) -> None:
    calls = []

    def fake_collect(config, url):
        del config
        calls.append(url)
        return [_posting("1"), _posting("2")]

    monkeypatch.setattr(
        "job_radar.collectors.talentbrew.collect_html_jobs_page",
        fake_collect,
    )

    postings = collect_talentbrew_jobs(_config(max_pages=80))

    assert [posting.source_job_id for posting in postings] == ["1", "2"]
    assert len(calls) == 2


def test_talentbrew_respects_bounded_page_limit(monkeypatch) -> None:
    calls = []

    def fake_collect(config, url):
        del config
        calls.append(url)
        return [_posting(str(len(calls)))]

    monkeypatch.setattr(
        "job_radar.collectors.talentbrew.collect_html_jobs_page",
        fake_collect,
    )

    postings = collect_talentbrew_jobs(_config(max_pages=2))

    assert len(postings) == 2
    assert len(calls) == 2


def test_talentbrew_page_url_preserves_existing_search_filters() -> None:
    url = _build_page_url(
        "https://jobs.example.com/search-jobs?location=Michigan&sort=recent&p=9",
        2,
    )

    assert url == (
        "https://jobs.example.com/search-jobs?"
        "location=Michigan&sort=recent&p=2"
    )


def test_talentbrew_labels_a_later_page_failure(monkeypatch) -> None:
    calls = 0

    def fake_collect(config, url):
        nonlocal calls
        del config, url
        calls += 1
        if calls == 2:
            raise CollectorError("synthetic request failure")
        return [_posting("1")]

    monkeypatch.setattr(
        "job_radar.collectors.talentbrew.collect_html_jobs_page",
        fake_collect,
    )

    with pytest.raises(CollectorError) as caught:
        collect_talentbrew_jobs(_config())

    assert caught.value.failure_stage == "results_pagination_request"
    assert "later results page" in str(caught.value)
