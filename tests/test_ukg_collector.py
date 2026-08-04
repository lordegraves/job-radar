"""Verify UKG Pro public boards become complete normalized job postings."""

import json
from typing import Any

from job_radar.collectors.ukg import _workplace_status, collect_ukg_jobs


class FakeResponse:
    def __init__(self, *, text: str = "", payload: Any = None) -> None:
        self.text = text
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self._payload


class FakeSession:
    def __init__(self) -> None:
        self.post_payloads: list[dict[str, Any]] = []

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        if "OpportunityDetail" not in url:
            return FakeResponse(
                text=(
                    '<input name="__RequestVerificationToken" '
                    'type="hidden" value="synthetic-token">'
                )
            )
        detail = {
            "Id": "opportunity-123",
            "Title": "Synthetic Infrastructure Engineer",
            "Description": "<p>Operate reliable Linux systems.</p>",
            "Locations": [
                {
                    "Address": {
                        "City": "Fort Collins",
                        "State": {"Code": "CO"},
                        "Country": {"Code": "USA"},
                    }
                }
            ],
            "PayRange": {
                "PayRangeMinimum": 150000,
                "PayRangeMaximum": 190000,
            },
            "PayRangeCurrencyCode": "USD",
        }
        return FakeResponse(
            text=(
                "var opportunity = new "
                "US.Opportunity.CandidateOpportunityDetail("
                f"{json.dumps(detail)}"
                ");"
            )
        )

    def post(
        self,
        url: str,
        *,
        json: dict[str, Any],
        **kwargs: Any,
    ) -> FakeResponse:
        self.post_payloads.append(json)
        return FakeResponse(
            payload={
                "opportunities": [
                    {
                        "Id": "opportunity-123",
                        "Title": "Synthetic Infrastructure Engineer",
                        "JobLocationType": "Hybrid",
                    }
                ],
                "totalCount": 1,
            }
        )


def test_collect_ukg_jobs_uses_public_board_and_detail_data(
    monkeypatch,
) -> None:
    fake_session = FakeSession()
    monkeypatch.setattr(
        "job_radar.collectors.ukg.requests.Session",
        lambda: fake_session,
    )

    jobs = collect_ukg_jobs(
        {
            "company_key": "synthetic-company",
            "name": "Synthetic Company",
            "source_type": "ukg",
            "source_url": (
                "https://recruiting.ultipro.com/TENANT/JobBoard/"
                "board-id/"
            ),
        }
    )

    assert len(jobs) == 1
    job = jobs[0]
    assert job.source_type == "ukg"
    assert job.source_job_id == "opportunity-123"
    assert job.title == "Synthetic Infrastructure Engineer"
    assert job.location == "Fort Collins, CO, USA"
    assert job.description == "Operate reliable Linux systems."
    assert job.remote_status == "Hybrid"
    assert job.salary_text == "150000 - 190000 USD"
    assert job.canonical_key
    assert job.content_hash
    assert fake_session.post_payloads[0]["opportunitySearch"]["Top"] == 50
    assert fake_session.post_payloads[0]["opportunitySearch"]["Skip"] == 0


def test_ukg_numeric_workplace_codes_are_translated_conservatively() -> None:
    assert _workplace_status(0) is None
    assert _workplace_status("1") == "On-site"
    assert _workplace_status(2) == "Remote"
    assert _workplace_status("Hybrid") == "Hybrid"
