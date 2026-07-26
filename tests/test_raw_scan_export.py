"""Verify raw scan downloads contain every collected posting in plain text."""

from pathlib import Path
import zipfile

from job_radar.models import JobPosting
from job_radar.raw_scan_export import RAW_SCAN_TEXT_NAME, write_raw_scan_export
from job_radar.report_models import ScanReport


def test_raw_scan_export_contains_every_collected_posting(tmp_path: Path) -> None:
    report = ScanReport(
        companies_enabled=1,
        jobs_collected=2,
        jobs_new=2,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[],
        postings=[
            JobPosting(
                company_key="example",
                company_name="Example Company",
                source_type="generic",
                source_url=f"https://example.invalid/jobs/{index}",
                source_job_id=str(index),
                title=f"Synthetic Role {index}",
                location="Remote",
                salary_text="$100,000 - $120,000",
                description=f"Synthetic description {index}",
            )
            for index in (1, 2)
        ],
        generated_at="2026-07-26T12:00:00+00:00",
    )
    archive_path = tmp_path / "target-scan-raw.zip"

    write_raw_scan_export(archive_path, report)

    with zipfile.ZipFile(archive_path) as archive:
        assert archive.namelist() == [RAW_SCAN_TEXT_NAME]
        content = archive.read(RAW_SCAN_TEXT_NAME).decode("utf-8")
    assert "Jobs collected: 2" in content
    assert "Synthetic Role 1" in content
    assert "Synthetic description 1" in content
    assert "Synthetic Role 2" in content
    assert "Synthetic description 2" in content
