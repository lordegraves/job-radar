# Job Radar

Job Radar is a local-first job discovery, triage, reporting, and application-tracking tool.

It scans configured company job boards, normalizes postings, stores them in SQLite, scores them against configurable preferences, imports application/history data, and provides reports plus a local tracker GUI.

Job Radar does not apply to jobs automatically. It does not contact employers. It does not scrape LinkedIn. It does not broadly crawl the internet.

## Documentation policy

This README is the single source of truth for project documentation. It owns current state, commands, current capabilities, verification, repository structure, ownership boundaries, MVP scope, deferred scope, and long-term roadmap.

Do not duplicate current-state details, test counts, completed milestone summaries, or user-facing documentation into separate Markdown files.


## Product direction

Job Radar started as a personal job discovery and application-tracking tool.

The long-term direction is a configurable local-first cross-platform application that another user can install, configure, and use without editing source code. Long-term targets are Windows packaged app, Linux packaged app, and container/server mode for always-on use.

The near-term MVP target is narrower: a disciplined single-user local workflow that can scan target companies, score roles, manage active applications, surface follow-ups, preserve history, maintain resume/profile input, and produce useful reports without risky architecture expansion.

Projected MVP completion target: **2026-07-31**.

Complete-enough for the current MVP means one user can run Job Radar locally, maintain their resume/profile input, scan configured companies, review scored results, manage active applications and archived history through the GUI, and know what needs action next without treating the spreadsheet or command line as the primary daily interface.

The projected full-project completion target is **2026-09-30**. Full-project completion means Job Radar becomes a configurable local-first app with multiple launch targets, profile-aware configuration, user-managed companies/preferences/email/schedule, and no normal-use dependency on editing repo files by hand.

## MVP boundary

Projected MVP completion target: **2026-07-31**.

MVP means the local GUI supports the normal daily loop:

```text
scan -> review report -> track application -> update application -> review history -> manage resume/profile basics
```

MVP includes:

- single local user
- existing profile/resume path
- existing scan/report/email-preview flow
- existing application tracker and history/archive
- GUI-managed active application workflow
- workflow-aware tracker next-action guidance
- follow-up dates and dashboard flags
- report card to tracker-add workflow
- tracked scan job matching by Job Radar ID and source URL
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
- Windows packaged installer
- Linux packaged distribution
- container/server deployment
- multi-profile/profile-switching support
- LLM resume tailoring or cover-letter generation

These deferred items remain valid long-term goals, but they should not hijack the current MVP.

## Full project boundary

Projected full-project completion target: **2026-09-30**.

Full-project completion means a non-developer user can install or run Job Radar, configure their own profile, resume, preferences, target companies, scan settings, email settings, schedule, and application tracker without editing source files or YAML by hand.

Full project includes:

- everything in MVP
- profile creation and switching
- different resumes per profile
- different target companies per profile
- different role preferences per profile
- different scoring/preferences per profile
- user-added companies
- first-run setup flow
- user-friendly company add/edit/disable workflows
- email settings setup that does not expose secrets
- scheduled scan settings
- scan-history retention settings
- Windows packaged app target
- Linux packaged app target
- container/server mode
- developer CLI mode
- shared service layer across GUI, CLI, and packaged modes
- clear backup/export strategy for SQLite/user data
- no dependency on spreadsheet for normal use

Full project does not include automatic applications, automatic recruiter contact, LinkedIn scraping, bypassing authentication or anti-bot controls, or becoming a generic job board crawler.

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
- local Flask GUI for Active Applications, Application History, reports, companies, scan, settings, and profile/resume workflows
- shared navigation-aligned page width across the GUI for consistent left/right boundaries
- controlled manual scans from the local GUI
- GUI profile/resume page with candidate readiness summary, fit-profile signals, readable resume preview, safe resume upload/replacement, and collapsed troubleshooting paths
- PDF, DOCX, Markdown, and plain-text resume loading
- clickable Home dashboard cards for tracker workflow navigation
- focused latest-scan dashboard drill-downs for Top Matches, Review Needed, Tracked Applications, New Jobs, and Collector Errors
- human-readable Collector Errors cards with a clean zero-error state
- dashboard follow-up work panels for follow-ups due, date review, stale/dormant applications, and recent active applications
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
- post-tracking redirect to the tracked application's edit/detail page
- operational Active Applications edit/detail workspace with clear application identity, canonical workflow badge, prominent Next action guidance, grouped quick actions, structured application details, and an isolated delete action
- tracked scan job matching by exact Job Radar ID first, then source URL fallback, so manually tracked scanned jobs do not keep reappearing as new Top Matches

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

