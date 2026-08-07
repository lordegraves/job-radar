"""Tests public detail enrichment for summary-only recruiting sources."""

from types import SimpleNamespace

from job_radar.collectors.detail_page import enrich_from_public_detail_page
from job_radar.models import JobPosting


def _posting() -> JobPosting:
    return JobPosting(
        company_key="example",
        company_name="Example",
        source_type="icims",
        source_url="https://example.com/jobs/1/job",
        source_job_id="1",
        title="Infrastructure Engineer",
        location=None,
        description=None,
        normalization_state="incomplete",
    )


def test_enrich_from_public_detail_page_prefers_jobposting_json_ld(
    monkeypatch,
) -> None:
    html = """
    <html><head><script type="application/ld+json">
    {"@type":"JobPosting","description":"<h2>Requirements</h2><p>Linux and Kubernetes operations experience required.</p><p>Maintain reliable production infrastructure and incident response systems.</p><p>Work with engineering teams to improve automation, observability, and capacity planning across the platform.</p>","jobLocation":{"address":{"addressLocality":"Denver","addressRegion":"CO","addressCountry":"US"}},"jobLocationType":"TELECOMMUTE"}
    </script></head><body>Navigation text</body></html>
    """
    monkeypatch.setattr(
        "job_radar.collectors.detail_page.get_response",
        lambda *args, **kwargs: SimpleNamespace(text=html),
    )

    result = enrich_from_public_detail_page(_posting())

    assert result.description.startswith("Requirements\nLinux and Kubernetes")
    assert result.location == "Denver, CO, US"
    assert result.remote_status == "TELECOMMUTE"
    assert result.detail_retrieval_state is None


def test_enrich_from_public_detail_page_uses_visible_detail_text(
    monkeypatch,
) -> None:
    html = "<html><body><main><h1>Infrastructure Engineer</h1>" + "".join(
        f"<p>Responsibility {index}: Operate Linux infrastructure, production "
        "services, automation, monitoring, incident response, and capacity "
        "planning.</p>"
        for index in range(4)
    ) + "</main></body></html>"
    monkeypatch.setattr(
        "job_radar.collectors.detail_page.get_response",
        lambda *args, **kwargs: SimpleNamespace(text=html),
    )

    result = enrich_from_public_detail_page(_posting())

    assert "Operate Linux infrastructure" in result.description
    assert result.detail_retrieval_state is None


def test_amentum_retries_empty_accepted_detail_response(monkeypatch) -> None:
    posting = JobPosting(
        **{
            **_posting().__dict__,
            "source_type": "html",
            "source_url": "https://www.amentumcareers.com/jobs/platform-engineer",
        }
    )
    complete_html = "<main>" + (
        "Operate reliable infrastructure, automation, monitoring, incident "
        "response, networking, and capacity planning. " * 4
    ) + "</main>"
    responses = iter(
        [
            SimpleNamespace(text="", content=b"", status_code=202),
            SimpleNamespace(
                text=complete_html,
                content=complete_html.encode("utf-8"),
                status_code=200,
            ),
        ]
    )
    monkeypatch.setattr(
        "job_radar.collectors.detail_page.get_response",
        lambda *args, **kwargs: next(responses),
    )
    monkeypatch.setattr("job_radar.collectors.detail_page.time.sleep", lambda _: None)

    result = enrich_from_public_detail_page(posting)

    assert result.detail_retrieval_state is None
    assert len(result.description or "") >= 200


def test_html_detail_refreshes_changed_slug_from_exact_index_title(monkeypatch) -> None:
    posting = JobPosting(
        **{
            **_posting().__dict__,
            "source_type": "html",
            "source_url": "https://jobs.example/jobs/infrastructure-engineer-old",
        }
    )
    index_url = "https://jobs.example/jobs/search"
    refreshed_url = "https://jobs.example/jobs/infrastructure-engineer-new"
    detail = "".join(
        f"<p>Operate Linux infrastructure, automation, monitoring, incident "
        f"response, networking, and capacity planning responsibility {index}.</p>"
        for index in range(4)
    )
    responses = {
        index_url: SimpleNamespace(
            text=(
                '<a href="/jobs/infrastructure-engineer-new">'
                "Infrastructure Engineer</a>"
            )
        ),
        refreshed_url: SimpleNamespace(text=f"<html><body>{detail}</body></html>"),
    }

    def fake_response(url, **kwargs):
        if url == posting.source_url:
            from job_radar.collectors.greenhouse import CollectorError

            raise CollectorError("safe test failure")
        return responses[url]

    monkeypatch.setattr(
        "job_radar.collectors.detail_page.get_response",
        fake_response,
    )

    result = enrich_from_public_detail_page(
        posting,
        source_api_url=index_url,
    )

    assert "Operate Linux infrastructure" in result.description
    assert result.detail_retrieval_state is None


