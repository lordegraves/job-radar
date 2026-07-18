# Architecture

## Overview

Job Radar is one local-first Python application with multiple launch surfaces:

```text
CLI
Flask web interface
future packaged desktop launcher
future unattended service/container mode
```

These surfaces must share the same service and storage layers rather than becoming separate products.

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

The user-data root contains separate `config`, `profiles`, `data`, `reports`, and `logs` directories.

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

`database.py` owns connections and transaction behavior. `storage.py` owns general persistence. Tracker persistence lives under `job_radar/tracker/`.

Database protections include:

- migration version tracking
- foreign-key enforcement
- backup before schema migration
- atomic tracker/history moves
- compatibility migrations for older databases

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
job_radar/tracker/      tracker storage and workflow services
job_radar/web_routes/   Flask feature routes
job_radar/templates/    Jinja templates
tests/                  unit, integration, web, and packaging tests
scripts/                operational helpers
data/ reports/ logs/    ignored runtime output roots
```
