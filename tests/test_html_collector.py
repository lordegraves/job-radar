"""Tests job discovery and normalization from ordinary HTML career pages."""

from __future__ import annotations

from typing import Any

import pytest
import requests

from job_radar.collectors.greenhouse import CollectorError
from job_radar.collectors.html import (
    _extract_location_from_url,
    _extract_source_job_id,
    _get_timeout_seconds,
    _parse_html_jobs,
    collect_html_jobs,
)


class FakeResponse:
    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")


def _company_config() -> dict[str, Any]:
    return {
        "company_key": "ornl",
        "name": "Oak Ridge National Laboratory",
        "source_type": "html",
        "source_url": "https://jobs.ornl.gov/go/Computational-SciencesSupercomputing-Jobs/4534300/",
    }


def test_get_timeout_seconds_uses_config_value() -> None:
    config = _company_config()
    config["timeout_seconds"] = 90

    assert _get_timeout_seconds(config) == 90


def test_get_timeout_seconds_defaults_for_invalid_values() -> None:
    config = _company_config()

    assert _get_timeout_seconds(config) == 30
    config["timeout_seconds"] = "invalid"
    assert _get_timeout_seconds(config) == 30

    config["timeout_seconds"] = 0
    assert _get_timeout_seconds(config) == 30


def test_parse_html_jobs_reads_schema_org_job_posting() -> None:
    html = """
    <script type="application/ld+json">
    {
      "@context": "https://schema.org",
      "@type": "JobPosting",
      "identifier": {"value": "baker-42"},
      "title": "Head Baker",
      "description": "<p>Lead the bakery team.</p>",
      "url": "/jobs/head-baker",
      "jobLocation": {
        "@type": "Place",
        "address": {
          "addressLocality": "Fort Collins",
          "addressRegion": "Colorado"
        }
      }
    }
    </script>
    """

    jobs = _parse_html_jobs(
        _company_config(),
        html,
        "https://careers.example.invalid/openings",
    )

    assert len(jobs) == 1
    assert jobs[0].title == "Head Baker"
    assert jobs[0].location == "Fort Collins, Colorado"
    assert jobs[0].source_job_id == "baker-42"
    assert jobs[0].source_url == "https://careers.example.invalid/jobs/head-baker"


def test_parse_html_jobs_reads_complete_embedded_jobs_data() -> None:
    html = """
    <script>
    const jobsData = [{
      "id": 1639,
      "name_with_override": "Senior Payroll Officer",
      "full_description": "Run weekly payroll and maintain strong controls.",
      "location": "Wellington"
    }];
    </script>
    """

    jobs = _parse_html_jobs(
        _company_config(),
        html,
        "https://careers.example.test/jobs",
    )

    assert len(jobs) == 1
    assert jobs[0].source_job_id == "1639"
    assert jobs[0].title == "Senior Payroll Officer"
    assert jobs[0].location == "Wellington"
    assert jobs[0].description == (
        "Run weekly payroll and maintain strong controls."
    )
    assert jobs[0].source_url == "https://careers.example.test/jobs/1639"


def test_parse_html_jobs_reads_legacy_hrmdirect_rows() -> None:
    html = """
    <tr class="reqitem" data-req-id="3699712">
      <td>Engineering</td>
      <td class="posTitle"><a href="job-opening.php?req=3699712&amp;#job">
        GNC Engineer III
      </td>
      <td class="state">TX</td>
    </tr>
    <tr class="reqitem" data-req-id="3699723">
      <td>Engineering</td>
      <td class="posTitle"><a href="job-opening.php?req=3699723&amp;#job">
        Platform Engineer
      </td>
      <td class="state">CA</td>
    </tr>
    """

    jobs = _parse_html_jobs(
        _company_config(),
        html,
        "https://example.hrmdirect.com/employment/job-openings.php?search=true",
    )

    assert [(job.source_job_id, job.title, job.location) for job in jobs] == [
        ("3699712", "GNC Engineer III", "TX"),
        ("3699723", "Platform Engineer", "CA"),
    ]


def test_parse_html_jobs_supports_configured_nintendo_job_cards() -> None:
    html = """
    <a class="job-card" href="/jobs/4130435009/">
      <h3 class="job-card-title">Sr Engineer, IT Security (NTD)</h3>
      <div><span>Redmond, WA</span><span>Software Development</span></div>
    </a>
    """
    config = _company_config()
    config["job_link_patterns"] = ["/jobs/"]

    jobs = _parse_html_jobs(
        config,
        html,
        "https://careers.nintendo.com/jobs/",
    )

    assert len(jobs) == 1
    assert jobs[0].title == "Sr Engineer, IT Security (NTD)"
    assert jobs[0].source_job_id == "4130435009"


