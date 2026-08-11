"""Tests marker-based pagination for older generic HTML sources."""

from job_radar.collectors.adaptive_html import collect_adaptive_html_jobs
from job_radar.models import JobPosting


def _config():
    return {
        "company_key": "synthetic",
        "name": "Synthetic",
        "source_type": "html",
        "source_url": "https://jobs.example.com/search?q=engineer",
    }


def _posting(job_id: str) -> JobPosting:
    return JobPosting(
        company_key="synthetic",
        company_name="Synthetic",
        source_type="html",
        source_job_id=job_id,
        source_url=f"https://jobs.example.com/job/{job_id}",
        title=f"Engineer {job_id}",
        location="Remote",
        description=None,
    )


def test_generic_source_stops_when_no_numbered_page_is_advertised(monkeypatch) -> None:
    monkeypatch.setattr(
        "job_radar.collectors.adaptive_html.collect_html_jobs_document",
        lambda config, url: ("<html>ordinary careers page</html>", [_posting("1")]),
    )

    assert len(collect_adaptive_html_jobs(_config())) == 1


def test_generic_source_follows_advertised_numbered_pages(monkeypatch) -> None:
    requested = []

    def fake_document(config, url):
        del config
        requested.append(url)
        if "page=2" in url:
            return ("<html>No later page</html>", [_posting("3")])
        return (
            "<a href='?q=engineer&amp;page=2#results'>Next</a>"
            "<a href='?q=engineer&amp;page=3#results'>3</a>",
            [_posting("1"), _posting("2")],
        )

    monkeypatch.setattr(
        "job_radar.collectors.adaptive_html.collect_html_jobs_document",
        fake_document,
    )

    postings = collect_adaptive_html_jobs(_config())

    assert [posting.source_job_id for posting in postings] == ["1", "2", "3"]
    assert requested == [
        "https://jobs.example.com/search?q=engineer",
        "https://jobs.example.com/search?q=engineer&page=2",
    ]


def test_generic_source_follows_advertised_start_offsets(monkeypatch) -> None:
    requested = []
    config = _config()
    config["source_url"] = "https://jobs.example.com/positions/"

    def fake_document(config, url):
        del config
        requested.append(url)
        if "start=36" in url:
            return ("<html>No later offset</html>", [_posting("3")])
        return (
            "<button data-url='/positions/?start=36'>Load more</button>",
            [_posting("1"), _posting("2")],
        )

    monkeypatch.setattr(
        "job_radar.collectors.adaptive_html.collect_html_jobs_document",
        fake_document,
    )

    postings = collect_adaptive_html_jobs(config)

    assert [posting.source_job_id for posting in postings] == ["1", "2", "3"]
    assert requested == [
        "https://jobs.example.com/positions/",
        "https://jobs.example.com/positions/?start=36",
    ]


def test_older_talentbrew_html_configuration_uses_p_pages(monkeypatch) -> None:
    monkeypatch.setattr(
        "job_radar.collectors.adaptive_html.collect_html_jobs_document",
        lambda config, url: (
            "<script src='tbcdn.talentbrew.com'></script>",
            [_posting("1")],
        ),
    )

    monkeypatch.setattr(
        "job_radar.collectors.adaptive_html.collect_talentbrew_jobs",
        lambda config: [_posting("1"), _posting("2")],
    )

    postings = collect_adaptive_html_jobs(_config())

    assert [posting.source_job_id for posting in postings] == ["1", "2"]


def test_successfactors_html_configuration_uses_startrow(monkeypatch) -> None:
    requested = []

    def fake_document(config, url):
        del config
        requested.append(url)
        if "startrow=25" in url:
            return ("<html>No more pages</html>", [_posting("3")])
        return (
            "<meta name='generator' content='SAP SuccessFactors'>"
            "<a href='?q=engineer&amp;startrow=25'>Next</a>",
            [_posting("1"), _posting("2")],
        )

    monkeypatch.setattr(
        "job_radar.collectors.adaptive_html.collect_html_jobs_document",
        fake_document,
    )

    postings = collect_adaptive_html_jobs(_config())

    assert [posting.source_job_id for posting in postings] == ["1", "2", "3"]
    assert requested == [
        "https://jobs.example.com/search?q=engineer",
        "https://jobs.example.com/search?q=engineer&startrow=25",
    ]
