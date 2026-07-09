# Job Radar Current State

Last updated: 2026-07-09

## Purpose

Job Radar is a local job discovery, triage, reporting, and application-tracking tool.

Its purpose is to safely scan known target company job boards, normalize postings, store them in SQLite, score them against the user's job preferences, generate reports that make manual review faster, and track application workflow through an app-native tracker.

Job Radar does not apply to jobs automatically. It does not contact employers. It does not broadly crawl the internet.

## Document ownership

This file is the detailed current-state snapshot and completed milestone ledger.

Use the documentation set this way:

- `README.md` owns quick project overview, common commands, and user-facing capabilities.
- `docs/current-state.md` owns detailed current behavior and completed milestone state.
- `docs/product-roadmap.md` owns future direction, finish-line definition, and remaining milestones.
- `docs/file-map.md` owns repository structure and file ownership boundaries.

Avoid pasting the same update into all four docs.

## Product direction

Job Radar started as a personal job discovery and application-tracking tool, but the project direction is expanding toward a configurable local-first cross-platform application that can be adapted for other users.

The intended long-term targets are:

- Windows packaged app
- Linux packaged app
- container/server mode for always-on use

These targets should share the same core services and SQLite-backed data model instead of becoming separate products.

The finish line is defined in:

- `docs/product-roadmap.md`

## Current scan coverage

The primary live scan configuration is:

- `config/target-companies.yaml`

The current main settings file is:

- `config/settings.yaml`

The live-test settings file remains available for sandbox validation when needed:

- `config/live-test-settings.yaml`

Current verified live scan state from the last documented scan:

- Companies enabled: 62
- Jobs collected: 10,000
- Jobs stored: 150
- Jobs omitted: 9,850
- Collector errors: 0

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

Source coverage is broad enough for current use. New sources should only be added when they improve the actual target universe.

## Current storage behavior

Job Radar stores normalized job postings in SQLite.

It tracks:

- New jobs
- Seen jobs
- Changed jobs
- Stored/actionable jobs
- Omitted/not-actionable jobs
- Imported job/application history
- Application tracker records
- Application workflow state

SQLite is the current system of record for scans, imported history, and app-native tracker data.

Tracker identity is app-owned. Scanned postings use generated scan IDs. Spreadsheet-imported active applications without scanned IDs and GUI-created manual applications receive generated `jr_manual_*` IDs. Posting URLs remain evidence/source URLs and are not tracker primary keys.

Older tracker rows that used `posting-url:*` as their primary Job Radar ID are repaired into app-owned `jr_manual_*` IDs during tracker table initialization and before tracker reads.

## Current scoring behavior

Job Radar uses config-driven scoring from:

- `config/scoring.yaml`

Current scoring includes:

- Positive keyword scoring
- Negative keyword scoring
- Location preference scoring
- Top Match eligibility rules
- Review Needed eligibility rules
- Compensation floor handling
- Profile avoid matching
- Resume/profile match signals
- Hiring probability labels
- Hiring risk flags

Top Matches are reserved for clean, high-confidence roles with strong fit signals.

Production Kubernetes-primary roles are demoted out of Top Matches unless there is strong infrastructure counterevidence. They may still appear under Review Needed when otherwise relevant.

Generic Remote Competition is a risk signal only. It must not block or reject a role by itself.

## Current recommendation and tracker routing behavior

A scanned posting with an attached application tracker record is treated as `Track Status`.

Tracked applications are not new leads.

Tracked applications:

- do not appear in Top Matches
- do not appear in Review Needed
- do not appear in email summaries
- appear in the full Markdown and HTML reports under Tracked Applications
- keep tracker context visible in the full report

This behavior is driven by the attached tracker record, not merely by fuzzy history context.

Job Radar does not auto-track jobs because they scored well. Scan/report reads tracker state only.

## Current report behavior

Job Radar generates:

- Markdown report
- HTML report
- Plain-text email preview
- HTML email preview

Reports include:

- Summary
- Companies scanned
- Source type counts
- Work location fit
- Recommendation summary
- History risk summary
- Tracker action summary
- Tracker workflow summary
- Omitted jobs audit
- Top Matches
- Top Matches Quick View
- Northern Colorado Highlights
- Review Needed
- Tracked Applications
- Passed / Not Recommended

The full Markdown and HTML reports keep detailed review information.

Collector Errors sections now explain that some source/network failures are temporary and may clear on a later scan.

Markdown, HTML, and email-preview outputs show stable Job Radar IDs for scanned postings so imported history and tracker records can point back to exact surfaced roles.

The email preview is intentionally capped for readability and excludes tracked applications.

Passed / Not Recommended includes audit details so large scans explain why most collected jobs did not surface as Top Match or Review Needed.

## Current history behavior

Job Radar imports application and review history from a local Excel workbook.

A sanitized example workbook is included at:

- `examples/job-history-template.xlsx`

The example workbook contains the simplified Job Log headers, formatting, validation lists, and one fake sample row. It must not contain real application history.

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

Job Radar ID is generated by Job Radar for scanned postings and is the preferred durable history key when present.

History matching checks exact Job Radar ID before falling back to guarded company/title similarity.

Exact Job Radar ID matches can provide history context. Existing application tracker records are attached during scan/report generation so already-tracked jobs route to Tracked Applications.

Fuzzy company/title matches only route to Track Status when the title match is strong enough. Weaker fuzzy matches remain history context instead of treating the role as already applied.

Rows without Job Radar ID are allowed for LinkedIn, referral, recruiter, company-site, and manual leads.

Posting URL is fallback evidence for manual/external rows, but it is not active tracker identity. When an active spreadsheet-imported row lacks a real Job Radar ID, the app assigns a generated `jr_manual_*` tracker ID.

The workbook is treated as a human job log and import bridge, not the app's internal schema.

Spreadsheet import partitions rows into either the active application tracker or the archived job history table. Tracker and History are mutually exclusive: a row should exist in one place or the other, not both.

Current routing rules:

- `Applied` with live outcomes goes to the tracker.
- `Applied` with terminal outcomes goes to history.
- `Passed`, `Withdrawn`, and `Revisit` go to history.
- Terminal outcomes include `Closed Before Application`, `Rejected - No Interview`, `Rejected - After Interview`, and `Withdrawn`.

The latest clean workbook rebuild read 75 rows and produced:

- 45 tracker records
- 30 history records
- 0 cross-table company/role duplicates

Job Radar does not write IDs or enrichment data back to the workbook.

## Current tracker behavior

Job Radar now has an app-native application tracker.

The tracker stores:

- Job Radar ID
- Company
- Role
- Source URL
- Status / Decision
- Follow-up date
- Applied date
- Last activity date
- Outcome
- Notes
- Created/updated timestamps

Tracker status/decision values now use the canonical workbook vocabulary. Active tracker records use `Applied` instead of internal lowercase values such as `applied`. Dormant state is represented by `Applied` plus the `Dormant` outcome.

The tracker can classify application workflow state, including:

- follow_up_due
- needs_date_review
- active_pipeline
- follow_up_scheduled
- waiting
- dormant
- stale
- presumed_closed
- closed

Tracker action summaries are included in reports so applications needing attention are visible during scans.

The tracker can be managed through CLI commands and through the Flask GUI.

The tracker GUI currently supports:

- clickable tracker summary cards
- active tracker filter highlighting
- workflow filters
- search
- raw status filters
- raw outcome filters
- combined workflow/search/status/outcome/sort review
- workflow-priority sorting
- applied-date newest/oldest sorting
- company sorting
- role sorting
- status sorting
- outcome sorting
- manual add with app-assigned Job Radar ID
- edit/update
- grouped quick actions
- quick action to refresh last activity to today
- quick action to schedule follow-up next week
- quick action to mark follow-up due
- quick actions for active pipeline states
- quick actions for moving terminal records to history
- Needs Review queue guidance
- workflow badges
- visual emphasis for stale/dormant/presumed-closed rows
- moving terminal tracker records to history
- deleting tracker records
- notes display
- wrapping Job Radar ID display on the edit page
- `/tracker/` redirect to `/tracker`