def test_parse_html_jobs_supports_valve_query_links_without_configuration() -> None:
    html = """
    <a href="https://www.valvesoftware.com/en/jobs?job_id=27">
      <h5 class="job_title">Software Engineer</h5>
    </a>
    """
    config = _company_config()

    jobs = _parse_html_jobs(
        config,
        html,
        "https://www.valvesoftware.com/en/jobs",
    )

    assert len(jobs) == 1
    assert jobs[0].title == "Software Engineer"
    assert jobs[0].source_job_id == "27"


def test_collect_html_jobs_rejects_browser_challenge(monkeypatch) -> None:
    class FakeResponse:
        text = (
            '<script src="/cdn-cgi/challenge-platform/start"></script>'
            "Enable JavaScript and cookies to continue"
        )

    monkeypatch.setattr(
        "job_radar.collectors.html.get_response",
        lambda *_args, **_kwargs: FakeResponse(),
    )

    with pytest.raises(CollectorError, match="interactive browser challenge"):
        collect_html_jobs(_company_config())


def test_parse_html_jobs_supports_rocket_lab_position_cards() -> None:
    html = """
    <div class="job__container">
      <a class="job" href="/careers/positions/systems-engineer-denver-123/">
        <div class="job__title">Systems Engineer</div>
        <div class="job__location">Denver, CO</div>
      </a>
    </div>
    """

    jobs = _parse_html_jobs(
        _company_config(),
        html,
        "https://rocketlabcorp.com/careers/positions/",
    )

    assert len(jobs) == 1
    assert jobs[0].title == "Systems Engineer"
    assert jobs[0].source_url == (
        "https://rocketlabcorp.com/careers/positions/"
        "systems-engineer-denver-123/"
    )

def test_extract_source_job_id_from_successfactors_url() -> None:
    assert (
        _extract_source_job_id(
            "https://jobs.ornl.gov/job/Oak-Ridge-IAM-Linux-Engineer-TN-37830/1394830700/"
        )
        == "1394830700"
    )


def test_extract_location_from_successfactors_url() -> None:
    assert (
        _extract_location_from_url(
            "https://jobs.ornl.gov/job/Oak-Ridge-IAM-Linux-Engineer-TN-37830/1394830700/"
        )
        == "Oak Ridge, TN"
    )


def test_parse_html_jobs_returns_job_postings() -> None:
    html = """
    <html>
      <body>
        <span class="jobTitle hidden-phone">
          <a href="/job/Oak-Ridge-IAM-Linux-Engineer-TN-37830/1394830700/" class="jobTitle-link">IAM Linux Engineer</a>
        </span>
      </body>
    </html>
    """

    postings = _parse_html_jobs(
        company_config=_company_config(),
        html=html,
        source_url="https://jobs.ornl.gov/go/Computational-SciencesSupercomputing-Jobs/4534300/",
    )

    assert len(postings) == 1
    assert postings[0].company_key == "ornl"
    assert postings[0].company_name == "Oak Ridge National Laboratory"
    assert postings[0].source_type == "html"
    assert postings[0].source_job_id == "1394830700"
    assert postings[0].source_url == (
        "https://jobs.ornl.gov/job/"
        "Oak-Ridge-IAM-Linux-Engineer-TN-37830/1394830700/"
    )
    assert postings[0].title == "IAM Linux Engineer"
    assert postings[0].location == "Oak Ridge, TN"
    assert postings[0].canonical_key is not None
    assert postings[0].content_hash is not None


def test_parse_html_jobs_recognizes_talentbrew_data_job_id_links() -> None:
    html = """
    <html><body>
      <a href="/job/denver/platform-engineer/694/98252076128"
         data-job-id="98252076128">Platform Engineer</a>
    </body></html>
    """

    postings = _parse_html_jobs(
        company_config=_company_config(),
        html=html,
        source_url="https://jobs.example.com/search-jobs",
    )

    assert len(postings) == 1
    assert postings[0].source_job_id == "98252076128"
    assert postings[0].title == "Platform Engineer"


def test_html_collector_enforces_required_job_url_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    html = """
        <a class="jobTitle-link" href="/job/Fort-Collins-Robot-CO/101/">Robot</a>
        <a class="jobTitle-link" href="/job/Fort-Loramie-Welder-OH/202/">Welder</a>
    """
    monkeypatch.setattr(
        "job_radar.collectors.html.get_response",
        lambda *_args, **_kwargs: FakeResponse(html),
    )

    config = _company_config()
    config["required_job_url_terms"] = ["/job/fort-collins-"]
    postings = collect_html_jobs(config)

    assert [posting.title for posting in postings] == ["Robot"]


