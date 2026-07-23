# Architecture

## Overview

junior is one local-first Python application with multiple launch surfaces:

```text
Developer and automation CLI
Local Flask web interface
Browser-opening desktop launcher
Future native desktop shell and installer
Future unattended service/container mode
```

These surfaces must share the same service and storage layers rather than becoming separate products.

## Entry points and operating modes

- `job-radar` / `job_radar.cli`: developer, automation, validation, scan, history, database, and tracker commands.
- `job-radar-web` / `job_radar.web_app`: local browser/server mode. An explicit settings path may be supplied; otherwise runtime-path resolution selects bootstrapped user settings when present and falls back to repository settings for development compatibility.
- `job-radar-desktop` / `job_radar.desktop_launcher`: the current desktop-style launcher. It prepares packaged user configuration when needed, starts a local Werkzeug server, waits for readiness, and opens the default browser.
- `job-radar-scheduled` / `job_radar.scheduled_scan`: the unattended scan entry point. It reads the saved schedule, exits safely when scheduling is off, and calls the same scan service used by GUI and CLI scans.
- A future native desktop shell may wrap the shared Flask interface, but it must not duplicate application rules.
- Windows Task Scheduler and Linux systemd user timers invoke the shared scheduled entry point. Future container and Kubernetes modes must call the same scan and storage services.

## Startup and shutdown flow

The web application resolves runtime paths, loads settings, initializes or migrates the SQLite database, and then registers feature routes. Startup failures are converted into safe user-facing messages, with sanitized diagnostics written under the user-owned logs directory when possible.

The desktop launcher first checks whether junior already responds at its configured local address. If so, it opens the existing interface. Otherwise, it ensures the user-owned workspace exists, creates the Flask application, starts a local server, waits for readiness, and opens the browser.

The current launcher stops its server when its process exits or startup fails, but it does not yet provide a native application window, a GUI Exit command, focus an existing native window, or manage an unattended background service. Complete shutdown controls and service lifecycle integration remain future product work.

## Major layers

### Configuration and runtime paths

- `config.py` loads typed application settings.
- `runtime_paths.py` resolves repository or user-owned paths.
- `user_data_bootstrap.py` creates and populates user-owned storage without replacing existing files.
- `bootstrap_defaults/` contains the safe starter settings, empty company list, and starter scoring rules included in installed packages.

`JOB_RADAR_DATA_DIR` is the supported explicit runtime-root override.

Default user-data roots:

- Windows: `%LOCALAPPDATA%\JobRadar`
- Linux and other POSIX systems: `$XDG_DATA_HOME/job-radar` or `~/.local/share/job-radar`

The user-data root contains separate `config`, `profiles`, `resumes`, `data`, `reports`, and `logs` directories. Managed resume files use app-owned names under `resumes/<profile-id>/` so moving or renaming the original uploaded file cannot break an active profile.

A normal bootstrap uses only packaged starter files. Repository profiles, resumes, databases, live company configuration, and credentials are not automatic bootstrap sources. Existing data is migrated only when the user supplies an explicit source argument.

Imported settings are parsed before copying. Literal password, token, API-key, credential, or secret values are rejected, while references such as `smtp_password_env` remain allowed.

### Collection

Source-specific collectors live under `job_radar/collectors/`.

`registry.py` maps configured source types to collectors. `collector_http.py` and `pagination.py` own shared request and bounded-pagination behavior.

Collectors return normalized posting data and should not own scoring, tracker, history, or reporting rules.

### Scan lifecycle

`scan_service.py` owns the shared scan pipeline.

The lifecycle includes:

- durable scan-run records
- progress updates
- cross-process locking
- stage-specific failure recording
- collector errors
- normalization and persistence
- scoring and recommendation policy
- tracker and history context
- structured snapshot generation
- HTML and email-preview outputs

CLI and GUI scan execution must call the same service.

### Scheduling

`schedule_service.py` owns the durable, application-wide schedule and scheduled-run summary. `scheduler_integration.py` selects the host integration without changing scan behavior. `windows_scheduler.py` manages only Junior's named Task Scheduler entry. `linux_scheduler.py` manages only Junior-marked systemd user service/timer files and rolls their prior contents back if systemd rejects an update. Both integrations invoke `scheduled_scan.py`; neither contains its own collection, scoring, report, or email rules.