Reports include Summary, Companies scanned, Source type counts, Work location fit, Recommendation summary, History risk summary, Tracker action summary, Tracker workflow summary, Omitted jobs audit, Top Matches, Top Matches Quick View, Northern Colorado Highlights, Review Needed, Tracked Applications, New Jobs, and Passed / Not Recommended.

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

The Active Applications GUI supports summary cards, active filters, workflow/search/status/outcome filters, sorting, manual add with app-assigned Job Radar ID, an operational edit/detail workspace, grouped quick actions, prominent Next action guidance, Needs Review guidance, canonical workflow badges, stale/dormant/presumed-closed emphasis, moving terminal records to Application History, deleting records through an isolated danger zone, notes display, and wrapping Job Radar ID display.

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

The Scan page can run a controlled manual scan using the current Job Radar settings. Email sending remains disabled for manual scans started from the GUI.

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
488 passed
```

Latest verified focused web-app suite:

```powershell
python -m pytest tests\test_web_app.py
```

Expected current result:

```text
77 passed
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

## Repository map and ownership boundaries

## Root files

| File | Purpose | Keep / Review |
|---|---|---|
| `.gitignore` | Keeps local runtime data, generated reports, credentials, caches, and build artifacts out of Git. | Keep |
| `.vscode/settings.json` | Local editor guardrails for the repo, including disabling HTML/Jinja format-on-save to avoid template damage. | Keep |
| `README.md` | Canonical project overview, current MVP state, commands, capabilities, principles, and current verification. | Keep |
| `pyproject.toml` | Python project metadata, dependencies, package config, and test/tooling config. | Keep |

## Configuration

| File | Purpose | Keep / Review |
|---|---|---|
| `config/settings.yaml` | Main application settings used by the local GUI and normal app runs. | Keep |
| `config/scoring.yaml` | Scoring thresholds and scoring-related configuration. | Keep |
| `config/target-companies.yaml` | Primary target company/source list used by scans. | Keep |
| `config/demo-companies.yaml` | Small/demo-safe company config for development and examples. | Keep |
| `config/live-test-settings.yaml` | Live test scan settings. | Keep |
| `config/local-*.yaml` | Local/private config files, ignored by Git. | Local only / ignored |

## Runtime data

| File / Pattern | Purpose | Keep / Review |
|---|---|---|
| `data/.gitkeep` | Preserves the runtime data directory in Git. | Keep |
| `data/*.sqlite3` | Local runtime databases. | Local only / ignored |
| `data/*.db` | Local runtime databases. | Local only / ignored |
| `data/*.xlsx` | Local spreadsheet inputs, including current job history import files. | Local only / ignored |
| `reports/.gitkeep` | Preserves generated reports directory in Git. | Keep |
| `reports/*` | Generated reports, previews, audits, probes, and local run output. | Local only / ignored |
| `logs/.gitkeep` | Preserves log directory in Git. | Keep |
| `logs/*.log` | Runtime logs. | Local only / ignored |
| `logs/*.log.*` | Rotated runtime logs. | Local only / ignored |

## Examples

| File | Purpose | Keep / Review |
|---|---|---|
| `examples/job-history-template.xlsx` | Sanitized example workbook for the simplified Job Log import format. Contains headers, formatting, validation lists, and one fake sample row. | Keep |

## Core application package

| File | Purpose | Keep / Review |
|---|---|---|
| `job_radar/__init__.py` | Package marker. | Keep |
| `job_radar/__main__.py` | Allows running the package with `python -m job_radar`. | Keep |
| `job_radar/cli.py` | Command-line entry points and user-facing commands. | Keep / watch growth |
| `job_radar/config.py` | Loads and validates app configuration. | Keep |
| `job_radar/company_config_service.py` | Company configuration view models, read-only company config loading, source summaries, filtering, search text, detail-page lookup helpers, and write-strategy readiness checks. | Keep |
| `job_radar/models.py` | Core shared data models such as job postings. | Keep |
| `job_radar/storage.py` | SQLite persistence for collected/scored job data. | Keep |
| `job_radar/validation.py` | Validation helpers. | Keep |
| `job_radar/normalize.py` | Text/key normalization helpers. | Keep |

## Profile, resume, and match context

