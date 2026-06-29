import pytest
import requests

from job_radar.collectors.greenhouse import CollectorError
from job_radar.collectors.weka import _parse_weka_jobs, collect_weka_jobs


def test_parse_weka_jobs_returns_job_postings() -> None:
    html = """
    <html>
      <body>
        <div
          class="col-sm-6 col-md-6 col-lg-4 block-tier mrkto-job"
          data-departments="RD"
          data-location="USRemote"
          data-offices="4027732007"
        >
          <div class="tile-item">
            <div class="tile-content">
              <div class="content-wrap">
                <a href="?gh_jid=5085240007"></a>
                <h3>Tech Lead - AI Inference - U.S. Remote</h3>
                <div class="location">U.S. Remote</div>
              </div>
              <div class="cta-box">
                <a href="?gh_jid=5085240007#career-position" class="cbtn wk-primary">
                  Read More
                </a>
              </div>
            </div>
          </div>
        </div>
      </body>
    </html>
    """

    postings = _parse_weka_jobs(
        company_config={
            "company_key": "weka",
            "name": "WEKA",
            "source_type": "weka",
            "source_url": "https://www.weka.io/company/careers/",
        },
        html=html,
        source_url="https://www.weka.io/company/careers/",
    )

    assert len(postings) == 1
    assert postings[0].company_key == "weka"
    assert postings[0].company_name == "WEKA"
    assert postings[0].source_type == "weka"
    assert postings[0].source_job_id == "5085240007"
    assert postings[0].source_url == (
        "https://www.weka.io/company/careers/?gh_jid=5085240007#career-position"
    )
    assert postings[0].title == "Tech Lead - AI Inference - U.S. Remote"
    assert postings[0].location == "U.S. Remote"
    assert postings[0].description == "RD"
    assert postings[0].canonical_key is not None
    assert postings[0].content_hash is not None


def test_parse_weka_jobs_deduplicates_by_source_job_id() -> None:
    html = """
    <div class="block-tier mrkto-job" data-departments="RD">
      <div class="content-wrap">
        <a href="?gh_jid=5085240007"></a>
        <h3>Tech Lead - AI Inference - U.S. Remote</h3>
        <div class="location">U.S. Remote</div>
      </div>
      <div class="cta-box"></div>
    </div>

    <div class="block-tier mrkto-job" data-departments="RD">
      <div class="content-wrap">
        <a href="?gh_jid=5085240007"></a>
        <h3>Tech Lead - AI Inference - U.S. Remote</h3>
        <div class="location">U.S. Remote</div>
      </div>
      <div class="cta-box"></div>
    </div>
    """

    postings = _parse_weka_jobs(
        company_config={
            "company_key": "weka",
            "name": "WEKA",
            "source_type": "weka",
            "source_url": "https://www.weka.io/company/careers/",
        },
        html=html,
        source_url="https://www.weka.io/company/careers/",
    )

    assert len(postings) == 1


def test_collect_weka_jobs_wraps_request_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def mock_get(*args: object, **kwargs: object) -> requests.Response:
        raise requests.RequestException("network failed")

    monkeypatch.setattr("job_radar.collectors.weka.requests.get", mock_get)

    with pytest.raises(CollectorError, match="Failed to fetch WEKA careers page"):
        collect_weka_jobs(
            {
                "company_key": "weka",
                "name": "WEKA",
                "source_type": "weka",
                "source_url": "https://www.weka.io/company/careers/",
            }
        )