Linux standalone use installs the marked units under the current user's systemd configuration. A server may run the same user timer under a dedicated service account and pass that account's explicit user-data root to `job-radar-scheduled`. System-wide packaging and service-account provisioning remain deployment concerns rather than a second scheduler implementation.

### Scoring and recommendation policy

Scoring and recommendation concerns are separated:

- `scoring.py`: base scoring and location classification
- `score_evidence.py`: structured scoring evidence
- `recommendation_policy.py`: Top Match and Review Needed eligibility
- `recommendations.py`: recommendation labels, risks, actions, and hiring probability
- `compensation.py`: compensation parsing and floor evaluation
- `resume_match.py`: resume-to-posting match signals

This separation prevents one numeric score from silently overriding policy constraints.

### Persistence

SQLite is the system of record for:

- job postings
- scan runs and errors
- active applications
- application history
- the installation-wide employer/source catalog and profile-specific employer selections
- managed profile identity, preferences, scoring/report settings, and app-owned resume metadata

`database.py` owns connections and transaction behavior. `storage.py` owns general persistence. Tracker persistence lives under `job_radar/tracker/`.

Database protections include:

- migration version tracking
- foreign-key enforcement
- backup before schema migration
- atomic tracker/history moves
- compatibility migrations for older databases

Managed profile storage is connected to GUI creation, editing, active-profile selection, guarded deletion, resume upload, and scan-time candidate matching. A selected managed profile takes priority; when none is selected, the existing YAML profile path continues to work unchanged.

Active Applications and Application History are profile-owned. Schema migrations assign legacy application records to the active, non-archived managed profile. If legacy application records exist without an eligible active profile, migration fails atomically instead of guessing an owner or creating a fallback profile. A profile that owns Tracker or History records cannot be deleted. Real-data migrations must first be rehearsed against temporary copies and separately approved.

The broader preference model can store target roles, locations, work arrangements, employment types, and travel tolerance, but those fields do not yet replace the existing scoring configuration. Current scan behavior consumes the managed profile's strengths, adjacent areas, gaps, exclusions, compensation values, and resume through the existing candidate-scoring boundary. Recommendation actions and risk labels do not contain global occupation, employer, title-family, or regional assumptions; those decisions come from the active profile, practical eligibility, resume evidence, and that profile's application history.

`profile_migration.py` owns the controlled legacy-YAML conversion boundary. Planning validates the source without creating the database, destination, or backup directory. Applying a plan refuses duplicate names, IDs, existing resume destinations, and backup paths outside the user-data root. It completes a private recovery bundle before creating managed files, preserves source files unchanged, and removes only newly created managed files if the database transaction fails. The migration service is internal until a guided migration or setup workflow is approved.

`backup_service.py` owns manual backup, readable export, and restore. Restorable bundles use a manifest with bounded paths, sizes, and SHA-256 checksums; SQLite is copied and restored through its online-backup API. Restore validates the staged database before touching active data and creates an independent pre-restore bundle first. Only known Junior-owned paths are accepted, symlinks and archive traversal are rejected, and credentials are excluded by remaining in the operating-system credential boundary. JSON export serializes database records for portability but deliberately omits résumé documents and is not accepted by restore.

Destructive services invoke safety backup at their ownership boundary. Managed-profile deletion creates a complete bundle after eligibility checks and before moving the résumé or deleting SQLite rows. Employer storage creates a validated SQLite-only backup after reference checks and immediately before its delete statement. Schema migration retains its established pre-migration copy. Future repair or reset operations must use the same boundary before they become available.

### Tracker and History

Active Applications and Application History are separate but related workflows.

Rules:

- active records belong in Tracker
- terminal, passed, withdrawn, rejected, closed, or archived records belong in History
- Tracker and History records belong to one managed profile
- the same durable job identity may exist independently in different profiles
- a record should not exist in both
- movement between them must be transactional
- movement between them must preserve profile ownership
- application dates and record details must survive round trips
- application history remains available for scan-time matching and context