| File | Purpose | Keep / Review |
|---|---|---|
| `job_radar/candidate_profile.py` | Candidate preference/profile loading and interpretation. | Keep |
| `job_radar/profile_service.py` | Profile/resume service helpers, including GUI-safe resume upload/replacement and normalized resume regeneration. | Keep |
| `job_radar/resume_loader.py` | Loads Markdown, plain-text, PDF, and DOCX resume/profile text for matching. | Keep |
| `job_radar/resume_match.py` | Resume-to-posting match logic. | Keep |
| `profiles/clayton/profile.yaml` | Clayton-specific target profile and avoid/preference signals. | Keep / review before public release |
| `profiles/clayton/resume.md` | Clayton-specific resume source used by Job Radar. | Keep / review before public release |
| `profiles/clayton/resume.normalized.txt` | Normalized resume text for matching. | Keep / review whether generated |

## Scoring, recommendations, and history

| File | Purpose | Keep / Review |
|---|---|---|
| `job_radar/scoring.py` | Base score calculation and top-match eligibility signals. | Keep |
| `job_radar/recommendations.py` | Technical match, hiring probability, risk flags, recommended actions, and display eligibility. | Keep / watch growth |
| `job_radar/recommendation_constants.py` | Shared labels for actions, risks, recommendation ordering, and history reasons. | Keep |
| `job_radar/compensation.py` | Compensation parsing and compensation-floor evaluation. | Keep |
| `job_radar/job_history.py` | Imports and represents external job/application history from the spreadsheet bridge. Posting URLs are import evidence; active tracker identity is assigned by Job Radar when needed. | Keep |
| `job_radar/history_match.py` | Matches current postings against prior application/review history. | Keep |
| `job_radar/history_context.py` | Adds history context to scored postings/reports. | Keep |
| `job_radar/history_summary.py` | Summarizes imported history for reports. | Keep |

## Application tracker

| File | Purpose | Keep / Review |
|---|---|---|
| `job_radar/tracker/__init__.py` | Tracker package marker. | Keep |
| `job_radar/tracker/tracker_ids.py` | App-owned manual Job Radar ID generation for spreadsheet-imported and GUI-created tracker records that did not come from a scan. | Keep |
| `job_radar/tracker/tracker_models.py` | Application tracker data model. | Keep |
| `job_radar/tracker/tracker_storage.py` | SQLite persistence for application tracker records, including repair of legacy `posting-url:*` tracker IDs to app-owned `jr_manual_*` IDs. | Keep |
| `job_radar/tracker/tracker_service.py` | Tracker workflow classification, tracker/history conversion, tracker/history update and delete workflow actions, import partitioning, generated tracker identity rules, and tracker business rules. | Keep |

## Reporting and email

| File | Purpose | Keep / Review |
|---|---|---|
| `job_radar/reporting.py` | Markdown/HTML report rendering and report section logic. | Keep / watch growth |
| `job_radar/email_summary.py` | Email subject/body/HTML preview generation. | Keep / watch growth |
| `job_radar/email_sender.py` | Email delivery integration. | Keep |

## Web app / GUI

