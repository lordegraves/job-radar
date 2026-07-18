# Architecture

## Overview

Job Radar is one local-first Python application with multiple launch surfaces:

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
- A future native desktop shell may wrap the shared Flask interface, but it must not duplicate application rules.
- Future unattended Windows, Linux, container, and Kubernetes modes must call the same scan and storage services.

## Startup and shutdown flow

The web application resolves runtime paths, loads settings, initializes or migrates the SQLite database, and then registers feature routes. Startup failures are converted into safe user-facing messages, with sanitized diagnostics written under the user-owned logs directory when possible.

The desktop launcher first checks whether Job Radar already responds at its configured local address. If so, it opens the existing interface. Otherwise, it ensures the user-owned workspace exists, creates the Flask application, starts a local server, waits for readiness, and opens the browser.

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
- managed profile identity, preferences, company associations, and app-owned resume metadata

`database.py` owns connections and transaction behavior. `storage.py` owns general persistence. Tracker persistence lives under `job_radar/tracker/`.

Database protections include:

- migration version tracking
- foreign-key enforcement
- backup before schema migration
- atomic tracker/history moves
- compatibility migrations for older databases

Managed profile storage currently exists as an internal foundation and is not yet connected to profile selection, scans, or GUI profile management. Migration of an existing candidate profile and assignment of existing operational records will occur only after those workflows are complete and validated against temporary copies.

### Tracker and History

Active Applications and Application History are separate but related workflows.

Rules:

- active records belong in Tracker
- terminal, passed, withdrawn, rejected, closed, or archived records belong in History
- a record should not exist in both
- movement between them must be transactional
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

Each successful scan replaces the previous fixed-name outputs. Arbitrary files in the reports directory are not part of the normal Reports-page interface. Configurable report history, retention, and rotation remain future product work.

Databases belong in `data`, logs belong in `logs`, and migration backups are safety artifacts rather than user reports. None of these runtime artifacts belong in source control or release packages.

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

Scanned postings receive stable Job Radar IDs.

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
