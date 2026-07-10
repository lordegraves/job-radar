# Job Radar

Job Radar is a local-first job discovery, triage, reporting, and application-tracking tool.

It scans configured company job boards, normalizes postings, stores them in SQLite, scores them against configurable preferences, imports application/history data, and provides reports plus a local tracker GUI.

Job Radar does not apply to jobs automatically. It does not contact employers. It does not scrape LinkedIn. It does not broadly crawl the internet.

## Documentation set

This README is the canonical project document. It owns the current MVP state, setup commands, capabilities, operating principles, MVP boundary, and immediate direction.

Additional docs are intentionally limited in scope:

- `docs/product-roadmap.md` owns future direction, MVP finish line, post-MVP vision, and deferred scope.
- `docs/file-map.md` owns repository structure and file ownership boundaries.

`docs/current-state.md` is retired as a standalone long-form ledger. Current state belongs here.

## Product direction

Job Radar started as a personal job discovery and application-tracking tool.

The long-term direction is a configurable local-first cross-platform application that another user can install, configure, and use without editing source code. Long-term targets are Windows packaged app, Linux packaged app, and container/server mode for always-on use.

The near-term MVP target is narrower: a disciplined single-user local workflow that can scan target companies, score roles, manage active applications, surface follow-ups, preserve history, and produce useful reports without risky architecture expansion.

Complete-enough for the current MVP means one user can run Job Radar locally, maintain their resume/profile input, scan configured companies, review scored results, manage active applications and archived history through the GUI, and know what needs action next.

## MVP boundary

MVP includes:

- single local user
- existing profile/resume path
- existing scan/report/email-preview flow
- existing application tracker and history/archive
- GUI-managed active application workflow
- follow-up dates and dashboard flags
- read-only Companies page as scan/source inventory
- read-only Settings page as runtime visibility
- manual application tracking
- local SQLite data
- rules-based scoring
- no-regression tests and docs

MVP does not include:

- multi-user login/password
- generalized first-run onboarding wizard
- full company CRM
- separate contact database
- database-backed company inventory
- GUI company add/edit
- YAML-backed company writes
- LLM profile/gap analysis
- knowledge-base attachment system
- generalized multi-domain job-hunt workflows
- hosted SaaS behavior

These deferred items remain valid long-term goals, but they should not hijack the current MVP.

## Current capabilities

Job Radar currently supports:

- configured company/source scanning
- SQLite-backed job storage
- new/seen/changed job tracking
- rules-based scoring with positive/negative keywords, location rules, compensation floor handling, resume/profile match signals, Top Match rules, Review Needed rules, hiring probability labels, and hiring risk flags
- Markdown reports, HTML reports, plain-text email previews, and HTML email previews
- guarded email sending
- imported job/application history from a simplified Excel Job Log
- app-native application tracker records
- tracker workflow classification
- tracker/history mutual-exclusion import partitioning
- app-owned generated Job Radar IDs for scanned, spreadsheet-imported, and GUI-created tracker records
- automatic repair of older tracker IDs that used `posting-url:*` as primary identity
- local Flask GUI for tracker/history/report/companies/scan/settings workflows
- controlled manual scans from the local GUI
- GUI profile/resume page with resume upload/replacement support
- PDF, DOCX, Markdown, and plain-text resume loading
- clickable Home dashboard cards for tracker workflow navigation
- clickable Tracker summary cards with active filter highlighting
- clickable History archive summary cards
- tracker Needs Review queue guidance
- grouped tracker quick actions for common workflow updates
- direct scan completion links to HTML report, Markdown report, and email preview
- latest scan result shortcut cards on the Reports page
- in-app report viewer with copy button and focused Ctrl+A report-content selection
- read-only Companies page showing configured target companies, source types, enabled status, source details, notes, card-driven filters, search, and per-company detail pages
- read-only Settings page showing active runtime paths, retention settings, GUI scan defaults, and email status
- scan/report reassurance for temporary company/source or source/network errors
- `/tracker/` trailing-slash redirect to `/tracker`

## Source coverage

The primary live scan configuration is `config/target-companies.yaml`.

Implemented source types include Greenhouse, Lever, Ashby, Workday, USAJobs, iCIMS, Jibe, Jobsyn, Oracle HCM, SmartRecruiters, SelectMinds, Phenom, Dayforce, ADP Workforce Now, Activate, WEKA custom, Rippling, SchoolSpring, and HTML job-link collectors.

Current verified live scan state from the last documented scan:

```text
Companies enabled: 62
Jobs collected: 10,000
Jobs stored: 150
Jobs omitted: 9,850
Collector errors: 0
```

