"""Tests SelectMinds HTML parsing, normalized postings, and failures."""

from __future__ import annotations

import pytest
import requests

from job_radar.collectors.greenhouse import CollectorError
from job_radar.collectors.incremental_cache import DETAIL_PLANNER_CONFIG_KEY
from job_radar.collectors.selectminds import collect_selectminds_jobs
from job_radar.detail_retrieval import DetailRetrievalDecision


class FakeResponse:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


def _config():
    return {
        "company_key": "berkeley_lab_nersc",
        "name": "Berkeley Lab / NERSC",
        "source_type": "selectminds",
        "source_url": "https://lbl.referrals.selectminds.com/page/nersc-careers-85",
    }


def test_collect_selectminds_jobs_builds_posting(monkeypatch):
    listing_html = """
    <p><a href="https://lbl.referrals.selectminds.com/jobs/hpc-scientific-support-engineer-7496" class="job_link font_bold">HPC Scientific Support Engineer</a></p>
    <p class="jlr_description">Support NERSC users and HPC workloads.</p>
    <p class="jlr_preferred_field job_external_id">
      <span class="jlr_value font_bold job_external_id">
        <span class="field_value">106834</span>
        <span class="field_label">Requisition #</span>
      </span>
      <span class="jlr_value font_bold job_post_date">
        <span class="field_value">Jun 03, 2026</span>
        <span class="field_label">Post Date</span>
      </span>
    </p>
    <a href="https://lbl.referrals.selectminds.com/jobs/hpc-scientific-support-engineer-7496" class="learn_more_btn">Learn More</a>
    """
    detail_html = """
    <script type="application/ld+json">
    {
      "@context": "https://schema.org",
      "@type": "JobPosting",
      "employmentType": "FULL_TIME",
      "jobLocation": {
        "@type": "Place",
        "address": {
          "@type": "PostalAddress",
          "addressLocality": "Bay Area",
          "addressRegion": "California",
          "addressCountry": "US"
        }
      },
      "description": "<h2>Minimum Qualifications</h2><p>Experience supporting scientific users and debugging HPC applications. Strong Fortran, MPI, and OpenMP experience is required.</p><p>This position may be on-site, hybrid, or full-time telework.</p>"
    }
    </script>
    """

    def fake_get(url, headers, timeout):
        assert headers["Accept"].startswith("text/html")
        assert timeout == 30
        if url == "https://lbl.referrals.selectminds.com/page/nersc-careers-85":
            return FakeResponse(listing_html)
        assert url == (
            "https://lbl.referrals.selectminds.com/jobs/"
            "hpc-scientific-support-engineer-7496"
        )
        return FakeResponse(detail_html)

    monkeypatch.setattr(requests, "get", fake_get)

    jobs = collect_selectminds_jobs(_config())

    assert len(jobs) == 1
    assert jobs[0].company_key == "berkeley_lab_nersc"
    assert jobs[0].company_name == "Berkeley Lab / NERSC"
    assert jobs[0].source_type == "selectminds"
    assert jobs[0].title == "HPC Scientific Support Engineer"
    assert jobs[0].source_job_id == "106834"
    assert jobs[0].source_url == (
        "https://lbl.referrals.selectminds.com/jobs/"
        "hpc-scientific-support-engineer-7496"
    )
    assert "Minimum Qualifications" in jobs[0].description
    assert "full-time telework" in jobs[0].description
    assert "Employment type: FULL_TIME" in jobs[0].description
    assert jobs[0].location == "Bay Area, California, US"
    assert "Post Date: Jun 03, 2026" in jobs[0].description
    assert jobs[0].canonical_key
    assert jobs[0].content_hash


