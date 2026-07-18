"""Tests SchoolSpring list and detail requests, pagination, and normalization."""

import pytest

from job_radar.collectors.greenhouse import CollectorError
from job_radar.collectors.schoolspring import (
    build_schoolspring_job_detail_url,
    build_schoolspring_jobs_url,
    parse_schoolspring_jobs,
)


def make_company_config() -> dict[str, object]:
    return {
        "company_key": "poudre_school_district",
        "name": "Poudre School District",
        "source_type": "schoolspring",
        "domain_name": "psdschools.schoolspring.com",
        "enabled": True,
    }


def make_list_payload() -> dict[str, object]:
    return {
        "success": True,
        "message": "",
        "validationErrors": [],
        "value": {
            "page": 1,
            "size": 20,
            "jobsList": [
                {
                    "jobId": 5814459,
                    "employer": "WEBBER MS",
                    "title": "2026-27 Paraprofessional II Special Education-Webber Middle School",
                    "location": "FORT COLLINS, Colorado",
                    "displayDate": "2026-07-02T06:00:00",
                }
            ],
        },
    }


def make_detail_payload() -> dict[str, object]:
    return {
        "success": True,
        "message": "",
        "validationErrors": [],
        "value": {
            "formattedExternalCloseDate": "Jul 06, 2026 11:59 PM (Mountain Standard Time)",
            "isAtsJob": True,
            "jobCategories": [
                {
                    "category": "Instructional Support",
                    "subCategory": "Paraprofessional / IA",
                }
            ],
            "jobInfo": {
                "jobId": 5814459,
                "jobTitle": "2026-27 Paraprofessional II Special Education-Webber Middle School",
                "infoURL": "https://psdschools.tedk12.com/hire/ViewJob.aspx?JobID=14135",
                "externalJobCode": "14135",
                "applicationDeadline": "2026-07-07T05:59:00",
                "jobDescription": "<p>Support students and classroom staff.</p>",
            },
            "jobLocations": [
                {
                    "locationID": 123,
                    "locationName": "WEBBER MS",
                    "displayLocation": "Fort Collins, Colorado",
                }
            ],
        },
    }


def test_build_schoolspring_jobs_url() -> None:
    url = build_schoolspring_jobs_url(
        "psdschools.schoolspring.com",
        page=1,
        page_size=20,
    )

    assert url.startswith(
        "https://api.schoolspring.com/api/Jobs/GetPagedJobsWithSearch?"
    )
    assert "domainName=psdschools.schoolspring.com" in url
    assert "page=1" in url
    assert "size=20" in url
    assert "sortDateAscending=false" in url


def test_build_schoolspring_job_detail_url() -> None:
    assert (
        build_schoolspring_job_detail_url(5814459)
        == "https://api.schoolspring.com/api/Jobs/5814459"
    )


def test_parse_schoolspring_jobs_uses_detail_payload() -> None:
    postings = parse_schoolspring_jobs(
        make_company_config(),
        make_list_payload(),
        detail_payloads={"5814459": make_detail_payload()},
    )

    assert len(postings) == 1

    posting = postings[0]

    assert posting.company_key == "poudre_school_district"
    assert posting.company_name == "Poudre School District"
    assert posting.source_type == "schoolspring"
    assert posting.source_job_id == "5814459"
    assert (
        posting.source_url
        == "https://psdschools.tedk12.com/hire/ViewJob.aspx?JobID=14135"
    )
    assert (
        posting.title
        == "2026-27 Paraprofessional II Special Education-Webber Middle School"
    )
    assert posting.location == "Fort Collins, Colorado"
    assert posting.description is not None
    assert "Support students and classroom staff." in posting.description
    assert "Employer: WEBBER MS" in posting.description
    assert "Instructional Support: Paraprofessional / IA" in posting.description
    assert posting.canonical_key is not None
    assert posting.content_hash is not None


def test_parse_schoolspring_jobs_falls_back_without_detail_payload() -> None:
    postings = parse_schoolspring_jobs(make_company_config(), make_list_payload())

    assert len(postings) == 1

    posting = postings[0]

    assert posting.source_job_id == "5814459"
    assert posting.source_url == "https://psdschools.schoolspring.com/?jobId=5814459"
    assert posting.location == "FORT COLLINS, Colorado"
    assert posting.description == "Employer: WEBBER MS"


def test_parse_schoolspring_jobs_decodes_html_entities() -> None:
    payload = make_list_payload()
    jobs_list = payload["value"]["jobsList"]
    jobs_list[0]["title"] = "Language, Culture, &amp; Equity"

    postings = parse_schoolspring_jobs(make_company_config(), payload)

    assert postings[0].title == "Language, Culture, & Equity"


def test_parse_schoolspring_jobs_rejects_unsuccessful_payload() -> None:
    payload = {
        "success": False,
        "message": "bad request",
        "validationErrors": [],
        "value": None,
    }

    with pytest.raises(CollectorError, match="success=false"):
        parse_schoolspring_jobs(make_company_config(), payload)


def test_parse_schoolspring_jobs_rejects_payload_without_jobs_list() -> None:
    payload = {
        "success": True,
        "message": "",
        "validationErrors": [],
        "value": {},
    }

    with pytest.raises(CollectorError, match="jobsList"):
        parse_schoolspring_jobs(make_company_config(), payload)