| File | Purpose | Keep / Review |
|---|---|---|
| `job_radar/web_app.py` | Flask web application entry point and GUI route handlers, including tracker/history/report/companies/scan/settings routes and `/tracker/` trailing-slash redirect. Route handlers should delegate tracker/history workflow actions and company configuration view/filter logic to service-layer functions. | Keep / watch growth |
| `job_radar/templates/index.html` | Web app landing page with tracker workflow cards, latest-scan drill-down cards, and the Needs attention queue. | Keep |
| `job_radar/templates/tracker.html` | Active Applications list with clickable summary filter cards, workflow filters, search, sorting, workflow display, Needs Review guidance, workflow badges, and edit links. | Keep |
| `job_radar/templates/tracker_edit.html` | Active Applications edit/detail workspace with application identity, canonical workflow badge, prominent Next action guidance, grouped quick actions, structured application details, and isolated destructive controls. | Keep |
| `job_radar/templates/tracker_add.html` | Manual application tracker add form. Job Radar assigns the tracker ID when the record is saved. | Keep |
| `job_radar/templates/history.html` | Application History page for terminal, passed, withdrawn, rejected, closed, and archived records, including summary cards, quick filters, search, filtering, sorting, chip display, and edit links. | Keep |
| `job_radar/templates/history_edit.html` | Job history edit form, including save, delete, and move-back-to-tracker workflow. | Keep |
| `job_radar/templates/profile.html` | Profile/resume page for viewing profile state and uploading/replacing resumes through the GUI. | Keep |
| `job_radar/templates/reports.html` | Reports page for viewing existing generated reports and email previews, including latest scan result shortcut cards. | Keep |
| `job_radar/templates/companies.html` | Read-only Companies list page showing configured target companies, source types, enabled status, source details, notes, source/status filters, and search without writing config changes. | Keep |
| `job_radar/templates/company_detail.html` | Read-only company detail page showing the full YAML-derived company record for inspection before future edit flows. | Keep |
| `job_radar/templates/report_view.html` | In-app report viewer shell for opening generated reports inside the GUI with shared dark styling, copy support, and focused Ctrl+A report-content selection. | Keep |
| `job_radar/templates/report_section.html` | Focused latest-scan section view for structured job cards and human-readable Collector Errors details. | Keep |
| `job_radar/templates/scan.html` | Scan page for manual command display, controlled local GUI scan execution, direct completion links to the latest outputs, and temporary source/company error reassurance. | Keep |
| `job_radar/templates/settings.html` | Read-only Settings page showing active runtime paths, retention settings, GUI scan defaults, and email status without showing secrets or writing config changes. | Keep |

## Collectors

Each collector should stay isolated by source/ATS type. This keeps source-specific behavior from becoming one large collector file.

| File | Purpose | Keep / Review |
|---|---|---|
| `job_radar/collectors/__init__.py` | Collector package marker. | Keep |
| `job_radar/collectors/registry.py` | Maps configured source types to collector implementations. | Keep |
| `job_radar/collectors/activate.py` | Activate source collector. | Keep |
| `job_radar/collectors/adp.py` | ADP collector. | Keep |
| `job_radar/collectors/ashby.py` | Ashby collector. | Keep |
| `job_radar/collectors/dayforce.py` | Dayforce collector. | Keep |
| `job_radar/collectors/greenhouse.py` | Greenhouse collector. | Keep |
| `job_radar/collectors/html.py` | Generic HTML collector. | Keep |
| `job_radar/collectors/icims.py` | iCIMS collector. | Keep |
| `job_radar/collectors/jibe.py` | Jibe collector. | Keep |
| `job_radar/collectors/jobsyn.py` | Jobsyn collector. | Keep |
| `job_radar/collectors/lever.py` | Lever collector. | Keep |
| `job_radar/collectors/oracle_hcm.py` | Oracle HCM collector. | Keep |
| `job_radar/collectors/phenom.py` | Phenom collector. | Keep |
| `job_radar/collectors/rippling.py` | Rippling collector. | Keep |
| `job_radar/collectors/schoolspring.py` | SchoolSpring collector. | Keep |
| `job_radar/collectors/selectminds.py` | SelectMinds collector. | Keep |
| `job_radar/collectors/smartrecruiters.py` | SmartRecruiters collector. | Keep |
| `job_radar/collectors/usajobs.py` | USAJobs collector. | Keep |
| `job_radar/collectors/weka.py` | WEKA-specific collector. | Keep / review if more company-specific collectors appear |
| `job_radar/collectors/workday.py` | Workday collector. | Keep |

## Scripts

| File | Purpose | Keep / Review |
|---|---|---|
| `scripts/run-daily-scan.ps1` | PowerShell helper for scheduled/manual daily scan runs. | Keep |

## Tests

Collector tests intentionally mirror collector files. This makes source-specific failures easier to identify.

| Test Area | Files | Keep / Review |
|---|---|---|
| Collector tests | `tests/test_*_collector.py`, plus `tests/test_collector_registry.py` | Keep |
| Config/CLI/storage/service tests | `tests/test_config.py`, `tests/test_company_config_service.py`, `tests/test_cli.py`, `tests/test_storage.py` | Keep |
| Scoring/recommendation/report tests | `tests/test_scoring.py`, `tests/test_reporting.py`, `tests/test_email_summary.py` | Keep |
| Profile/resume/history tests | `tests/test_candidate_profile.py`, `tests/test_resume_loader.py`, `tests/test_resume_match.py`, `tests/test_job_history.py`, `tests/test_history_match.py`, `tests/test_history_context.py`, `tests/test_history_summary.py` | Keep |
| Tracker tests | `tests/test_tracker_service.py`, `tests/test_tracker_storage.py` | Keep |
| Web app tests | `tests/test_web_app.py` | Keep |
| Utility tests | `tests/test_normalize.py`, `tests/test_compensation.py`, `tests/test_email_sender.py` | Keep |
| Integration tests | `tests/test_phase1a_integration.py` | Keep |

