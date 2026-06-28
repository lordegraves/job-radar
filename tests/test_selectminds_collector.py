from __future__ import annotations

import pytest
import requests

from job_radar.collectors.greenhouse import CollectorError
from job_radar.collectors.selectminds import collect_selectminds_jobs


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
    html = """
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

    def fake_get(url, headers, timeout):
        assert url == "https://lbl.referrals.selectminds.com/page/nersc-careers-85"
        assert headers["Accept"].startswith("text/html")
        assert timeout == 30
        return FakeResponse(html)

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
    assert "Support NERSC users and HPC workloads." in jobs[0].description
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


def test_collect_selectminds_jobs_wraps_request_errors(monkeypatch):
    def fake_get(url, headers, timeout):
        raise requests.RequestException("boom")

    monkeypatch.setattr(requests, "get", fake_get)

    with pytest.raises(CollectorError, match="SelectMinds request failed"):
        collect_selectminds_jobs(_config())