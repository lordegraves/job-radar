# Job Radar

Job Radar is a local job discovery, triage, and application-tracking tool.

It scans configured company job boards, normalizes postings, stores them in SQLite, scores them against configurable preferences, imports application/history data, and provides reports plus a local tracker GUI.

The current goal is not to apply to jobs automatically. The goal is to safely collect, rank, and track roles from known target companies so manual review is faster and less dependent on stale job boards, stale LinkedIn results, or missed company postings.

Job Radar does not contact employers. It does not scrape LinkedIn. It does not broadly crawl the internet.

## Product direction

Job Radar started as a personal job discovery and application-tracking tool. The long-term direction is a configurable local-first application that another user can install, configure, and use without editing source code.

The finish line is defined in:

```text
docs/product-roadmap.md
```

Complete-enough means a user can install Job Radar, configure their own companies, preferences, salary expectations, locations, role targets, scan schedule, and reporting preferences, then run scans and track applications through the GUI.

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
- Supports Activate collectors
- Supports WEKA custom collectors
- Supports Rippling collectors
- Supports SchoolSpring collectors
- Supports HTML job-link collectors
- Stores job postings in SQLite
- Tracks new, seen, and changed postings
- Scores jobs using configurable keyword, location, compensation, and fit rules
- Classifies location status
- Uses config-driven eligibility rules for Top Matches and Review Needed
- Separates Top Matches, Review Needed, Northern Colorado Highlights, Track Status, and Passed / Not Recommended
- Keeps Passed / Not Recommended audit details available when Top Matches and Review Needed are filtered
- Keeps the full Markdown and HTML reports complete for review
- Keeps email summaries intentionally capped for readability
- Generates a Markdown report
- Generates an HTML report
- Builds plain-text and HTML email previews during scan
- Summarizes scanned companies
- Summarizes source type counts
- Summarizes location status counts
- Adds a generated timestamp to each report
- Keeps generated reports and email preview files out of git
- Validates email settings without sending email
- Wires the email send path behind an explicit `--send-email` flag
- Keeps SMTP delivery disabled until enabled intentionally
- Requires email passwords to come from environment variables when email is enabled
- Imports job/application history from a tracking workbook
- Supports the simplified Job Log spreadsheet format
- Generates stable Job Radar IDs for scanned postings
- Shows Job Radar IDs in Markdown, HTML, and email-preview reports
- Treats Job Radar ID as the preferred history identity when present
- Matches imported history by exact Job Radar ID before falling back to guarded company/title similarity
- Imports tracker-worthy history rows into the application tracker
- Shows Track Status in reports only when a scanned job already has an application tracker record
- Routes fuzzy history matches to Track Status only when the title match is strong enough
- Allows manual/external leads without requiring ATS Platform, Import Key, or blocker/risk fields
- Provides an application tracker CLI
- Provides a local Flask GUI for tracker review/update workflows, imported history/archive review, existing report viewing, and controlled manual scan execution
- Supports tracker search, workflow filters, raw status filters, raw outcome filters, and sorting by workflow, applied date, company, role, status, and outcome
- Supports history/archive search, decision filters, outcome filters, and sorting by date, company, role, decision/status, and outcome

## Current live target sources

The primary live scan config is:

```text
config/target-companies.yaml
```

The main settings file is:

```text
config/settings.yaml
```

The live-test settings file remains available for sandbox validation:

```text
config/live-test-settings.yaml
```

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
- Rippling
- SchoolSpring
- HTML

Current verified live scan state from the last documented full live scan:

```text
Companies enabled: 62
Jobs collected: 10,000
Jobs stored: 150
Jobs omitted: 9,850
Collector errors: 0
```

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

```text
config/target-companies.yaml
```

Primary target company configuration.

```text
config/settings.yaml
```

Main settings used for normal local GUI and app runs.

```text
config/live-test-settings.yaml
```

Settings used for sandbox/live-test validation when needed.

```text
config/scoring.yaml
```

Keyword scoring, location preferences, Top Match rules, and Review Needed rules.

```text
config/demo-companies.yaml
```

Sample/demo company configuration. These entries are placeholders.

## Job history import

Job Radar can import application and review history from a local Excel workbook.

