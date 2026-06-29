# Job Radar

Job Radar is a local job discovery and triage tool.

It scans configured company job boards, normalizes postings, stores them in SQLite, scores them against configurable preferences, and writes Markdown, HTML, and email-preview reports.

The current goal is not to apply to jobs automatically. The goal is to safely collect and rank roles from known target companies so manual review is faster and less dependent on stale job boards, stale LinkedIn results, or missed company postings.

## Current capabilities

- Scans configured company sources
- Supports Greenhouse collectors
- Supports Lever collectors
- Supports Ashby collectors
- Supports Workday collectors
- Supports USAJobs collectors
- Supports iCIMS collectors
- Supports Jibe collectors
- Supports Jobsyn collectors
- Supports Oracle HCM collectors
- Supports SmartRecruiters collectors
- Supports SelectMinds collectors
- Supports Phenom collectors
- Supports Dayforce collectors
- Supports ADP Workforce Now collectors
- Supports HTML job-link collectors
- Stores job postings in SQLite
- Tracks new, seen, and changed postings
- Scores jobs using configurable keyword and location rules
- Classifies location status
- Uses config-driven eligibility rules for Top Matches and Review Needed
- Separates Top Matches, Review Needed, Northern Colorado Highlights, and All Jobs
- Keeps All Jobs complete even when Top Matches and Review Needed are filtered
- Keeps the full Markdown and HTML reports complete for Top Matches
- Keeps email summaries intentionally capped for readability
- Generates a Markdown report
- Generates an HTML report
- Builds a plain-text email preview during scan
- Summarizes scanned companies
- Summarizes source type counts
- Summarizes location status counts
- Adds a generated timestamp to each report
- Keeps generated email preview files out of git
- Validates email settings without sending email
- Wires the email send path behind an explicit --send-email flag
- Keeps SMTP delivery disabled until enabled intentionally
- Requires email passwords to come from environment variables when email is enabled

## Current live target sources

The primary live scan config is:

    config/target-companies.yaml

The live settings file is:

    config/live-test-settings.yaml

Current implemented source types:

- Greenhouse
- Lever
- Ashby
- Workday
- USAJobs
- iCIMS
- Jibe
- Jobsyn
- Oracle HCM
- SmartRecruiters
- SelectMinds
- Phenom
- Dayforce
- ADP Workforce Now
- Activate
- WEKA custom
- HTML

Current verified live scan state:

    Companies enabled: 62
    Jobs collected: 10,000
    Jobs stored: 150
    Jobs omitted: 9,850
    Collector errors: 0

Recently validated source additions:

- Oak Ridge National Laboratory - HTML
- Sandia National Laboratories - Jobsyn
- SAIC - Oracle HCM
- Lawrence Livermore National Laboratory - SmartRecruiters
- Berkeley Lab / NERSC - SelectMinds
- Battelle - Phenom
- ASRC Federal - Dayforce
- USRA - ADP Workforce Now
- Idaho National Laboratory - SelectMinds
- Nscale - Greenhouse
- Dell Technologies - Oracle HCM
- DDN - iCIMS
- Ocean Infinity - Workday
- Saildrone - Greenhouse
- Penguin Solutions - HTML
- Cherokee Federal - Oracle HCM
- Fugro - Workday
- Scripps Institution of Oceanography - HTML
- MBARI - HTML
- Los Alamos National Laboratory - Activate
- Amentum - HTML
- WEKA - custom
- Pacific Northwest National Laboratory - Jibe
- Voleon - Ashby
- Jacobs - Jobsyn/NLX

## Important config files

    config/target-companies.yaml

Primary target company configuration.

    config/live-test-settings.yaml

Settings used for live validation, including the live test database path and email settings.

    config/scoring.yaml

Keyword scoring, location preferences, Top Match rules, and Review Needed rules.

    config/companies.yaml

Sample/demo company configuration. These entries are placeholders.

## Run tests

    python -m pytest

Expected current result:

    191 passed

## Report structure

The Markdown and HTML reports include these major sections:

### Top Matches

Best clean matches based on score, location, excluded title filters, and strong technical signals.

The full Markdown and HTML reports show all Top Match eligible jobs.

### Top Matches Quick View

A capped summary view of the strongest Top Matches for fast scanning.

### Review Needed

High-score roles that are not clean Top Matches but may still deserve manual review.

### Northern Colorado Highlights

Location-focused section for Northern Colorado and nearby strategic locations.

This section avoids duplicating jobs already shown in full Top Matches.

### All Jobs

Complete scored archive of collected jobs. This section stays complete even when Top Matches and Review Needed are filtered.

## Run full live scan

    python -m job_radar scan --config config/target-companies.yaml --settings config/live-test-settings.yaml --report reports/target-scan.md --email-preview reports/target-email-preview.txt --send-email

Expected good output:

    Collector errors: 0
    Report written: reports\target-scan.md
    HTML report written: reports\target-scan.html
    Email preview written: reports\target-email-preview.txt
    Email send result: Email sending disabled by settings

## Run live validation with email preview

    Remove-Item data\live_test.sqlite3 -ErrorAction SilentlyContinue
    Remove-Item reports\target-email-preview.txt -ErrorAction SilentlyContinue

    python -m job_radar scan --config config/target-companies.yaml --settings config/live-test-settings.yaml --report reports/target-scan.md --email-preview reports/target-email-preview.txt

    Get-Content reports\target-email-preview.txt -Raw

Email settings are validated from the settings file. With email.enabled set to false, --send-email only exercises the guarded send path and prints that email sending is disabled. No SMTP connection is made and no email is sent.

    python -m job_radar scan --config config/target-companies.yaml --settings config/live-test-settings.yaml --report reports/target-scan.md --email-preview reports\target-email-preview.txt --send-email

With email.enabled set to false, --send-email only exercises the guarded send path and prints that email sending is disabled.

## Email secret handling

Email passwords must not be stored in YAML files.

When email sending is enabled, the settings file should name an environment variable that contains the SMTP password:

    email:
      enabled: true
      sender: "you@example.com"
      recipients:
        - "you@example.com"
      smtp_host: "smtp.example.com"
      smtp_port: 587
      smtp_password_env: "JOB_RADAR_SMTP_PASSWORD"

For local testing, that environment variable can be set in the shell.

For k3s, that environment variable should come from a Kubernetes Secret.

If email.enabled is true and the configured password environment variable is missing, Job Radar fails cleanly before attempting to send email.

## Project principles

- Configured-company scanning only
- No broad crawling
- No automatic job applications
- No contacting employers
- Local SQLite system of record
- Rules-based scoring before LLM integration
- Safe manual review first