## Simplification guidance

The project is not needlessly complicated yet. The apparent file count comes from three mostly healthy choices:

1. Each collector has its own file and test.
2. Runtime/generated data is separated under `data/`, `logs/`, and `reports/`.
3. Scoring, recommendations, history, resume matching, reporting, and email output are separate concerns.

The main risk is future feature growth landing in already-large files. Avoid adding tracker or web UI logic into:

- `job_radar/reporting.py`
- `job_radar/email_summary.py`
- `job_radar/recommendations.py`
- `job_radar/storage.py`
- `job_radar/cli.py`

Current tracker and GUI logic already have dedicated boundaries:

- `job_radar/tracker/`
- `job_radar/web_app.py`
- `job_radar/templates/`

Continue using those boundaries instead of moving tracker behavior into reporting, recommendations, collectors, or generic storage.

## Tracker / GUI boundary

The spreadsheet is being phased out as the normal application-tracking interface. It remains a bridge for import/history data, but active application tracking now has a dedicated tracker module and a basic Flask GUI.

Tracker and History are expected to be mutually exclusive. Active rows belong in the tracker. Terminal, passed, withdrawn, rejected, closed, or archived rows belong in history.

The tracker should not be mixed into collector code or generic storage.

Reporting and recommendation code may read tracker state from `ScoredPosting.application` for display/routing, but tracker workflow behavior should stay in the tracker service layer.

Future GUI growth should keep `job_radar/web_app.py` small by moving workflow/business logic into GUI-neutral service functions. If route/template volume keeps growing, split the Flask interface into a dedicated web package before it becomes hard to maintain.

## Companies / Settings boundary

The Companies list/detail pages and Settings page are read-only in the current MVP.

They belong to the GUI route/template boundary and should not grow into config-writing business logic inside templates or route handlers.

For MVP:

- Companies is scan/source inventory.
- Settings is runtime visibility.
- Neither writes config.

Future company management and settings editing should be handled through service-layer functions and explicit validation, not direct template or route mutation.

## Roadmap and long-term direction

## Product goal

Job Radar started as a personal job discovery, scoring, reporting, and application-tracking tool.

The long-term product direction is to make Job Radar a configurable local-first job search assistant that another user can install, configure, and use without editing source code.

The finish line is not a hosted SaaS product and not an automated job-application bot.

Job Radar is complete-enough when a user can install it, configure their own job search profile, add desired companies, run scans, review scored jobs, track applications, and receive reports without editing source code.

## Product principles

Job Radar should remain local-first, user-controlled, configured-company based, safe for manual review, transparent in scoring and recommendations, non-invasive, not dependent on broad crawling, not dependent on LinkedIn scraping, not responsible for contacting employers, and not responsible for submitting applications automatically.

The app should help the user decide where to spend time. It should not pretend to replace the user.

## MVP finish line

The immediate MVP target is a single-user local app that demonstrates disciplined execution and practical usefulness.

Projected MVP completion target: **2026-07-31**.

MVP is complete when:

1. A single local user can launch the GUI reliably.
2. The user can run or review scans from configured company sources.
3. The user can review Markdown/HTML reports and email previews.
4. The user can manage active applications in the GUI.
5. The user can add manual applications without inventing tracker IDs.
6. The user can edit tracker records and use common quick actions.
7. The user can move terminal applications from tracker to history.
8. The user can reopen history records back to tracker when needed.
9. The dashboard surfaces application follow-up work clearly.
10. Resume upload/replacement works through the GUI.
11. Settings and Companies pages provide safe read-only visibility.
12. The app preserves tracker/history mutual exclusivity.
13. The app preserves app-owned Job Radar IDs.
14. The app keeps private runtime data out of Git.
15. The test suite remains green.
16. Documentation is consolidated enough to stay maintainable.


## Near-term MVP priorities

1. MVP polish for the single-user local workflow.
2. Dashboard follow-up display refinement after real tracker use.
3. Settings visibility improvements where they remove real user friction.
4. Documentation alignment for local GUI use, scan use, and safe email behavior.
5. Company add/edit only if it can be done safely without corrupting source grouping.
6. Packaging/launcher preparation remains post-MVP unless explicitly pulled forward.