Core files:

- `history_models.py`
- `history_match.py`
- `history_context.py`
- `history_summary.py`
- `tracker/tracker_models.py`
- `tracker/tracker_storage.py`
- `tracker/tracker_service.py`

The retired Excel importer is not part of the architecture.

### Reporting

Current report architecture:

- `report_models.py`: structured report data
- `report_snapshot.py`: persisted JSON snapshot
- `report_view_model.py`: shared display model
- `html_report.py`: HTML rendering
- `email_summary.py`: text and HTML email preview
- `email_sender.py`: guarded delivery

HTML is the primary user-facing report. The GUI reads structured data rather than parsing Markdown.

### Runtime artifacts and retention

Scan artifacts belong in the user-owned `reports` directory:

- the fixed-name HTML scan report is the primary user-facing report
- the fixed-name plain-text email preview supports review before delivery
- the fixed-name structured JSON snapshot supports application behavior and is not a separate user-facing report

The latest outputs keep stable filenames for compatibility. Before replacement, `retention_service.py` can copy and verify the prior known report set into a marked, timestamped directory under `reports/archive`. Retention supports latest only, latest plus previous, or a configured total from 1 through 50. Pruning accepts only strict Junior archive markers and dated-log filename patterns; arbitrary report directories, unrelated logs, and the active fixed-name startup log are never retention targets. `retention_settings_service.py` validates and atomically replaces only the known retention keys while preserving unknown settings.

Databases belong in `data`, logs belong in `logs`, and migration backups are safety artifacts rather than user reports. None of these runtime artifacts belong in source control or release packages.

### Diagnostics

`diagnostic_service.py` owns the shared safe vocabulary for configuration, collector, network, email, and unexpected application failures. Scan collection and terminal scan failures store only these bounded summaries and categories, never raw exception text. The read-only Settings diagnostics view combines the latest sanitized scan state, aggregated employer connection health, email readiness, and successful settings loading. Safe log access and operating-system navigation use the narrower service boundary below.

`diagnostic_log_service.py` extends that boundary with an allowlist for the fixed startup log and strictly named dated Junior logs. Listing is capped at 20 files and viewing reads only the newest 200,000 bytes. Resolved-path checks reject traversal, symlinks escaping the logs directory, arbitrary filenames, and non-log files. The copyable support summary contains version, schema, resolved user-data location, and health-card state only. The CSRF-protected data-directory action uses the active settings location to identify the owning workspace and passes it to the operating system without invoking a shell.

### Web interface

`web_app.py` creates the Flask application and registers route modules.

Feature routes live under `web_routes/`:

- companies
- history
- profile
- reports
- scan
- settings
- tracker

Templates render data prepared by routes and services. Business behavior should remain outside templates.

## Identity

Scanned postings receive stable app-owned Job Radar IDs. The established label remains for data compatibility during the branding transition.

Manual tracker records receive app-owned `jr_manual_*` IDs. Posting URLs are evidence and fallback matching signals, not primary keys.

Older `posting-url:*` tracker identities are repaired when tracker storage initializes.

## Ownership boundaries

Keep these concerns separate:

- collectors do not own scoring or tracker behavior
- scoring does not own final recommendation eligibility
- reporting does not own tracker workflow changes
- route handlers do not own business rules
- templates do not mutate configuration
- runtime bootstrap does not overwrite existing user data
- normal bootstrap does not copy repository profiles, databases, live company configuration, or credentials
- optional migration sources are explicit and imported settings containing literal credentials are rejected
- packages and release artifacts do not include private runtime data or credentials

## Repository shape

```text
config/                         development and live-validation configuration
job_radar/                      application package
job_radar/bootstrap_defaults/   safe installed starter configuration
job_radar/collectors/           source integrations
job_radar/tracker/              tracker storage and workflow services
job_radar/web_routes/           Flask feature routes
job_radar/templates/            Jinja templates
tests/                          unit, integration, web, and packaging tests
scripts/                        operational helpers
data/ reports/ logs/            ignored runtime output roots
```