def test_parse_html_jobs_dedupes_desktop_and_mobile_links() -> None:
    html = """
    <html>
      <body>
        <span class="jobTitle hidden-phone">
          <a href="/job/Oak-Ridge-IAM-Linux-Engineer-TN-37830/1394830700/" class="jobTitle-link">IAM Linux Engineer</a>
        </span>
        <span class="jobTitle visible-phone">
          <a class="jobTitle-link" href="/job/Oak-Ridge-IAM-Linux-Engineer-TN-37830/1394830700/">IAM Linux Engineer</a>
        </span>
      </body>
    </html>
    """

    postings = _parse_html_jobs(
        company_config=_company_config(),
        html=html,
        source_url="https://jobs.ornl.gov/go/Computational-SciencesSupercomputing-Jobs/4534300/",
    )

    assert len(postings) == 1


def test_parse_html_jobs_supports_ucsd_result_links() -> None:
    html = """
    <html>
      <body>
        <a
          class="results-list__item-title--link"
          href="https://employment.ucsd.edu/project-manager-dso-140214/job/CC275D737FA5D76C08BA5A3D1B1B6850"
        >
          Project Manager / DSO - 140214
        </a>
      </body>
    </html>
    """

    postings = _parse_html_jobs(
        company_config={
            "company_key": "scripps",
            "name": "Scripps Institution of Oceanography",
            "source_type": "html",
            "source_url": "https://employment.ucsd.edu/jobs?keyword=scripps",
        },
        html=html,
        source_url="https://employment.ucsd.edu/jobs?keyword=scripps",
    )

    assert len(postings) == 1
    assert postings[0].company_key == "scripps"
    assert postings[0].company_name == "Scripps Institution of Oceanography"
    assert postings[0].source_type == "html"
    assert postings[0].source_job_id is None
    assert postings[0].source_url == (
        "https://employment.ucsd.edu/project-manager-dso-140214/job/"
        "CC275D737FA5D76C08BA5A3D1B1B6850"
    )
    assert postings[0].title == "Project Manager / DSO - 140214"
    assert postings[0].location is None
    assert postings[0].canonical_key is not None
    assert postings[0].content_hash is not None


def test_collect_html_jobs_fetches_and_parses(monkeypatch: pytest.MonkeyPatch) -> None:
    html = """
    <html>
      <body>
        <a href="/job/Oak-Ridge-HPC-Linux-Systems-Engineer%2C-Classified-Environment-TN-37830/1393480400/" class="jobTitle-link">HPC Linux Systems Engineer, Classified Environment</a>
      </body>
    </html>
    """
    captured = {}

    def fake_get(
        url: str,
        headers: dict[str, str],
        timeout: int,
    ) -> FakeResponse:
        captured["url"] = url
        captured["headers"] = headers
        captured["timeout"] = timeout
        return FakeResponse(text=html)

    monkeypatch.setattr(requests, "get", fake_get)

    postings = collect_html_jobs(_company_config())

    assert captured["url"] == (
        "https://jobs.ornl.gov/go/Computational-SciencesSupercomputing-Jobs/4534300/"
    )
    assert "User-Agent" in captured["headers"]
    assert captured["timeout"] == 30
    assert len(postings) == 1
    assert postings[0].title == "HPC Linux Systems Engineer, Classified Environment"


def test_collect_html_jobs_wraps_request_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_get(
        url: str,
        headers: dict[str, str],
        timeout: int,
    ) -> FakeResponse:
        raise requests.RequestException("network failed")

    monkeypatch.setattr(requests, "get", fake_get)

    with pytest.raises(CollectorError, match="Failed to fetch HTML postings"):
        collect_html_jobs(_company_config())


def test_parse_html_jobs_supports_mbari_job_opening_links() -> None:
    html = """
    <html>
      <body>
        <a
          class="list-item__link"
          href="/job-opening/marine-operations-technician/"
        >
          Marine Operations Technician MBARI is seeking a Marine Operations Technician
          to ensure that complex marine and subsea systems operate smoothly.
        </a>
      </body>
    </html>
    """

    postings = _parse_html_jobs(
        company_config={
            "company_key": "mbari",
            "name": "MBARI",
            "source_type": "html",
            "source_url": "https://www.mbari.org/about/careers/job-openings/",
        },
        html=html,
        source_url="https://www.mbari.org/about/careers/job-openings/",
    )

    assert len(postings) == 1
    assert postings[0].company_key == "mbari"
    assert postings[0].company_name == "MBARI"
    assert postings[0].source_type == "html"
    assert postings[0].source_job_id is None
    assert postings[0].source_url == (
        "https://www.mbari.org/job-opening/marine-operations-technician/"
    )
    assert postings[0].title == "Marine Operations Technician"
    assert postings[0].location is None
    assert postings[0].canonical_key is not None
    assert postings[0].content_hash is not None