The tracker is the long-term direction for active application workflow. The spreadsheet remains an import/history bridge and possible bulk-import path, but it is being retired as the normal application-tracking interface.

Passed/reviewed jobs are imported into job history. They are not automatically added to the active application tracker.

The tracker/history GUI now supports moving active tracker records to archived history when the GUI changes an active application to a terminal outcome.

Tracker/history workflow actions now live in GUI-neutral service functions so the CLI, Flask UI, future desktop launcher/wrapper, scheduler, and container/server mode can reuse the same behavior.

## Current GUI behavior

Job Radar has a basic Flask web interface.

Current GUI capabilities:

- Landing page
- Clickable Home dashboard cards for tracker workflow navigation
- Application tracker list
- Clickable tracker summary cards
- Active tracker filter card highlighting
- Tracker workflow filters
- Tracker search
- Tracker raw status filters
- Tracker raw outcome filters
- Tracker combined workflow/search/status/outcome/sort review
- Tracker workflow-priority sorting
- Tracker applied-date newest/oldest sorting
- Tracker company sorting
- Tracker role sorting
- Tracker status sorting
- Tracker outcome sorting
- Tracker Needs Review queue guidance
- Tracker workflow badges
- Tracker edit page
- Tracker edit summary cards with wrapped Job Radar ID display
- Status and outcome dropdowns
- Grouped tracker quick actions
- Tracker quick actions for refreshing activity, scheduling follow-up, marking workflow state, and moving terminal records to history
- Manual application add form with app-assigned Job Radar ID on save
- Tracker-to-history movement for terminal outcomes
- Tracker row deletion
- Notes display from stored tracker records
- Job history/archive page for imported historical records
- Clickable History archive summary cards
- History edit page
- History-to-tracker movement for reopened opportunities
- History row deletion
- History search
- History decision filters
- History outcome filters
- History combined search/filter/sort review
- History date newest/oldest sorting
- History company sorting
- History role sorting
- History decision/status sorting
- History outcome sorting
- Profile/resume page
- Resume upload and replacement from the GUI
- Existing generated report and email-preview viewing
- Reports page for existing generated reports and email previews
- Reports page latest scan result shortcut cards
- Read-only Companies page showing configured target companies, source types, enabled status, source details, notes, filters, and per-company detail pages
- In-app report viewer
- Report viewer Copy report text button
- Report viewer Ctrl+A report-content selection when the viewer has focus
- Controlled manual scan execution from the local GUI
- Direct scan completion links to HTML report, Markdown report, and email preview
- Scan page reassurance that some company/source errors may be temporary and can be retried
- Read-only Settings page showing active runtime paths, retention settings, GUI scan defaults, and email status
- `/tracker/` trailing-slash redirect

Current GUI files include:

- `job_radar/web_app.py`
- `job_radar/templates/index.html`
- `job_radar/templates/tracker.html`
- `job_radar/templates/tracker_edit.html`
- `job_radar/templates/tracker_add.html`
- `job_radar/templates/history.html`
- `job_radar/templates/history_edit.html`
- `job_radar/templates/profile.html`
- `job_radar/templates/reports.html`
- `job_radar/templates/companies.html`
- `job_radar/templates/company_detail.html`
- `job_radar/templates/report_view.html`
- `job_radar/templates/scan.html`
- `job_radar/templates/settings.html`

Current tracker module files use the tracker naming convention:

- `job_radar/tracker/tracker_ids.py`
- `job_radar/tracker/tracker_models.py`
- `job_radar/tracker/tracker_storage.py`
- `job_radar/tracker/tracker_service.py`

Current GUI command:

```powershell
python -m job_radar.web_app --settings config/settings.yaml
```

Current local GUI URL:

```text
http://127.0.0.1:5000/
```

The tracker GUI focuses on active application tracker records. The job history/archive page shows imported historical records from the spreadsheet bridge without adding them to the active application tracker.