Source coverage is broad enough for the current MVP. New sources should only be added when they improve the actual target universe.

## Important config files

- `config/target-companies.yaml` — primary target company/source configuration.
- `config/settings.yaml` — main settings used for normal local GUI and app runs.
- `config/scoring.yaml` — keyword scoring, location preferences, compensation behavior, Top Match rules, and Review Needed rules.
- `config/live-test-settings.yaml` — live-test scan settings for sandbox validation when needed.
- `config/demo-companies.yaml` — small demo-safe company configuration for examples and development.

## Runtime data

Runtime data is local and ignored by Git.

Common runtime paths:

- `data/`
- `reports/`
- `logs/`

Typical local database:

```text
data/job_radar.sqlite3
```

Generated reports, local databases, logs, private settings, local spreadsheets, and private profile/resume data should not be committed.

## Storage, identity, and tracker routing

SQLite is the current system of record for scans, imported history, and app-native tracker data.

Job Radar stores normalized job postings, new/seen/changed jobs, stored/actionable jobs, omitted/not-actionable jobs, imported job/application history, application tracker records, and application workflow state.

Tracker identity is app-owned. Scanned postings use generated scan IDs. Spreadsheet-imported active applications without scanned IDs and GUI-created manual applications receive generated `jr_manual_*` IDs. Posting URLs remain evidence/source URLs and are not tracker primary keys.

Older tracker rows that used `posting-url:*` as their primary Job Radar ID are repaired into app-owned `jr_manual_*` IDs during tracker table initialization and before tracker reads.

A scanned posting with an attached application tracker record is treated as `Track Status`. Tracked applications are not new leads. They do not appear in Top Matches, Review Needed, or email summaries. They appear in full Markdown and HTML reports under Tracked Applications with tracker context.

Job Radar does not auto-track jobs because they scored well. Scan/report reads tracker state only.

## Scoring behavior

Scoring is configured from `config/scoring.yaml`.

Top Matches are reserved for clean, high-confidence roles with strong fit signals.

Production Kubernetes-primary roles are demoted out of Top Matches unless there is strong infrastructure counterevidence. They may still appear under Review Needed when otherwise relevant.

Generic Remote Competition is a risk signal only. It must not block or reject a role by itself.

## Report structure

Job Radar generates Markdown reports, HTML reports, plain-text email previews, and HTML email previews.

Reports include Summary, Companies scanned, Source type counts, Work location fit, Recommendation summary, History risk summary, Tracker action summary, Tracker workflow summary, Omitted jobs audit, Top Matches, Top Matches Quick View, Northern Colorado Highlights, Review Needed, Tracked Applications, and Passed / Not Recommended.

Collector Errors sections explain that some source/network failures are temporary and may clear on a later scan.

Markdown, HTML, and email-preview outputs show stable Job Radar IDs for scanned postings so imported history and tracker records can point back to exact surfaced roles.

Email previews are intentionally capped for readability and exclude tracked applications.

## Job history import

Job Radar can import application and review history from a local Excel workbook.

A sanitized example workbook is included at `examples/job-history-template.xlsx`.

The simplified Job Log format uses Job Radar ID, Date, Company, Role, Posting URL, Lead Source, Decision, Outcome, Recruiter/Contact, Notes, and Include In Job Radar.

The workbook is a human job log and transition bridge, not the app's internal schema. Job Radar does not write IDs or enrichment data back to the workbook.

Spreadsheet import partitions rows into either active tracker records or archived job history records. Tracker and History are mutually exclusive:

- active application rows belong in Tracker
- terminal, passed, withdrawn, rejected, closed, or archived rows belong in History

Current routing rules:

- `Applied` with live outcomes goes to the tracker.
- `Applied` with terminal outcomes goes to history.
- `Passed`, `Withdrawn`, and `Revisit` go to history.
- Terminal outcomes include `Closed Before Application`, `Rejected - No Interview`, `Rejected - After Interview`, and `Withdrawn`.

The latest clean workbook rebuild read 75 rows and produced 45 tracker records, 30 history records, and 0 cross-table company/role duplicates.

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

The tracker stores Job Radar ID, Company, Role, Source URL, Status / Decision, Follow-up date, Applied date, Last activity date, Outcome, Notes, and Created/updated timestamps.

Tracker status/decision values use the canonical workbook vocabulary. Active tracker records use `Applied` instead of internal lowercase values such as `applied`. Dormant state is represented by `Applied` plus the `Dormant` outcome.

The tracker classifies workflow state:

- `follow_up_due`
- `needs_date_review`
- `active_pipeline`
- `follow_up_scheduled`
- `waiting`
- `dormant`
- `stale`
- `presumed_closed`
- `closed`

The tracker GUI supports summary cards, active filters, workflow/search/status/outcome filters, sorting, manual add with app-assigned Job Radar ID, edit/update, grouped quick actions, Needs Review guidance, workflow badges, stale/dormant/presumed-closed emphasis, moving terminal records to history, deleting records, notes display, and wrapping Job Radar ID display.

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

Existing CLI manual-add/update commands remain available for fallback and testing workflows:

```powershell
python -m job_radar tracker add --job-radar-id jr-manual-example --company "Example AI" --role "Senior Infrastructure Engineer" --status Applied --outcome "Pending / In Progress" --settings config/settings.yaml
```

```powershell
python -m job_radar tracker update jr-manual-example --status Applied --outcome "Interview Scheduled" --follow-up-on 2026-07-10 --settings config/settings.yaml
```

## Local web app

Start the GUI:

```powershell
python -m job_radar.web_app --settings config/settings.yaml
```

Open:

```text
http://127.0.0.1:5000/
```

The local GUI is intentionally read/write only where the app already owns the workflow.

Report viewing is read-only. It opens existing generated reports and email previews without starting a scan or sending email.

The scan page can run a controlled manual scan from the local Flask process, with GUI email sending disabled.

The Companies page is read-only for MVP. It shows configured target companies, source types, enabled/disabled status, source details, notes, card-driven source-type/status filters, search, and per-company detail pages from `config/target-companies.yaml` without writing config changes.

Company config GUI writes remain intentionally disabled. The current write-strategy check allows future GUI writes only when `ruamel.yaml` is available, because PyYAML can read the config but does not preserve comments or source grouping on write. For MVP, company add/edit remains deferred.

The Settings page is read-only for MVP. It surfaces the active settings file, database path, reports path, logs path, candidate profile path, retention settings, GUI scan defaults, and email enabled/disabled status without writing config changes.

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

## Run tests

Run the full suite:

```powershell
python -m pytest tests
```

Expected current result:

```text
474 passed
```

Last verified focused/company-web suite:

```powershell
python -m pytest tests\test_company_config_service.py tests\test_web_app.py
```

Expected current result:

```text
70 passed
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

## Current project principles

- configured-company scanning only
- no broad crawling
- no automatic job applications
- no contacting employers
- local SQLite system of record
- rules-based scoring before LLM integration
- safe manual review first
- spreadsheet import is a bridge, not the final product
- app-native tracker CLI/GUI is the long-term tracking direction
- app-owned Job Radar IDs; URLs are evidence, not tracker identity
- no regression
- forward progress only
- MVP discipline before architecture expansion

## Known limitations

- Job Radar still imports spreadsheet history as a bridge for existing records and bulk intake, but GUI tracker/history search and filtering now cover the main review patterns previously handled with workbook filters.
- Future GUI growth should continue keeping `web_app.py` focused on route/form/render/redirect behavior.
- Resume/profile GUI support exists for resume upload/replacement, but broader profile/preference setup still requires config-file editing.
- Job Radar does not write enriched IDs or metadata back to the spreadsheet.
- Report scoring is still rules-based and may need calibration from real outcomes.
- Source coverage is broad enough for current use, but individual collectors may still need maintenance if ATS pages change.
- The email report is intentionally limited and does not include every detail from the full Markdown/HTML reports.
- Kubernetes deployment is not complete.
- LLM integration is not implemented yet.
- The Flask GUI is local/basic and not yet productionized.

## Not in scope right now

Do not work on these unless explicitly requested and documented as a new milestone:

- new source expansion
- broad scoring rewrite
- spreadsheet write-back
- LLM integration
- employer/contact automation
- production web authentication
- Kubernetes deployment
- large GUI styling overhaul
- company inventory database
- company add/edit GUI
- multi-user support

## Completed milestone summary

Completed areas include project scaffold, all current source collectors, SQLite storage, scan/report pipeline, Markdown/HTML/email outputs, guarded email sending, scoring/location/recommendation behavior, history import, Job Radar ID history matching, tracker storage/CLI/GUI, tracker workflow classification, tracker/history movement, tracker/history mutual exclusion, GUI report viewer, GUI scan flow, GUI profile/resume upload, read-only Companies page with filters/search/detail page, read-only Settings page, app-owned manual tracker ID generation, legacy `posting-url:*` repair, company config service layer, and company config write-strategy readiness checks.