def test_parse_html_jobs_cleans_mbari_job_opening_titles() -> None:
    html = """
    <html>
      <body>
        <a
          class="list-item__link"
          href="/job-opening/elementor-137960/"
        >
          Autonomous Systems Operations Manager The ASO Manager provides operational
          leadership as well as personnel management for the team.
        </a>
      </body>
    </html>
    """

    postings = _parse_html_jobs(
        company_config={
            "company_key": "mbari",
            "name": "MBARI",
            "source_type": "html",
            "source_url": "https://www.mbari.org/about/careers/job-openings/",
        },
        html=html,
        source_url="https://www.mbari.org/about/careers/job-openings/",
    )

    assert len(postings) == 1
    assert postings[0].title == "Autonomous Systems Operations Manager"
    assert postings[0].source_url == "https://www.mbari.org/job-opening/elementor-137960/"


def test_parse_html_jobs_cleans_mbari_title_before_mbari_teaser() -> None:
    html = """
    <html>
      <body>
        <a
          class="list-item__link"
          href="/job-opening/rov-pilot/"
        >
          ROV Pilot MBARI invites candidates to apply for the ROV Pilot/Technician role.
        </a>
      </body>
    </html>
    """

    postings = _parse_html_jobs(
        company_config={
            "company_key": "mbari",
            "name": "MBARI",
            "source_type": "html",
            "source_url": "https://www.mbari.org/about/careers/job-openings/",
        },
        html=html,
        source_url="https://www.mbari.org/about/careers/job-openings/",
    )

    assert len(postings) == 1
    assert postings[0].title == "ROV Pilot"
    assert postings[0].source_url == "https://www.mbari.org/job-opening/rov-pilot/"


def test_parse_html_jobs_cleans_mbari_title_with_normalized_whitespace() -> None:
    html = """
    <html>
      <body>
        <a
          class="list-item__link"
          href="/job-opening/electronic-technician-2/"
        >
          Electronic Technician
          The Monterey Bay Aquarium Research Institute (MBARI) is a nonprofit
          oceanographic research center.
        </a>
      </body>
    </html>
    """

    postings = _parse_html_jobs(
        company_config={
            "company_key": "mbari",
            "name": "MBARI",
            "source_type": "html",
            "source_url": "https://www.mbari.org/about/careers/job-openings/",
        },
        html=html,
        source_url="https://www.mbari.org/about/careers/job-openings/",
    )

    assert len(postings) == 1
    assert postings[0].title == "Electronic Technician"
    assert postings[0].source_url == "https://www.mbari.org/job-opening/electronic-technician-2/"


def test_parse_html_jobs_supports_amentum_job_title_ids() -> None:
    html = """
    <html>
      <body>
        <a
          id="link_job_title_1_0_9"
          href="https://www.amentumcareers.com/jobs/network-system-engineer-ii-arlington-virginia-united-states"
          aria-label="Title: Network/System Engineer II"
        >
          Network/System Engineer II
        </a>
      </body>
    </html>
    """

    postings = _parse_html_jobs(
        company_config={
            "company_key": "amentum",
            "name": "Amentum",
            "source_type": "html",
            "source_url": "https://www.amentumcareers.com/jobs/search",
        },
        html=html,
        source_url="https://www.amentumcareers.com/jobs/search",
    )

    assert len(postings) == 1
    assert postings[0].company_key == "amentum"
    assert postings[0].company_name == "Amentum"
    assert postings[0].source_type == "html"
    assert postings[0].source_job_id is None
    assert postings[0].source_url == (
        "https://www.amentumcareers.com/jobs/"
        "network-system-engineer-ii-arlington-virginia-united-states"
    )
    assert postings[0].title == "Network/System Engineer II"
    assert postings[0].location is None
    assert postings[0].canonical_key is not None
    assert postings[0].content_hash is not None


def test_parse_html_jobs_recognizes_employer_owned_job_cards() -> None:
    html = """
    <a href="/en/jobs/32248/systems-reliability-engineer/"
       class="stretched-link js-view-job">
        Systems Reliability Engineer III - Linux &amp; Virtualization
    </a>
    """

    postings = _parse_html_jobs(
        company_config={
            "company_key": "example",
            "name": "Example",
            "source_type": "html",
        },
        html=html,
        source_url="https://careers.example.com/en/jobs/",
    )

    assert len(postings) == 1
    assert postings[0].title == (
        "Systems Reliability Engineer III - Linux & Virtualization"
    )
    assert postings[0].source_job_id == "32248"