A sanitized example workbook is included at:

```text
examples/job-history-template.xlsx
```

The example workbook contains the simplified Job Log headers, formatting, validation lists, and one fake sample row. It must not contain real application history.

The current simplified Job Log format uses these columns:

```text
Job Radar ID
Date
Company
Role
Posting URL
Lead Source
Decision
Outcome
Recruiter/Contact
Notes
Include In Job Radar
```

The simplified workbook is treated as a human job log and import bridge, not as the app's internal schema.

Job Radar owns source/ATS details, scoring, blockers, risks, matching, report placement, and app-native tracker state. The workbook records what happened, what was decided, where the lead came from, and any human notes.

Job Radar ID is generated for scanned postings and shown in Markdown, HTML, and email-preview reports. It is used as the preferred durable history key when present.

Rows without a Job Radar ID are still allowed for LinkedIn, referral, recruiter, company-site, and other manual leads. Posting URL is used as fallback evidence when available.

Exact Job Radar ID matches can provide history context. Existing application tracker records are attached during scan/report generation so reports show Track Status only for jobs already tracked in `application_tracker`.

Fuzzy company/title matches are guarded so broad title overlap can provide history context without automatically treating a role as already applied.

Job Radar reads the workbook during manual history import. The workbook remains a transition bridge for existing history and bulk intake, but it is being retired as the normal application-tracking interface.

Job Radar does not write IDs or enrichment data back to the workbook.

Import history manually:

```powershell
python -m job_radar history import --workbook data/job-history.xlsx --settings config/settings.yaml
```

Legacy command still supported:

```powershell
python -m job_radar import-history --workbook data/job-history.xlsx --settings config/settings.yaml
```

Summarize imported history:

```powershell
python -m job_radar history summary --settings config/settings.yaml
```

Legacy command still supported:

```powershell
python -m job_radar history-summary --settings config/settings.yaml
```

## Application tracker

Job Radar has an app-native application tracker backed by SQLite.

The tracker stores:

- Job Radar ID
- Company
- Role
- Source URL
- Status
- Follow-up date
- Applied date
- Last activity date
- Outcome
- Notes
- Created/updated timestamps

The tracker classifies application workflow state, including:

- `follow_up_due`
- `needs_date_review`
- `active_pipeline`
- `follow_up_scheduled`
- `waiting`
- `dormant`
- `stale`
- `presumed_closed`
- `closed`

The tracker is the long-term direction for active application workflow. Spreadsheet import remains available as a bridge and bulk-import path, but the spreadsheet is being retired as the normal application-tracking interface.

Passed/reviewed jobs are imported into job history. They are not automatically added to the active application tracker.

List tracker records:

```powershell
python -m job_radar tracker list --settings config/settings.yaml
```

List records needing action:

```powershell
python -m job_radar tracker list --needs-action --settings config/settings.yaml
```

List records needing review:

```powershell
python -m job_radar tracker list --needs-review --settings config/settings.yaml
```

Add a manual tracker record:

```powershell
python -m job_radar tracker add --job-radar-id jr-manual-example --company "Example AI" --role "Senior Infrastructure Engineer" --status applied --settings config/settings.yaml
```

Update a tracker record:

```powershell
python -m job_radar tracker update jr-manual-example --status interviewing --follow-up-on 2026-07-10 --settings config/settings.yaml
```

## Local web app

Job Radar has a local Flask web interface for tracker review and updates.

Start the GUI:

```powershell
python -m job_radar.web_app --settings config/settings.yaml
```

Open:

```text
http://127.0.0.1:5000/
```

Current GUI summary:

- Local landing page
- Application tracker workflows
- Tracker workflow filters
- Tracker search
- Tracker raw status and outcome filters
- Tracker sorting by workflow, applied date, company, role, status, and outcome
- Imported job history/archive review
- History search
- History decision and outcome filters
- History sorting by date, company, role, decision/status, and outcome
- Existing generated report and email-preview viewing
- In-app report viewer
- Controlled manual scan execution with GUI email sending disabled

See `docs/current-state.md` for the detailed current GUI capability list.