## Deferred until after MVP

The following are valid long-term goals, but are intentionally deferred until the single-user MVP is stable, polished, tested, and portfolio-ready:

- editable company management
- company/contact relationship tracking
- database-backed company inventory
- GUI company add/edit
- YAML-backed company writes
- multi-user login/password support
- full onboarding wizard
- LLM-assisted strengths/gaps analysis
- generalized multi-domain job-hunt workflows
- full knowledge-base attachment system
- hosted SaaS behavior
- automatic job applications
- employer outreach automation
- LinkedIn scraping
- mobile app
- native desktop GUI rewrite

## Long-term product vision

Projected full-project completion target: **2026-09-30**.

The long-term product vision is a full job-hunt operations system.

It should eventually help users manage the many moving pieces of a job search: profile creation, resume upload and analysis, strengths and gaps, preferred companies, email setup, scheduled scans, dashboard workflow, application tracking, follow-up reminders, company research, contacts, recruiter history, and interview preparation.

The application should eventually behave more like an IT ticket system than a static spreadsheet:

- applications requiring follow-up should be flagged
- stale items should surface on the dashboard
- active records should have workflow state
- terminal records should move to history/archive
- companies should act like an inventory/knowledge-base area
- contacts should be tracked when available, but not required

The app should eventually become useful beyond IT job hunts, but the current MVP should stay focused on the existing single-user workflow. Profile creation and switching should eventually support different users, resumes, target companies, role preferences, and scoring/preferences without forcing separate code paths.

## Future product shape

Full-project completion means Job Radar is configurable and profile-aware enough that a normal user can install or run it, configure their own search, and use it without editing repo files by hand.

Target shape:

```text
Cross-platform local-first application + SQLite + guided setup + configurable job search profile
```

Job Radar should support three launch/deployment targets without becoming three separate products:

```text
Windows packaged app
Linux packaged app
Container/server mode
```

The current Flask GUI is the shared web/server interface. It should remain usable directly in browser/server mode and should also be able to sit behind a future desktop wrapper or launcher for normal click-to-open desktop use.

The final product should hide developer launch commands from normal users. A user should eventually open Job Radar from a Start Menu shortcut, Linux application launcher, packaged executable, or container/service URL depending on how they choose to run it.

The user should eventually be able to install Job Radar, open it from a normal launcher, create/edit their search profile, add target companies, define preferred roles, salary expectations, location rules, blocker rules, positive match signals, run scans manually, schedule scans, configure scan history retention, review results, track applications, review job history, configure email reports, and export or back up local data.

## Complete-enough product definition

Longer-term complete-enough means:

1. A non-developer user can install and launch the app.
2. A user can configure their own companies without editing source code.
3. A user can configure their own ATS/source settings without editing source code.
4. A user can configure their own preferences without editing source code.
5. A user can configure their own salary floor and ideal salary.
6. A user can configure their own acceptable locations and remote/hybrid/on-site rules.
7. A user can configure their own role interests, seniority targets, and avoid rules.
8. A user can configure email reporting through a user-friendly setup flow.
9. A user can run a scan from the GUI.
10. A user can review scan results from the GUI.
11. A user can track active applications from the GUI.
12. A user can review historical, passed, skipped, rejected, and archived jobs from the GUI.
13. A user can create manual applications from the GUI without manually inventing tracker IDs.
14. A user can schedule recurring scans.
15. Runtime data is stored outside the source/repo directory.
16. Real user data is not committed to Git.
17. The app can run as a standalone program on a user's PC.
18. The app can run unattended as a service on a user-controlled system.
19. The app can run in Kubernetes when that matches the user's setup.
20. The app can be packaged for Windows with an `.exe` entry point and installer.
21. The app can be packaged for Linux using a `.tar` or tarball-based distribution.
22. Documentation clearly separates developer setup from user setup.
23. Existing CLI/test/report behavior does not regress.

## User configuration requirements

Job Radar must stop assuming one hard-coded user profile.

The app should eventually support user-specific configuration for user name/profile label, desired role titles, seniority levels, desired/excluded companies, preferred/excluded industries, positive/negative keywords, hard blockers, soft risk signals, salary floor, ideal salary, acceptable/preferred locations, remote/hybrid/on-site rules, relocation openness, travel tolerance, security clearance tolerance, employment type preference, resume/profile text, report preferences, scan history retention, email preferences, and scan schedule.

