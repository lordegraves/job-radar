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
- Separates Top Matches, Review Needed, and All Jobs
- Uses config-driven eligibility rules for Top Matches and Review Needed
- Keeps All Jobs complete even when Top Matches and Review Needed are filtered
- Generates a Markdown report
- Summarizes scanned companies
- Summarizes location status counts
- Adds a generated timestamp to each report
- Summarizes source type counts
- Builds a plain-text email preview during scan
- Keeps generated email preview files out of git
- Validates email settings without sending email

## Current live validation sources

The live validation config is:

```text
config/live-test-companies.yaml
```

Current live validation sources:

- Anthropic - Greenhouse
- Scale AI - Greenhouse
- Distro - Lever

## Important config files

```text
config/companies.yaml
```

Sample/demo company configuration. These entries are placeholders.

```text
config/live-test-companies.yaml
```

Real live validation company configuration.

```text
config/live-test-settings.yaml
```

Settings used for live validation, including the live test database path.

```text
config/scoring.yaml
```

Keyword scoring, location preferences, Top Match rules, and Review Needed rules.

## Run tests

```powershell
python -m pytest
```

Expected current result:

```text
86 passed
```

## Report structure

The Markdown report has three job sections:

### Top Matches

Best clean matches based on score, location, excluded title filters, and strong technical signals.

### Review Needed

High-score roles that are not clean Top Matches but may still deserve manual review.

### All Jobs

Complete scored archive of collected jobs. This section stays complete even when Top Matches and Review Needed are filtered.

## Run live validation

```powershell
Remove-Item data\live_test.sqlite3 -ErrorAction SilentlyContinue

python -m job_radar scan --config config/live-test-companies.yaml --settings config/live-test-settings.yaml --report reports/live-test.md
```

Expected good output:

```text
Companies enabled: 3
Collector errors: 0
```
## Run live validation with email preview

```powershell
Remove-Item data\live_test.sqlite3 -ErrorAction SilentlyContinue
Remove-Item reports\live-email-preview.txt -ErrorAction SilentlyContinue

python -m job_radar scan --config config/live-test-companies.yaml --settings config/live-test-settings.yaml --report reports/live-test.md --email-preview reports/live-email-preview.txt

Get-Content reports\live-email-preview.txt -Raw
```

Email settings are validated from the settings file, but this command still only writes a local preview file and does not send email.

## Project principles

- Configured-company scanning only
- No broad crawling
- No automatic job applications
- No contacting employers
- Local SQLite system of record
- Rules-based scoring before LLM integration
- Safe manual review first