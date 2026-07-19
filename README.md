# junior

junior is a local-first job discovery, triage, reporting, and application-tracking tool.

It scans configured company career sites, normalizes and scores job postings, stores results in SQLite, and provides a local Flask interface for reviewing results, tracking active applications, and preserving application history.

junior does **not** apply to jobs automatically, contact employers, scrape LinkedIn, bypass authentication, or broadly crawl the internet.

## Status

- Current version: `0.1.0`
- MVP completed and acceptance-tested: July 14, 2026
- Current development branch: `feature/productization-foundation`
- Python requirement: 3.11 or newer

The current release is a functional single-user local application. Python wheel and source-package validation are complete. A standalone executable, installer, guided setup, editable configuration, scheduling, backup/export, and broader release-readiness work are still in progress.

See [CHANGELOG.md](CHANGELOG.md) for released and unreleased changes.

## Current capabilities

junior currently provides:

- configured-company scanning across multiple ATS and career-site formats
- SQLite-backed scan results, active applications, and application history
- rules-based scoring, recommendation policy, compensation checks, and resume/profile matching
- structured scan snapshots and HTML reports
- plain-text and HTML email previews with guarded SMTP delivery
- a local Flask GUI with Home, Scan, Reports, Active Applications, Application History, Profile / Resume, Companies, and Settings pages
- GUI-managed profile creation, editing, selection, reversible archival, and app-owned resume storage
- GUI-managed Search Preferences for saving profile-owned role, location, workplace, schedule, compensation, and travel selections without changing the existing scoring rules
- tracker workflow states, follow-up dates, quick actions, archive/restore workflows, and guarded deletion
- scan lifecycle records, progress state, cross-process locking, stage-specific failures, and bounded pagination
- user-owned runtime paths and non-destructive configuration/database bootstrap
- versioned SQLite migrations, foreign-key enforcement, atomic tracker/history moves, and backup-before-migration protection
- clean wheel installation and installed-package rendering tests

Application History is a permanent app-native feature. It is stored in SQLite and remains available for review, filtering, scan-time matching, prior-decision context, reporting, and tracker/history restoration workflows.

## Quick start for development

```powershell
cd C:\dev\job-radar
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
python -m job_radar.web_app --settings config\settings.yaml
```

Open:

```text
http://127.0.0.1:5000/
```

The installed console entry point is also available:

```powershell
job-radar-web --settings config\settings.yaml
```

## Common commands

Validate configuration:

```powershell
python -m job_radar validate --config config\target-companies.yaml --settings config\settings.yaml --scoring config\scoring.yaml
```

Run a scan:

```powershell
python -m job_radar scan --config config\target-companies.yaml --settings config\settings.yaml --report reports\target-scan.html --email-preview reports\target-email-preview.txt
```

Summarize application history:

```powershell
python -m job_radar history summary --settings config\settings.yaml
```

List active applications:

```powershell
python -m job_radar tracker list --settings config\settings.yaml
```

Create a new user-owned junior workspace:

```powershell
python -m job_radar bootstrap-user-data
```

This creates safe starter settings, an empty company list, and starter scoring rules. It does not copy a profile, résumé, database, credentials, or the repository's live company list.

Existing settings, companies, scoring rules, profiles, or a database can be brought over only by supplying the matching optional `--source-*` argument.

junior uses bootstrapped user settings by default when they are present. The established `JOB_RADAR_DATA_DIR` compatibility name remains unchanged so existing installations and user data continue to work.

## Validation

Run Ruff:

```powershell
python -m ruff check job_radar tests
```

Run the full test suite:

```powershell
python -m pytest -q tests
```

Packaging validation is covered by `tests/test_packaging.py`, including clean-wheel installation, installed desktop-launcher startup, and installed web rendering outside the source tree.

## Configuration and private data

Safe starter files included in the install package:

- `job_radar/bootstrap_defaults/settings.yaml`
- `job_radar/bootstrap_defaults/scoring.yaml`
- `job_radar/bootstrap_defaults/target-companies.yaml`

Development and live-validation configuration remains under `config/` and is not used as the installed application's automatic starting data.

Runtime databases, reports, logs, private settings, resumes, profiles, and credentials must remain outside source control.

Managed profiles and uploaded resumes are stored inside junior's user-data area. Uploaded resume files receive stable app-owned names, so renaming or moving the original file does not break the active profile. Existing YAML profiles remain supported when no managed profile is selected; junior does not automatically migrate or replace them.

A controlled migration service can prepare an existing YAML profile for managed storage, but migration is not automatic or exposed as a normal GUI action yet. It creates a private recovery bundle containing the source profile, resume files, and a consistent SQLite backup before creating or selecting the managed profile. Real user-data migration requires a separate backup-and-rehearsal step and explicit approval.

The Search Preferences page builds and saves the active managed profile junior will eventually use to evaluate jobs during targeted company scans. The page does not run a search and is not a broad job-board filter. It stores normalized occupation identities, structured U.S. locations and commute radii, job levels, employment types, schedule, workplace arrangements, minimum compensation, and travel percentage in SQLite. Selected locations use approximate straight-line distance to define acceptable hybrid and on-site commutes. Truly remote jobs ignore commuting distance, while an employer's remote residency restriction must match a location where the user lives or genuinely plans to move. These saved preferences do not yet replace or modify the existing scoring and recommendation rules. Occupation suggestions use the O*NET 30.3 Database under CC BY 4.0; location suggestions and radius coverage use the U.S. Census Bureau 2025 Gazetteer Files, with display prioritization from the Census Bureau Vintage 2025 Population Estimates. junior includes only the reference fields needed by this workflow and has modified their packaging and presentation.

A successful scan writes fixed-name outputs in the user-owned `reports` directory. The current HTML report and email preview replace the previous versions. The structured JSON snapshot supports the application internally and is not presented as a separate user report. Configurable report history and retention are not implemented yet.

SMTP passwords must not be stored in YAML, SQLite, logs, reports, previews, bootstrap files, packages, or source control. Environment variables remain the supported credential mechanism for the current implementation.

## Database upgrade recovery

Before changing an existing database structure, junior creates a backup in the `backups` directory beside the active database. The established default Windows location remains `%LOCALAPPDATA%\JobRadar\data\backups`. Backup filenames identify the database and migration range, for example `job_radar.sqlite3.pre-migration-v1-v3-<timestamp>.bak`.

If junior reports an upgrade failure, close junior and do not delete, rename, replace, or repeatedly reopen the active database or its backups. Preserve the complete `data` directory and contact Clayton Graves at `claytonmgraves@outlook.com`. Include the displayed technical details and diagnostic-log location, but do not send the database, résumé, profile, passwords, access tokens, or other credentials unless an approved secure support process is provided.

junior does not yet provide self-service restore controls. Do not manually replace the active database with a backup unless the replacement has first been copied to a separate recovery location and validated through the supported recovery process.

## Documentation

- [User Guide](docs/USER_GUIDE.md)
- [Development Guide](docs/DEVELOPMENT.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Security and Privacy](docs/SECURITY.md)
- [Roadmap](docs/ROADMAP.md)
- [Release Checklist](docs/RELEASE_CHECKLIST.md)
- [Changelog](CHANGELOG.md)

## Product boundaries

junior is designed to remain:

- local-first and user-controlled
- based on configured companies rather than broad crawling
- transparent in scoring and recommendations
- safe for manual review
- independent of automatic applications or recruiter outreach
- usable through one shared service layer across CLI, browser, packaged, and service modes

The long-term target is a configurable cross-platform application that a non-developer can install, launch, configure, and operate without editing source files by hand.
