# junior User Guide

This guide describes the current local application. It does not assume that installer or first-run onboarding work is complete.

## First-time setup

Create a user-owned junior workspace:

```powershell
python -m job_radar bootstrap-user-data
```

This creates:

- safe starter settings
- an empty company list
- starter scoring rules
- empty data, profile, report, and log directories

It does not copy a personal profile, résumé, database, credentials, or live company list.

Existing junior data can be brought over deliberately with the optional `--source-settings`, `--source-companies`, `--source-scoring`, `--source-profiles`, and `--source-database` arguments. Existing destination files are always preserved.

## Launching the application

The current installed desktop-style entry point is:

```powershell
job-radar-desktop
```

It creates the user-owned workspace when needed, starts junior locally, waits for the interface to become ready, and opens the default browser. If junior is already running on the selected local address, the launcher reuses that instance instead of starting another server.

This is a browser-opening launcher, not the final native desktop window or Windows installer. Those remain future productization work.

From an activated development environment:

```powershell
python -m job_radar.web_app --settings config\settings.yaml
```

Open `http://127.0.0.1:5000/`.

When bootstrapped user settings exist, junior can use them by default:

```powershell
python -m job_radar.web_app
```

## Database upgrade recovery

junior creates a backup before changing an existing database structure. The established default Windows workspace remains `%LOCALAPPDATA%\JobRadar`, and migration backups are stored in its `data\backups` directory.

If an upgrade fails:

1. Close junior.
2. Do not delete, rename, replace, or repeatedly reopen the active database or any backup.
3. Preserve the complete junior `data` directory.
4. Contact Clayton Graves at `claytonmgraves@outlook.com` with the displayed technical details and diagnostic-log location.

Do not send your database, résumé, profile, passwords, access tokens, or other credentials unless an approved secure support process is provided. junior does not currently provide a self-service restore screen, so do not manually replace the active database with a backup.

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

Starting a scan from this page returns control immediately. You may continue using other junior pages while the scan runs. A status indicator remains available throughout the interface, and junior displays an app-wide notification when the scan completes, completes with source warnings, or fails. The notification links to the latest results or scan details.

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

The Reports page opens the latest successful scan outputs.

Current scan artifacts are:

- HTML scan report — the primary user-facing report
- plain-text email preview — the message that can be reviewed before delivery
- structured JSON snapshot — internal structured data used by the application

Each successful scan replaces the previous fixed-name outputs. The Reports page does not expose arbitrary files from the reports directory. Configurable report history and retention are planned but are not implemented yet.

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

junior assigns app-owned IDs to manual records. Posting URLs remain source evidence, not primary identity.

## Application History

Application History is a permanent SQLite-backed part of junior.

History contains terminal, passed, withdrawn, rejected, closed, and archived records. It supports:

- search, sorting, and filters
- record detail and editing
- prior-decision context during scans
- history summaries
- restoration to Active Applications
- preservation of company, role, URL, source/contact context, notes, and workflow dates

Tracker and History are mutually exclusive. A record should not exist in both at the same time.

## Profile / Resume

The Profile / Resume page shows candidate readiness and resume-derived fit information. It also allows you to create, edit, select, archive, and restore managed profiles without editing YAML. Archiving is reversible; permanent profile deletion is not currently offered.

When a managed profile is selected, future scans use its candidate-fit signals, compensation values, and managed resume. If no managed profile is selected, the existing YAML profile remains in use. junior does not automatically convert, overwrite, or remove an existing YAML profile.

Supported resume formats:

- PDF
- DOCX
- Markdown
- plain text

Resume replacement is written to the active user-data area. For a managed profile, junior copies the upload under `resumes/<profile-id>/` using an app-owned filename such as `resume.pdf`; moving or renaming the original uploaded file cannot break the profile. To use a revised resume, upload it again through the Profile / Resume page. Private resumes and profiles must not be committed to the repository.

Managed profiles can retain additional preferences for later product stages. Target roles, locations, work arrangements, employment types, and travel tolerance do not yet replace the existing scoring configuration, so saving those fields alone does not currently change all scan-scoring behavior.

Existing YAML profiles are not migrated automatically. junior now has an internal backup-first migration service, but it is not yet a normal GUI action. Do not manually move, rename, delete, or rewrite your working profile, resume, or database in an attempt to migrate it. Migration of real data should occur only after a rehearsal on copies and an explicit backup confirmation.

## Companies

The current Companies pages are read-only.

They show configured company names, source types, enabled state, source details, notes, filters, search, and per-company detail views.

Company add/edit/disable workflows are future productization work.

## Settings

The current Settings page is read-only.

It surfaces active runtime paths, the current latest-scan-only report policy, scan defaults, profile paths, and email readiness without displaying secrets.

## Email

Email delivery requires explicit configuration and the CLI `--send-email` option. The GUI Scan page currently creates the email preview but does not send email.

To run a scan and deliberately request configured SMTP delivery:

```powershell
python -m job_radar scan --config config\target-companies.yaml --settings config\settings.yaml --report reports\target-scan.html --email-preview reports\target-email-preview.txt --send-email
```

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
