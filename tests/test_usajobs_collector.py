from __future__ import annotations

import pytest

from job_radar.collectors.greenhouse import CollectorError
from job_radar.collectors.usajobs import (
    _build_params,
    _parse_search_items,
)


def make_company(**extra):
    company = {
        "company_key": "nasa_usajobs",
        "name": "NASA",
        "source_type": "usajobs",
        "enabled": True,
    }
    company.update(extra)
    return company


def test_build_params_includes_extra_query_params():
    company = make_company(
        query_params={
            "Organization": "NN",
            "Keyword": "linux",
            "LocationName": "",
        }
    )

    params = _build_params(company, page=2)

    assert params["Page"] == 2
    assert params["ResultsPerPage"] == 100
    assert params["Organization"] == "NN"
    assert params["Keyword"] == "linux"
    assert "LocationName" not in params


def test_parse_search_items_returns_job_postings():
    company = make_company()

    payload = {
        "SearchResult": {
            "SearchResultItems": [
                {
                    "MatchedObjectDescriptor": {
                        "PositionID": "12345",
                        "PositionTitle": "HPC Systems Engineer",
                        "PositionURI": "https://www.usajobs.gov/job/12345",
                        "PositionLocation": [
                            {"LocationName": "Greenbelt, Maryland"},
                            {"LocationName": "Remote job"},
                        ],
                        "QualificationSummary": "Linux cluster experience.",
                        "MajorDuties": "Operate HPC systems.",
                        "Requirements": "US citizenship is required.",
                    }
                }
            ]
        }
    }

    postings = _parse_search_items(company, payload)

    assert len(postings) == 1
    posting = postings[0]
    assert posting.company_key == "nasa_usajobs"
    assert posting.company_name == "NASA"
    assert posting.source_type == "usajobs"
    assert posting.source_job_id == "12345"
    assert posting.source_url == "https://www.usajobs.gov/job/12345"
    assert posting.title == "HPC Systems Engineer"
    assert posting.location == "Greenbelt, Maryland; Remote job"
    assert "Linux cluster experience." in posting.description
    assert "US citizenship is required." in posting.description


def test_parse_search_items_skips_missing_required_fields():
    company = make_company()

    payload = {
        "SearchResult": {
            "SearchResultItems": [
                {
                    "MatchedObjectDescriptor": {
                        "PositionID": "12345",
                        "PositionTitle": "",
                        "PositionURI": "https://www.usajobs.gov/job/12345",
                    }
                }
            ]
        }
    }

    postings = _parse_search_items(company, payload)

    assert postings == []


def test_parse_search_items_rejects_missing_search_result():
    company = make_company()

    with pytest.raises(CollectorError, match="missing SearchResult"):
        _parse_search_items(company, {})