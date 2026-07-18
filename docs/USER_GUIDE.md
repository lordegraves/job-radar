# Job Radar User Guide

This guide describes the current local application. It does not assume that installer or first-run onboarding work is complete.

## First-time setup

Create a user-owned Job Radar workspace:

```powershell
python -m job_radar bootstrap-user-data
```

This creates:

- safe starter settings
- an empty company list
- starter scoring rules
- empty data, profile, report, and log directories

It does not copy a personal profile, résumé, database, credentials, or live company list.

Existing Job Radar data can be brought over deliberately with the optional `--source-settings`, `--source-companies`, `--source-scoring`, `--source-profiles`, and `--source-database` arguments. Existing destination files are always preserved.

## Launching the application

From an activated development environment:

```powershell
python -m job_radar.web_app --settings config\settings.yaml
```

Open `http://127.0.0.1:5000/`.

When bootstrapped user settings exist, Job Radar can use them by default:

```powershell
python -m job_radar.web_app
```

## Home

The Home page summarizes the latest scan and active application work.

It includes:

- latest scan status
- Top Matches, Review Needed, Tracked Applications, New Jobs, and Collector Errors
- active workflow counts
- follow-ups due
- applications needing date review
- stale or dormant records
- recently active applications

Dashboard cards link to focused views rather than duplicating entire reports.

## Scan

The Scan page runs the shared scan pipeline.

A scan:

1. loads settings, company sources, scoring configuration, profile, and resume
2. acquires the cross-process scan lock
3. creates a durable scan-run record
4. collects and normalizes postings
5. scores jobs and applies recommendation policy
6. loads tracker and application-history context
7. stores postings and structured results
8. writes the HTML report, structured snapshot, and email preview
9. records completion or stage-specific failure

Occasional company or network errors may be temporary. The interface preserves error details and does not imply that one collector failure invalidates the entire scan.

## Reports

The Reports page emphasizes the latest scan results.

Current primary outputs are:

- HTML scan report
- structured JSON snapshot used by the GUI
- plain-text email preview

Older or additional files in the reports directory may also be displayed. Retention settings are not yet fully user-configurable through the GUI.

## Active Applications

Active Applications is the source of truth for live application tracking.

Typical actions include:

- add a manual application
- search, sort, and filter records
- update status, outcome, and dates
- record follow-up dates and notes
- use workflow-aware quick actions
- move terminal applications to Application History
- delete a record through explicit confirmation

Job Radar assigns app-owned IDs to manual records. Posting URLs remain source evidence, not primary identity.

## Application History

Application History is a permanent SQLite-backed part of Job Radar.

History contains terminal, passed, withdrawn, rejected, closed, and archived records. It supports:

- search, sorting, and filters
- record detail and editing
- prior-decision context during scans
- history summaries
- restoration to Active Applications
- preservation of company, role, URL, source/contact context, notes, and workflow dates

Tracker and History are mutually exclusive. A record should not exist in both at the same time.

## Profile / Resume

The Profile / Resume page shows candidate readiness and resume-derived fit information.

Supported resume formats:

- PDF
- DOCX
- Markdown
- plain text

Resume replacement is written to the active user-data area. Private resumes and profiles must not be committed to the repository.

## Companies

The current Companies pages are read-only.

They show configured company names, source types, enabled state, source details, notes, filters, search, and per-company detail views.

Company add/edit/disable workflows are future productization work.

## Settings

The current Settings page is read-only.

It surfaces active runtime paths, the current latest-scan-only report policy, scan defaults, profile paths, and email readiness without displaying secrets.

## Email

Email delivery requires explicit configuration and an explicit send action.

The application can still launch and perform unrelated work when email is disabled or a credential is unavailable.

SMTP password values must be supplied through a supported credential source. The current implementation supports environment-variable references and must never store the password value in YAML, SQLite, logs, reports, previews, or source control.

## CLI fallbacks

Summarize history:

```powershell
python -m job_radar history summary --settings config\settings.yaml
```

List applications:

```powershell
python -m job_radar tracker list --settings config\settings.yaml
```

List records needing action:

```powershell
python -m job_radar tracker list --needs-action --settings config\settings.yaml
```

The CLI remains useful for validation, testing, automation, and fallback operation. The GUI is the normal daily interface.