def test_html_detail_does_not_guess_between_duplicate_exact_titles(monkeypatch) -> None:
    posting = JobPosting(
        **{
            **_posting().__dict__,
            "source_type": "html",
            "source_url": "https://jobs.example/jobs/old",
        }
    )

    def fake_response(url, **kwargs):
        if url == posting.source_url:
            from job_radar.collectors.greenhouse import CollectorError

            raise CollectorError("safe test failure")
        return SimpleNamespace(
            text=(
                '<a href="/jobs/new-1">Infrastructure Engineer</a>'
                '<a href="/jobs/new-2">Infrastructure Engineer</a>'
            )
        )

    monkeypatch.setattr(
        "job_radar.collectors.detail_page.get_response",
        fake_response,
    )

    result = enrich_from_public_detail_page(
        posting,
        source_api_url="https://jobs.example/jobs/search",
    )

    assert result.detail_retrieval_state == "unavailable"


def test_oracle_detail_uses_candidate_experience_resource(monkeypatch) -> None:
    posting = JobPosting(
        company_key="oracle-example",
        company_name="Oracle Example",
        source_type="oracle_hcm",
        source_url=(
            "https://example.fa.oraclecloud.com/hcmUI/CandidateExperience/"
            "en/sites/CX/job/12345"
        ),
        source_job_id="12345",
        title="Linux Systems Engineer",
        location="United States",
        description=None,
        normalization_state="incomplete",
    )
    calls = []

    class OracleResponse:
        def json(self):
            return {
                "ExternalResponsibilitiesStr": (
                    "Operate Linux clusters, automate production infrastructure, "
                    "and lead incident response for reliable services."
                ),
                "ExternalQualificationsStr": (
                    "Required qualifications include Linux administration, "
                    "Python automation, networking, monitoring, and distributed "
                    "systems experience in production environments."
                ),
                "PrimaryLocation": "Fort Collins, Colorado, United States",
                "JobSchedule": "Full time",
                "WorkplaceType": "Hybrid",
            }

    def fake_response(url, **kwargs):
        calls.append((url, kwargs))
        return OracleResponse()

    monkeypatch.setattr(
        "job_radar.collectors.detail_page.get_response",
        fake_response,
    )

    result = enrich_from_public_detail_page(
        posting,
        source_api_url=(
            "https://oracle.example/hcmRestApi/resources/latest/"
            "recruitingCEJobRequisitions"
        ),
    )

    assert calls[0][0].startswith("https://oracle.example/")
    assert calls[0][0].endswith(
        "/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails/12345"
    )
    assert calls[0][1]["params"]["onlyData"] == "true"
    assert "ExternalQualifications" not in calls[0][1]["params"]["expand"]
    assert "Required qualifications" in result.description
    assert "Employment details: Full time" in result.description
    assert result.location == "Fort Collins, Colorado, United States"
    assert result.remote_status == "Hybrid"
    assert result.detail_retrieval_state is None


def test_adp_detail_uses_public_requisition_resource(monkeypatch) -> None:
    posting = JobPosting(
        company_key="adp-example",
        company_name="ADP Example",
        source_type="adp",
        source_url=(
            "https://workforcenow.adp.com/mascsr/default/mdf/recruitment/"
            "recruitment.html?cid=client-id&ccId=center-id&lang=en_US&"
            "jobId=123_1&selectedMenuKey=CurrentOpenings"
        ),
        source_job_id="123_1",
        title="Operations Support Specialist",
        location="Fort Collins, CO, US",
        description=None,
        normalization_state="incomplete",
    )
    calls = []

    class AdpResponse:
        def json(self):
            return {
                "requisitionDescription": (
                    "Required qualifications include experience supporting "
                    "healthcare operations, maintaining clinical records, "
                    "coordinating patient services, following safety procedures, "
                    "and communicating with multidisciplinary care teams."
                )
            }

    def fake_response(url, **kwargs):
        calls.append((url, kwargs))
        return AdpResponse()

    monkeypatch.setattr(
        "job_radar.collectors.detail_page.get_response",
        fake_response,
    )

    result = enrich_from_public_detail_page(posting)

    assert calls[0][0].endswith(
        "/careercenter/public/events/staffing/v1/job-requisitions/123_1"
    )
    assert calls[0][1]["params"] == {
        "cid": "client-id",
        "ccId": "center-id",
        "lang": "en_US",
        "locale": "en_US",
    }
    assert "Required qualifications" in result.description
    assert result.detail_retrieval_state is None