## Desired companies

For MVP, the Companies page remains read-only scan/source inventory.

Long term, users need a way to add desired companies without editing YAML manually.

Required long-term behavior:

- add company from GUI
- edit company from GUI
- disable company without deleting it
- delete company if needed
- choose source type when known
- store company career page URL
- store ATS/source-specific identifier when needed
- validate company source configuration before saving when possible
- show whether the source works
- show last scan result per company
- show collector errors per company
- allow targeted company/source rescan when practical
- allow import/export of company lists

The GUI should eventually support a company setup flow:

```text
Company name
Career page URL
Source type
Remote/location relevance
Notes
Enabled yes/no
Test source button
Save
```

Normal GUI company data should eventually live in SQLite or user data, not as risky direct YAML mutation. YAML may remain useful for seed/default source definitions. If YAML writes are ever supported, they require a comment-preserving writer such as `ruamel.yaml`.

## Preferences and scoring setup

Users need guided preference setup for salary floor, ideal salary, acceptable/preferred locations, remote-only or remote-preferred behavior, target roles, acceptable seniority levels, positive keywords, negative keywords, blockers, review-needed signals, and avoid-company or avoid-industry rules.

The GUI should eventually explain what each setting does in plain language.

## Profile and resume setup

The current profile and resume flow has started moving into the GUI, but broader profile setup is still too user-specific.

Long-term behavior:

- create a user profile from the GUI
- add, paste, upload, or replace resume/profile text from the GUI
- preserve the current GUI resume upload/replacement flow
- keep PDF, DOCX, Markdown, and plain-text resume loading supported
- store resume/profile text in the user data directory
- allow the user to update it
- use it for match signals
- avoid committing private profile/resume data to Git
- mirror the existing CLI resume/profile process instead of creating a separate GUI-only resume system
- reuse the same resume loader/profile logic used by scans and CLI commands

Future user-data layout should separate shipped app files from personal data.

Windows target:

```text
%LOCALAPPDATA%\JobRadar\
  settings.yaml
  profile.yaml
  companies.yaml
  preferences.yaml
  job_radar.sqlite3
  reports\
  logs\
```

Linux target:

```text
~/.config/job-radar/
  settings.yaml
  profile.yaml
  companies.yaml
  preferences.yaml

~/.local/share/job-radar/
  job_radar.sqlite3
  reports/
  logs/
```

## Cross-platform app direction

Job Radar should be built as one core application with multiple launch targets, not as separate desktop, web, and server products.

Supported target modes:

- Windows packaged app
- Linux packaged app
- Container/server mode
- Developer CLI mode

Recommended path:

1. Keep Flask as the shared web/server UI.
2. Keep workflow/business logic in GUI-neutral services.
3. Add a friendly GUI launch command.
4. Add a local launcher that starts the app and opens the UI automatically.
5. Add container/server deployment.
6. Add desktop wrapper or packaged launcher for Windows and Linux.
7. Package Windows and Linux distributions.

## Installer and packaging roadmap

The long-term Windows target is `JobRadarSetup.exe`.

The Windows installation path should be simple enough for a non-developer user to install, launch, configure, and run a first scan without manually editing source files.

Likely Windows packaging path:

```text
PyInstaller + Inno Setup
```

Possible later alternatives include Nuitka, Briefcase, MSIX, NSIS, and WiX Toolset.

Linux should remain supported, but Windows packaging comes first. The required Linux packaging path is a `.tar` or tarball-based distribution. Possible later Linux formats include AppImage, `.deb`, systemd user service/timer, and Docker/container deployment.

## Deployment flexibility roadmap

Job Radar should be flexible enough to run in different user-controlled environments: Windows packaged desktop/local app, Linux packaged desktop/local app, unattended service on a local machine or small server, containerized web/server mode, Kubernetes service in a user-managed cluster, and developer CLI mode.

Deployment work must preserve one core service layer so CLI, Flask UI, desktop launcher/wrapper, scheduler, packaged deployments, and container/server deployments do not become separate products.

## Scheduler roadmap

Scheduled scans should eventually be configurable without editing scripts.

Windows target: Task Scheduler integration, user-selectable schedule, local logs, and safe failure behavior.

Linux target: systemd user timer, local logs, and safe failure behavior.

The scheduler should run the same scan pipeline as manual scans.