The local GUI is intentionally read/write only where the app already owns the workflow. Report viewing is read-only: it opens existing generated reports and email previews without starting a scan or sending email. The scan page can run a controlled manual scan from the local Flask process, with GUI email sending disabled.

## Run tests

Run the full suite:

```powershell
python -m pytest tests
```

Expected current result:

```text
430 passed
```

## Report structure

The Markdown and HTML reports include these major sections:

### Top Matches

Best clean matches based on score, location, excluded title filters, strong technical signals, and fit-risk checks.

Production Kubernetes-primary roles are demoted out of Top Matches unless there is strong infrastructure counterevidence. They may still appear under Review Needed when otherwise relevant.

The full Markdown and HTML reports show all Top Match eligible jobs.

### Top Matches Quick View

A capped summary view of the strongest Top Matches for fast scanning.

### Review Needed

High-score roles that are not clean Top Matches but may still deserve manual review.

### Track Status

Jobs already present in the application tracker are shown with tracker context.

Track Status is shown only when the scanned job has an actual tracker record. Job Radar does not auto-track jobs merely because they are good matches.

### Northern Colorado Highlights

Location-focused section for Northern Colorado and nearby strategic locations.

This section avoids duplicating jobs already shown in full Top Matches.

### Tracker action summary

Reports summarize tracked applications that may need action or review.

### Tracker workflow summary

Reports summarize tracker workflow states so stale, dormant, waiting, follow-up, active, and closed applications are visible during scan review.

### Passed / Not Recommended

The report summary includes an omitted jobs audit so large scans show why collected jobs did not surface as Top Match or Review Needed.

The full Markdown and HTML reports include passed jobs most worth reviewing, capped for readability.

## Run full live scan

```powershell
python -m job_radar scan --config config/target-companies.yaml --settings config/live-test-settings.yaml --report reports/target-scan.md --email-preview reports/target-email-preview.txt --send-email
```

Expected good output:

```text
Collector errors: 0
Report written: reports\target-scan.md
HTML report written: reports\target-scan.html
Email preview written: reports\target-email-preview.txt
Email send result: Email sending disabled by settings
```

## Run live validation with email preview

```powershell
Remove-Item data\live_test.sqlite3 -ErrorAction SilentlyContinue
Remove-Item reports\target-email-preview.txt -ErrorAction SilentlyContinue

python -m job_radar scan --config config/target-companies.yaml --settings config/live-test-settings.yaml --report reports/target-scan.md --email-preview reports/target-email-preview.txt

Get-Content reports\target-email-preview.txt -Raw
```

Email settings are validated from the settings file. With `email.enabled` set to `false`, `--send-email` only exercises the guarded send path and prints that email sending is disabled. No SMTP connection is made and no email is sent.

```powershell
python -m job_radar scan --config config/target-companies.yaml --settings config/live-test-settings.yaml --report reports/target-scan.md --email-preview reports\target-email-preview.txt --send-email
```

With `email.enabled` set to `false`, `--send-email` only exercises the guarded send path and prints that email sending is disabled.

## Email secret handling

Email passwords must not be stored in YAML files.

When email sending is enabled, the settings file should name an environment variable that contains the SMTP password:

```yaml
email:
  enabled: true
  sender: "you@example.com"
  recipients:
    - "you@example.com"
  smtp_host: "smtp.example.com"
  smtp_port: 587
  smtp_password_env: "JOB_RADAR_SMTP_PASSWORD"
```

For local testing, that environment variable can be set in the shell.

For k3s, that environment variable should come from a Kubernetes Secret.

If `email.enabled` is true and the configured password environment variable is missing, Job Radar fails cleanly before attempting to send email.

After real email send tests, remove the password environment variable from the shell:

```powershell
Remove-Item Env:\JOB_RADAR_SMTP_PASSWORD -ErrorAction SilentlyContinue
Test-Path Env:\JOB_RADAR_SMTP_PASSWORD
```

Expected:

```text
False
```

## Project principles

- Configured-company scanning only
- No broad crawling
- No automatic job applications
- No contacting employers
- Local SQLite system of record
- Rules-based scoring before LLM integration
- Safe manual review first
- Spreadsheet import is a bridge, not the final product
- App-native tracker CLI/GUI is the long-term tracking direction
- No regression
