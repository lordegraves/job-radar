import copy
import json

import pytest

from job_radar.collectors.greenhouse import CollectorError
from job_radar.collectors.rippling import (
    build_rippling_jobs_url,
    collect_rippling_jobs,
    extract_rippling_next_data,
    get_rippling_total_pages,
    parse_rippling_jobs,
)


def make_company_config() -> dict[str, object]:
    return {
        "company_key": "cbts",
        "name": "CBTS",
        "source_type": "rippling",
        "source_slug": "cbts",
        "enabled": True,
    }


def make_payload() -> dict[str, object]:
    return {
        "props": {
            "pageProps": {
                "dehydratedState": {
                    "queries": [
                        {
                            "queryKey": [
                                "board",
                                "cbts",
                                "job-posts",
                                False,
                                {
                                    "page": 0,
                                    "pageSize": 20,
                                    "searchQuery": "",
                                },
                            ],
                            "state": {
                                "data": {
                                    "items": [
                                        {
                                            "department": {
                                                "name": "Network Engineering",
                                            },
                                            "id": "job-1",
                                            "language": "en-US",
                                            "locations": [
                                                {
                                                    "name": "Remote (United States)",
                                                    "workplaceType": "REMOTE",
                                                }
                                            ],
                                            "name": "Senior Network Engineer",
                                            "url": "https://ats.rippling.com/cbts/jobs/job-1",
                                        },
                                        {
                                            "department": {
                                                "name": "Network Engineering",
                                            },
                                            "id": "job-1",
                                            "language": "en-US",
                                            "locations": [
                                                {
                                                    "name": "Cincinnati, OH",
                                                    "workplaceType": "REMOTE",
                                                }
                                            ],
                                            "name": "Senior Network Engineer",
                                            "url": "https://ats.rippling.com/cbts/jobs/job-1",
                                        },
                                        {
                                            "department": {
                                                "name": "Security",
                                            },
                                            "id": "job-2",
                                            "language": "en-US",
                                            "locations": [
                                                {
                                                    "name": "Chicago, IL",
                                                    "workplaceType": "REMOTE",
                                                }
                                            ],
                                            "name": "Security Services Specialist",
                                            "url": "https://ats.rippling.com/cbts/jobs/job-2",
                                        },
                                    ],
                                    "page": 0,
                                    "pageSize": 20,
                                    "totalItems": 23,
                                    "totalPages": 2,
                                }
                            },
                        },
                        {
                            "queryKey": ["board", "cbts", "locations"],
                            "state": {
                                "data": {
                                    "items": [
                                        {"name": "Remote (United States)"},
                                    ],
                                    "page": 0,
                                    "pageSize": 1,
                                    "totalItems": 1,
                                    "totalPages": 1,
                                }
                            },
                        },
                    ]
                }
            }
        }
    }


def test_build_rippling_jobs_url() -> None:
    assert (
        build_rippling_jobs_url("cbts", page=1)
        == "https://ats.rippling.com/cbts/jobs?page=1"
    )


def test_extract_rippling_next_data() -> None:
    payload = make_payload()
    html = (
        '<html><script id="__NEXT_DATA__" type="application/json">'
        f"{json.dumps(payload)}"
        "</script></html>"
    )

    assert extract_rippling_next_data(html) == payload


def test_extract_rippling_next_data_rejects_missing_json() -> None:
    with pytest.raises(CollectorError, match="__NEXT_DATA__"):
        extract_rippling_next_data("<html></html>")


def test_get_rippling_total_pages() -> None:
    assert get_rippling_total_pages(make_payload()) == 2


def test_parse_rippling_jobs_returns_job_postings_and_merges_locations() -> None:
    postings = parse_rippling_jobs(make_company_config(), make_payload())

    assert len(postings) == 2

    posting = postings[0]

    assert posting.company_key == "cbts"
    assert posting.company_name == "CBTS"
    assert posting.source_type == "rippling"
    assert posting.source_job_id == "job-1"
    assert posting.source_url == "https://ats.rippling.com/cbts/jobs/job-1"
    assert posting.title == "Senior Network Engineer"
    assert posting.location == "Remote (United States); Cincinnati, OH"
    assert posting.description == "Department: Network Engineering"
    assert posting.canonical_key is not None
    assert posting.content_hash is not None


def test_parse_rippling_jobs_skips_jobs_missing_title() -> None:
    payload = make_payload()
    job_posts = (
        payload["props"]["pageProps"]["dehydratedState"]["queries"][0]["state"]["data"][
            "items"
        ]
    )
    job_posts[0].pop("name")

    postings = parse_rippling_jobs(make_company_config(), payload)

    assert len(postings) == 2
    assert all(posting.title for posting in postings)


def test_parse_rippling_jobs_rejects_payload_without_job_posts() -> None:
    payload = {
        "props": {
            "pageProps": {
                "dehydratedState": {
                    "queries": [
                        {
                            "queryKey": ["board", "cbts", "locations"],
                            "state": {"data": {"items": []}},
                        }
                    ]
                }
            }
        }
    }

    with pytest.raises(CollectorError, match="job-posts"):
        parse_rippling_jobs(make_company_config(), payload)


def test_collect_rippling_jobs_stops_at_configured_max_pages(
    monkeypatch,
) -> None:
    company_config = {
        **make_company_config(),
        "max_pages": 2,
    }
    requested_urls: list[str] = []

    def fake_fetch_payload(url: str) -> dict[str, object]:
        requested_urls.append(url)
        payload = copy.deepcopy(make_payload())

        job_posts_query = payload["props"]["pageProps"]["dehydratedState"][
            "queries"
        ][0]
        job_posts_query["state"]["data"]["totalPages"] = 500

        return payload

    monkeypatch.setattr(
        "job_radar.collectors.rippling._fetch_rippling_payload",
        fake_fetch_payload,
    )

    postings = collect_rippling_jobs(company_config)

    assert requested_urls == [
        "https://ats.rippling.com/cbts/jobs?page=0",
        "https://ats.rippling.com/cbts/jobs?page=1",
    ]
    assert len(postings) == 2
    