The reports page opens existing generated reports and email previews without starting a scan or sending email. The Reports page now highlights latest scan results with shortcut cards and separates additional files from the primary scan outputs.

The Companies page is currently read-only. It shows configured target companies, source types, enabled/disabled status, source details, notes, source-type/status filters, and per-company detail pages from `config/target-companies.yaml` without writing config changes.

The in-app report viewer supports copying report text and selecting only report content with Ctrl+A when the viewer has focus.

The scan page can run a controlled manual scan from the local Flask process, with GUI email sending disabled. On success, the Scan page links directly to the latest HTML report, Markdown report, and email preview. The scan page also explains that some company/source errors are temporary and may clear after a later scan.

The Settings page is currently read-only. It shows active runtime paths, retention settings, GUI scan defaults, and email enabled/disabled status without showing secrets or writing config changes.

## Current email behavior

Email delivery is guarded behind explicit configuration and an explicit scan flag.

Email behavior:

- Email settings are validated without sending by default.
- SMTP delivery is disabled until intentionally enabled.
- `--send-email` is required to exercise the send path.
- Passwords must come from environment variables.
- No SMTP password should be stored in YAML.
- With email disabled, `--send-email` prints that sending is disabled.
- Email summaries are intentionally capped for readability.
- Tracked applications are excluded from email summaries.

## Current verification

Latest verification from this milestone:

```text
python -m pytest tests\test_web_app.py
64 passed

python -m pytest tests
465 passed
```

## Current project principles

- Configured-company scanning only
- No broad crawling
- No automatic job applications
- No employer outreach
- Local SQLite system of record
- Rules-based scoring before LLM integration
- Safe manual review first
- No regression
- Forward progress only
- Spreadsheet import is a bridge, not the final product
- App-native tracker CLI/GUI is the long-term tracking direction
- Job Radar ID is app-owned identity; URLs are evidence, not tracker primary keys

## Completed milestones

Completed so far:

