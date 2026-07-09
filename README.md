# Job Radar

Job Radar is a local job discovery, triage, reporting, and application-tracking tool.

It scans configured company job boards, normalizes postings, stores them in SQLite, scores them against configurable preferences, imports application/history data, and provides reports plus a local tracker GUI.

The goal is to safely collect, rank, review, and track roles from known target companies so manual job-search work is faster and less dependent on stale job boards, stale LinkedIn results, or missed company postings.

Job Radar does not apply to jobs automatically. It does not contact employers. It does not scrape LinkedIn. It does not broadly crawl the internet.

## Documentation

Use these docs as the project reference set:

- `README.md` — quick project overview, common commands, and user-facing capabilities
- `docs/current-state.md` — detailed current project state and completed milestone ledger
- `docs/product-roadmap.md` — future direction, finish-line definition, and remaining milestones
- `docs/file-map.md` — repository structure and file ownership guide

Avoid duplicating the same update in all four docs. Update the doc that owns the information.

## Product direction

Job Radar started as a personal job discovery and application-tracking tool.

The long-term direction is a configurable local-first cross-platform application that another user can install, configure, and use without editing source code.

The intended long-term targets are:

- Windows packaged app
- Linux packaged app
- container/server mode for always-on use

Complete-enough means a user can install Job Radar, configure their own companies, preferences, salary expectations, locations, role targets, scan schedule, and reporting preferences, then run scans and track applications through the GUI.

## Current capabilities

Job Radar currently supports:

- configured company/source scanning
- SQLite-backed job storage
- new/seen/changed job tracking
- rules-based scoring
- location classification
- compensation-floor handling
- resume/profile match signals
- Top Match and Review Needed eligibility
- Markdown reports
- HTML reports
- plain-text email previews
- HTML email previews
- guarded email sending
- imported job/application history
- app-native application tracker records
- tracker workflow classification
- tracker/history mutual-exclusion import partitioning
- app-owned generated Job Radar IDs for scanned, spreadsheet-imported, and GUI-created tracker records
- automatic repair of older tracker IDs that used `posting-url:*` as primary identity
- local Flask GUI for tracker/history/report/scan/settings workflows
- controlled manual scans from the local GUI
- GUI profile/resume page with resume upload/replacement support
- PDF, DOCX, Markdown, and plain-text resume loading
- clickable Home dashboard cards for tracker workflow navigation
- clickable Tracker summary cards with active filter highlighting
- clickable History archive summary cards
- tracker Needs Review queue guidance
- grouped tracker quick actions for common workflow updates
- direct scan completion links to the HTML report, Markdown report, and email preview
- latest scan result shortcut cards on the Reports page
- in-app report viewer with copy button and focused Ctrl+A report-content selection
- read-only Settings page showing active runtime paths, retention settings, GUI scan defaults, and email status
- scan/report reassurance for temporary company/source or source/network errors
- `/tracker/` trailing-slash redirect to `/tracker`

Implemented source types include:

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
- HTML job-link collectors

## Important config files

`config/target-companies.yaml`

Primary target company/source configuration.

`config/settings.yaml`

Main settings used for normal local GUI and app runs.

`config/scoring.yaml`

Keyword scoring, location preferences, compensation behavior, Top Match rules, and Review Needed rules.

`config/live-test-settings.yaml`

Live-test scan settings for sandbox validation when needed.

`config/demo-companies.yaml`

Small demo-safe company configuration for examples and development.

## Runtime data

Runtime data is local and ignored by Git.

Common runtime paths:

- `data/`
- `reports/`
- `logs/`

Typical local database:

- `data/job_radar.sqlite3`

Generated reports, local databases, logs, private settings, local spreadsheets, and private profile/resume data should not be committed.

## Job history import

Job Radar can import application and review history from a local Excel workbook.

A sanitized example workbook is included at:

- `examples/job-history-template.xlsx`

The simplified Job Log format uses:

- Job Radar ID
- Date
- Company
- Role
- Posting URL
- Lead Source
- Decision
- Outcome
- Recruiter/Contact
- Notes
- Include In Job Radar

The workbook is a human job log and transition bridge, not the app's internal schema.

Job Radar ID is generated for scanned postings and shown in Markdown, HTML, and email-preview outputs. It is the preferred durable key when present.

Rows without Job Radar ID are still allowed for LinkedIn, referral, recruiter, company-site, and other manual leads. Posting URL remains evidence only; it is not used as the active tracker primary identity. When a spreadsheet-imported active application lacks a real Job Radar ID, the app assigns an app-owned `jr_manual_*` ID.

Spreadsheet import partitions rows into either active tracker records or archived job history records. Tracker and History are mutually exclusive:

- active application rows belong in Tracker
- terminal, passed, withdrawn, rejected, closed, or archived rows belong in History

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