Scan history retention should be configurable from Settings. The default should favor the latest scan outputs, with optional retention such as latest plus previous scan or a configured number of retained scans.

## Data ownership and privacy

Job Radar should assume job search data is private.

Private data includes user profile, resume text, target companies, application history, tracker notes, recruiter/contact details, email settings, local reports, and logs that may contain job/application details.

Private data should live in the user data directory and stay out of Git.

The repo may include demo config, example config, sanitized workbook, documentation, tests, and non-private sample data.

## Staged roadmap

### Stage 1: Finish Current GUI Workflow

- Finish GUI-native tracker/history workflows so normal application tracking no longer depends on the spreadsheet.
- Preserve completed tracker workflow improvements.
- Make the GUI the source of truth for active applications, archived history, passed roles, rejected applications, dormant roles, and follow-up state.
- Preserve Tracker/History mutual exclusivity.
- Preserve app-owned tracker identity.
- Keep tracker/history workflow actions in GUI-neutral services.
- Decide the final role of the spreadsheet bridge.
- Keep scan/report behavior stable while GUI tracker/history behavior improves.

### Stage 2: User Configuration

- Build user-friendly configuration for desired companies, ATS sources, role preferences, compensation, location rules, exclusions, and email settings.
- Add configuration screens or guided setup so users do not need to hand-edit YAML for basic use.
- Add preference setup page.
- Add company management page.
- Add salary/location setup.
- Add resume/profile setup that mirrors the existing CLI resume/profile process.
- Move user-specific runtime config out of repo assumptions.

### Stage 3: Scheduling and Email

- Add email setup flow.
- Configure email from GUI.
- Support SMTP settings, sender/recipient configuration, safe test email, and clear failure messages.
- Configure scheduled scans from GUI.
- Keep secrets out of config files.
- Add clear validation and failure messages.

### Stage 4: Packaging and Deployment

- Prepare the app to run as a standalone desktop/local program.
- Keep the Flask GUI usable as the shared web/server interface.
- Add a friendly GUI launch command.
- Add a launcher that starts Job Radar and opens the UI automatically.
- Store user data in OS-appropriate location.
- Build Windows executable.
- Build Windows installer.
- Build Linux `.tar` / tarball distribution.
- Add container/server deployment.
- Support standalone PC operation.
- Support service-style operation.
- Support Kubernetes deployment.
- Add deployment-friendly configuration for persistent data, reports, logs, backups, retention, and safe upgrades.

### Stage 5: First-Run Experience and Stabilization

- Keep the app single-user by default, while leaving room for multiple profiles if useful.
- Create a simple first-run experience from installation to first scan/report.
- Improve user-facing error messages.
- Add backup/export path.
- Add import path for companies/preferences.
- Add onboarding documentation.
- Add recovery/troubleshooting documentation.
- Add installation and operations documentation for Windows desktop, Linux standalone/server, and Kubernetes service modes.
- Add release validation for packaged builds.
- Run no-regression validation.

## Completed milestone summary

Completed areas include:

- project scaffold and repository structure
- current source collectors and source registry
- SQLite-backed scan, job, tracker, and history storage
- scan, scoring, recommendation, reporting, and guarded email workflows
- Markdown, HTML, plain-text email, and HTML email outputs
- spreadsheet history import with tracker/history mutual exclusion
- app-owned Job Radar IDs and repair of legacy `posting-url:*` tracker IDs
- tracker storage, CLI support, workflow classification, quick actions, and tracker/history movement
- Flask GUI for Home, Active Applications, Application History, Profile / Resume, Reports, Companies, Scan, and Settings
- dashboard scan summaries, workflow counts, follow-up work, and attention queues
- report-card-to-tracker-add workflow and post-tracking edit/detail redirect
- tracked scan job matching by Job Radar ID and source URL
- read-only Companies list/detail views and Settings visibility
- controlled GUI scans and in-app report viewing
- Profile / Resume MVP polish with candidate overview, fit-profile summary, readable resume preview, safer replacement flow, and collapsed technical details
- Active Applications edit/detail workspace with clear application identity, canonical workflow labeling, prominent Next action guidance, grouped quick actions, structured application details, and isolated destructive controls
- shared navigation-aligned page width and user-facing Active Applications/Application History terminology
- MVP scan/dashboard acceptance polish with redundant Home quick links removed, focused New Jobs and Collector Errors drill-downs, clearer scan labels, and user-facing latest-scan terminology
- consolidated documentation and no-regression test coverage