- Project scaffold
- Greenhouse collector
- Lever collector
- Ashby collector
- Workday collector
- USAJobs collector
- iCIMS collector
- Jibe collector
- Jobsyn collector
- Oracle HCM collector
- SmartRecruiters collector
- SelectMinds collector
- Phenom collector
- Dayforce collector
- ADP Workforce Now collector
- Activate collector support
- WEKA custom collector
- HTML job-link collector
- SQLite storage
- Scan/report pipeline
- Markdown reports
- HTML reports
- Email preview
- Guarded email send path
- Location classification
- Recommendation sections
- Review Needed section
- Top Match eligibility
- Northern Colorado Highlights
- History import
- Simplified Job Log import
- Generated Job Radar IDs for scanned postings
- Job Radar ID display in Markdown, HTML, and email-preview reports
- Exact Job Radar ID history matching
- Guarded fuzzy history matching
- History context summary
- Track Status recommendation routing
- Tracked Applications full-report section
- Tracked applications excluded from Top Matches, Review Needed, and email summaries
- Production Kubernetes Top Match demotion
- Omitted jobs audit summary
- Application tracker storage
- Application tracker CLI add/update/list workflow
- Tracker applied date and last activity date support
- Tracker workflow-state classification
- Tracker needs-action and needs-review filters
- Tracker action summary in reports
- Tracker workflow summary in reports
- Read-only tracker GUI
- Tracker GUI workflow filters
- Tracker GUI search
- Tracker GUI raw status filters
- Tracker GUI raw outcome filters
- Tracker GUI combined workflow/search/status/outcome/sort review
- Tracker GUI applied-date sorting
- Tracker GUI company sorting
- Tracker GUI role sorting
- Tracker GUI status sorting
- Tracker GUI outcome sorting
- History GUI search
- History GUI decision filters
- History GUI outcome filters
- History GUI combined search/filter/sort review
- History GUI date sorting
- History GUI company sorting
- History GUI role sorting
- History GUI decision/status sorting
- History GUI outcome sorting
- GUI reports page for existing generated reports and email previews
- In-app report viewer
- Controlled GUI scan execution with email sending disabled
- Duplicate GUI scan prevention
- Tracker GUI edit form
- Tracker GUI quick actions
- Tracker GUI manual add form
- Import classification by Decision and Outcome
- Tracker/History mutual-exclusion import partitioning
- Canonical tracker values in storage and GUI display
- Tracker module file rename to `tracker_models.py`, `tracker_storage.py`, and `tracker_service.py`
- CLI module entrypoint support
- Main application settings aligned to `config/settings.yaml`
- Private AI session prompt ignored by Git
- File map updated for tracker and GUI boundaries
- Tracker terminal outcomes move active applications into history from the GUI
- History rows can be edited from the GUI
- History rows can move back to tracker from the GUI when reopened
- Tracker rows can be deleted from the GUI
- History rows can be deleted from the GUI
- Tracker/history workflow actions moved out of `web_app.py` into GUI-neutral service functions
- Profile/resume GUI page
- Resume upload and replacement from the GUI
- PDF resume loading
- DOCX resume loading
- GUI report viewer dark-style integration
- Shared GUI layout consistency improvements
- Home dashboard tracker summary
- Clickable Home dashboard tracker cards
- Tracker workflow summary cards
- Clickable tracker summary filter cards
- Active tracker filter card highlighting
- Tracker Needs Review queue guidance
- Tracker workflow badges
- Grouped tracker quick actions
- Tracker quick action to refresh activity today
- Tracker quick action to schedule follow-up next week
- Tracker quick action to mark follow-up due
- Manual validation of tracker/history movement and count updates
- History archive summary cards
- History quick filters for applied, passed, rejected, withdrawn, and closed-before-application records
- Rejected history quick filter covering both rejection outcomes
- Withdrawn history quick filter matching both withdrawn decision and withdrawn outcome
- History chip styling for archive type, decision/status, and outcome
- Reports latest scan result shortcut cards
- Scan completion direct links to HTML report, Markdown report, and email preview
- Report viewer Copy report text button
- Report viewer Ctrl+A report-content selection when focused
- Collector Errors report reassurance for temporary source/network failures
- Scan page reassurance for temporary company/source errors
- Read-only Companies page showing configured target companies, source types, enabled status, source details, notes, filters, and per-company detail pages
- Read-only Settings page showing runtime paths, retention settings, GUI scan defaults, and email status
- Manual tracker add form now assigns Job Radar ID on save instead of asking the user
- Spreadsheet-imported active applications without a Job Radar ID now receive app-owned `jr_manual_*` IDs
- Existing `posting-url:*` tracker IDs are repaired to app-owned `jr_manual_*` IDs
- Tracker edit summary layout now keeps Job Radar ID aligned with other summary cards and wraps long IDs
- `/tracker/` redirects to `/tracker`

## Known limitations

Current limitations:

- Job Radar still imports spreadsheet history as a bridge for existing records and bulk intake, but GUI tracker/history search and filtering now cover the main review patterns previously handled with workbook filters.
- The tracker/history workflow service refactor is complete, but future GUI growth should continue keeping `web_app.py` focused on route/form/render/redirect behavior.
- Resume/profile GUI support now exists for resume upload/replacement, but broader profile/preference setup still requires config-file editing.
- Job Radar does not write enriched IDs or metadata back to the spreadsheet.
- Report scoring is still rules-based and may need calibration from real outcomes.
- Source coverage is broad enough for current use, but individual collectors may still need maintenance if ATS pages change.
- The email report is intentionally limited and does not include every detail from the full Markdown/HTML reports.
- Kubernetes deployment is not complete.
- LLM integration is not implemented yet.
- The Flask GUI is local/basic and not yet productionized.

## Not in scope right now

Do not work on these unless explicitly requested:

- New source expansion
- Broad scoring rewrite
- Spreadsheet write-back
- LLM integration
- Employer/contact automation
- Production web authentication
- Kubernetes deployment
- Large GUI styling overhaul