Job Radar ID is app-owned tracker identity. For scanned postings, it comes from the scan pipeline. For spreadsheet-imported active applications without a scanned Job Radar ID, and for GUI-created manual applications, Job Radar assigns a generated `jr_manual_*` ID. Posting URLs remain in Source URL and should not become tracker primary keys.

Older tracker rows that used `posting-url:*` as the Job Radar ID are repaired to generated `jr_manual_*` IDs during tracker initialization and tracker reads.

The tracker classifies workflow state, including:

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

Add a manual tracker record through the GUI when possible. The GUI assigns the Job Radar ID when the record is saved.

Existing CLI manual-add/update commands remain available for fallback and testing workflows:

```powershell
python -m job_radar tracker add --job-radar-id jr-manual-example --company "Example AI" --role "Senior Infrastructure Engineer" --status Applied --outcome "Pending / In Progress" --settings config/settings.yaml
```

```powershell
python -m job_radar tracker update jr-manual-example --status Applied --outcome "Interview Scheduled" --follow-up-on 2026-07-10 --settings config/settings.yaml
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

- landing page with clickable tracker dashboard cards
- application tracker workflows
- clickable tracker summary cards with active filter highlighting
- tracker workflow filters
- tracker search
- tracker raw status and outcome filters
- tracker sorting by workflow, applied date, company, role, status, and outcome
- tracker Needs Review queue guidance
- tracker edit page with grouped quick actions
- tracker edit summary cards with wrapping Job Radar ID display
- tracker quick actions for refreshing activity, scheduling follow-up, marking workflow state, and moving terminal records to history
- manual Add Application page that assigns Job Radar ID automatically on save
- imported job history/archive review
- clickable History archive summary cards for Applied, Passed, Rejected, Withdrawn, and Closed Before Application records
- history editing
- history-to-tracker movement for reopened opportunities
- tracker/history delete actions
- history search
- history decision and outcome filters
- history sorting by date, company, role, decision/status, and outcome
- profile/resume page
- resume upload and replacement from the GUI
- existing generated report and email-preview viewing
- Reports page with latest scan result shortcut cards
- in-app report viewer with copy button and focused Ctrl+A report-content selection
- controlled manual scan execution with GUI email sending disabled
- scan completion links directly to HTML report, Markdown report, and email preview
- scan page reassurance that some company/source errors may be temporary and can be retried
- read-only Settings page showing active runtime paths, retention settings, GUI scan defaults, and email status without showing secrets
- `/tracker/` redirects to `/tracker`

The local GUI is intentionally read/write only where the app already owns the workflow.

Report viewing is read-only. It opens existing generated reports and email previews without starting a scan or sending email.

The scan page can run a controlled manual scan from the local Flask process, with GUI email sending disabled.

The Settings page is read-only for now. It surfaces the active settings file, database path, reports path, logs path, candidate profile path, retention settings, GUI scan defaults, and email enabled/disabled status without writing config changes.

## Report structure

The Markdown and HTML reports include these major sections:

### Top Matches

Best clean matches based on score, location, excluded title filters, strong technical signals, and fit-risk checks.

Production Kubernetes-primary roles are demoted out of Top Matches unless there is strong infrastructure counterevidence. They may still appear under Review Needed when otherwise relevant.

### Top Matches Quick View

A capped summary view of the strongest Top Matches for fast scanning.

### Northern Colorado Highlights

Location-focused section for Northern Colorado and nearby strategic locations.

This section avoids duplicating jobs already shown in full Top Matches.

### Review Needed

High-score roles that are not clean Top Matches but may still deserve manual review.

### Tracked Applications

Jobs already present in the application tracker are shown in their own full-report section with tracker context.

Tracked applications are not treated as new leads. They are excluded from Top Matches, Review Needed, and email summaries.

Job Radar does not auto-track jobs merely because they are good matches.

### Tracker action summary

Reports summarize tracked applications that may need action or review.

### Tracker workflow summary

Reports summarize tracker workflow states so stale, dormant, waiting, follow-up, active, and closed applications are visible during scan review.

### Collector Errors

Collector Errors sections explain that some source/network failures are temporary and may clear on a later scan.

### Passed / Not Recommended

The report summary includes an omitted jobs audit so large scans show why collected jobs did not surface as Top Match or Review Needed.

The full Markdown and HTML reports include passed jobs most worth reviewing, capped for readability.

## Email behavior

Email delivery is guarded behind explicit configuration and an explicit scan flag.

Email behavior:

- email settings are validated without sending by default
- SMTP delivery is disabled until intentionally enabled
- `--send-email` is required to exercise the send path
- passwords must come from environment variables
- no SMTP password should be stored in YAML
- with email disabled, `--send-email` prints that sending is disabled
- email summaries are intentionally capped for readability
- tracked applications are excluded from email summaries

## Run tests

Run the full suite:

```powershell
python -m pytest tests
```

Expected current result:

```text
463 passed
```

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
- App-owned Job Radar IDs; URLs are evidence, not tracker identity
- No regression
