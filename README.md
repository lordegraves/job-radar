# Job Radar

Job Radar is a local job discovery and triage tool.

It scans configured company job boards, normalizes postings, stores them in SQLite, scores them against configurable preferences, and writes a Markdown report.

The current goal is not to apply to jobs automatically. The goal is to safely collect and rank roles from known target companies so manual review is faster and less dependent on stale job boards or missing LinkedIn results.

## Current capabilities

- Scans configured company sources
- Supports Greenhouse collectors
- Supports Lever collectors
- Stores job postings in SQLite
- Tracks new, seen, and changed postings
- Scores jobs using configurable keyword and location rules
- Separates Top Matches from All Jobs
- Keeps All Jobs complete even when Top Matches are filtered
- Generates a Markdown report
- Summarizes scanned companies
- Summarizes location status counts

## Current live validation sources

The live validation config is:

```text
config/live-test-companies.yaml