def test_collect_selectminds_jobs_deduplicates(monkeypatch):
    html = """
    <p><a href="/jobs/hpc-ai-performance-specialist-7475" class="job_link font_bold">HPC/AI Performance Specialist</a></p>
    <span class="field_value">106607</span><span class="field_label">Requisition #</span>
    <p><a href="/jobs/hpc-ai-performance-specialist-7475" class="job_link font_bold">HPC/AI Performance Specialist</a></p>
    <span class="field_value">106607</span><span class="field_label">Requisition #</span>
    """

    def fake_get(url, headers, timeout):
        return FakeResponse(html)

    monkeypatch.setattr(requests, "get", fake_get)

    jobs = collect_selectminds_jobs(_config())

    assert len(jobs) == 1
    assert jobs[0].source_job_id == "106607"


def test_collect_selectminds_jobs_skips_missing_title(monkeypatch):
    html = """
    <p><a href="/jobs/broken-1" class="job_link font_bold"></a></p>
    <span class="field_value">123</span><span class="field_label">Requisition #</span>
    """

    def fake_get(url, headers, timeout):
        return FakeResponse(html)

    monkeypatch.setattr(requests, "get", fake_get)

    jobs = collect_selectminds_jobs(_config())

    assert jobs == []


def test_collect_selectminds_jobs_uses_url_job_id_fallback(monkeypatch):
    html = """
    <p><a href="/jobs/regulatory-development-and-support-engineer-10671" class="job_link font_bold">Regulatory Development and Support Engineer</a></p>
    <p class="jlr_description">Support regulatory development.</p>
    """

    def fake_get(url, headers, timeout):
        return FakeResponse(html)

    monkeypatch.setattr(requests, "get", fake_get)

    jobs = collect_selectminds_jobs(_config())

    assert len(jobs) == 1
    assert jobs[0].source_job_id == "10671"


def test_collect_selectminds_jobs_wraps_request_errors(monkeypatch):
    def fake_get(url, headers, timeout):
        raise requests.RequestException("boom")

    monkeypatch.setattr(requests, "get", fake_get)

    with pytest.raises(CollectorError, match="SelectMinds request failed"):
        collect_selectminds_jobs(_config())


def test_collect_selectminds_jobs_skips_clearly_unrelated_detail(monkeypatch):
    listing_html = """
    <p><a href="/jobs/senior-tax-accountant-1234" class="job_link font_bold">Senior Tax Accountant</a></p>
    <p class="jlr_description">Prepare corporate tax filings.</p>
    """
    requested_urls = []

    def fake_get(url, headers, timeout):
        requested_urls.append(url)
        return FakeResponse(listing_html)

    monkeypatch.setattr(requests, "get", fake_get)
    config = _config()
    config[DETAIL_PLANNER_CONFIG_KEY] = lambda title, location: (
        DetailRetrievalDecision(False, "clearly unrelated")
    )

    jobs = collect_selectminds_jobs(config)

    assert requested_urls == [config["source_url"]]
    assert len(jobs) == 1
    assert jobs[0].detail_retrieval_reason == "clearly unrelated"
    assert jobs[0].detail_retrieval_state == "skipped_unrelated"


def test_collect_selectminds_jobs_reads_real_detail_container_shape(monkeypatch):
    listing_html = """
    <a href="/jobs/platform-engineer-7491" class="job_link">Platform Engineer</a>
    <p class="jlr_description">Help operate HPC systems.</p>
    """
    detail_html = """
    <h4 class="primary_location">🔍 Bay Area, California, United States</h4>
    <div id="description_box" class="main_content_box">
      <p>Build and manage Linux and HPC infrastructure.</p>
      <p>Work modality: This position requires substantial on-site presence,
      but hybrid schedules may be considered. Hybrid work includes work
      on-site at Lawrence Berkeley National Lab in Berkeley, California.</p>
    </div>
    """

    def fake_get(url, headers, timeout):
        if url == _config()["source_url"]:
            return FakeResponse(listing_html)
        return FakeResponse(detail_html)

    monkeypatch.setattr(requests, "get", fake_get)

    jobs = collect_selectminds_jobs(_config())

    assert len(jobs) == 1
    assert jobs[0].location == "Bay Area, California, United States"
    assert "requires substantial on-site presence" in jobs[0].description
