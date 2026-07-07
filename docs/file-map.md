# Job Radar File Map

This document maps the current Job Radar repository so the project stays understandable as it grows.

## Root Files

| File | Purpose | Keep / Review |
|---|---|---|
| `.gitignore` | Keeps local runtime data, generated reports, credentials, caches, and build artifacts out of Git. | Keep |
| `README.md` | Main project overview and usage documentation. | Keep |
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

## Runtime Data

| File / Pattern | Purpose | Keep / Review |
|---|---|---|
| `data/.gitkeep` | Preserves the runtime data directory in Git. | Keep |
| `data/*.sqlite3` | Local runtime databases. | Local only / ignored |
| `data/*.db` | Local runtime databases. | Local only / ignored |
| `data/*.xlsx` | Local spreadsheet inputs, including current job history import files. | Local only / ignored |

## Examples

| File | Purpose | Keep / Review |
|---|---|---|
| `examples/job-history-template.xlsx` | Sanitized example workbook for the simplified Job Log import format. Contains headers, formatting, validation lists, and one fake sample row. | Keep |

## Documentation

| File | Purpose | Keep / Review |
|---|---|---|
| `docs/current-state.md` | Current project state and milestone notes. | Keep |
| `docs/product-roadmap.md` | Product direction, finish-line definition, user-configuration requirements, packaging roadmap, and platform roadmap. | Keep |
| `docs/file-map.md` | Repository map and file ownership guide. | Keep |

## Core Application Package

| File | Purpose | Keep / Review |
|---|---|---|
| `job_radar/__init__.py` | Package marker. | Keep |
| `job_radar/__main__.py` | Allows running the package with `python -m job_radar`. | Keep |
| `job_radar/cli.py` | Command-line entry points and user-facing commands. | Keep / watch growth |
| `job_radar/config.py` | Loads and validates app configuration. | Keep |
| `job_radar/models.py` | Core shared data models such as job postings. | Keep |
| `job_radar/storage.py` | SQLite persistence for collected/scored job data. | Keep |
| `job_radar/validation.py` | Validation helpers. | Keep |
| `job_radar/normalize.py` | Text/key normalization helpers. | Keep |

## Profile, Resume, and Match Context

| File | Purpose | Keep / Review |
|---|---|---|
| `job_radar/candidate_profile.py` | Candidate preference/profile loading and interpretation. | Keep |
| `job_radar/resume_loader.py` | Loads resume/profile text for matching. | Keep |
| `job_radar/resume_match.py` | Resume-to-posting match logic. | Keep |
| `profiles/clayton/profile.yaml` | Clayton-specific target profile and avoid/preference signals. | Keep / review before public release |
| `profiles/clayton/resume.md` | Clayton-specific resume source used by Job Radar. | Keep / review before public release |
| `profiles/clayton/resume.normalized.txt` | Normalized resume text for matching. | Keep / review whether generated |

## Scoring, Recommendations, and History

| File | Purpose | Keep / Review |
|---|---|---|
| `job_radar/scoring.py` | Base score calculation and top-match eligibility signals. | Keep |
| `job_radar/recommendations.py` | Technical match, hiring probability, risk flags, recommended actions, and display eligibility. | Keep / watch growth |
| `job_radar/recommendation_constants.py` | Shared labels for actions, risks, recommendation ordering, and history reasons. | Keep |
| `job_radar/compensation.py` | Compensation parsing and compensation-floor evaluation. | Keep |
| `job_radar/job_history.py` | Imports and represents external job/application history from the spreadsheet bridge. | Keep |
| `job_radar/history_match.py` | Matches current postings against prior application/review history. | Keep |
| `job_radar/history_context.py` | Adds history context to scored postings/reports. | Keep |
| `job_radar/history_summary.py` | Summarizes imported history for reports. | Keep |

## Application Tracker

| File | Purpose | Keep / Review |
|---|---|---|
| `job_radar/tracker/__init__.py` | Tracker package marker. | Keep |
| `job_radar/tracker/tracker_models.py` | Application tracker data model. | Keep |
| `job_radar/tracker/tracker_storage.py` | SQLite persistence for application tracker records. | Keep |
| `job_radar/tracker/tracker_service.py` | Tracker workflow classification, tracker/history conversion, tracker/history update and delete workflow actions, import partitioning, and tracker business rules. | Keep |

## Reporting and Email

| File | Purpose | Keep / Review |
|---|---|---|
| `job_radar/reporting.py` | Markdown/HTML report rendering and report section logic. | Keep / watch growth |
| `job_radar/email_summary.py` | Email subject/body/HTML preview generation. | Keep / watch growth |
| `job_radar/email_sender.py` | Email delivery integration. | Keep |
| `reports/.gitkeep` | Preserves generated reports directory in Git. | Keep |
| `reports/*` | Generated reports, previews, audits, probes, and local run output. | Local only / ignored |

## Web App / GUI

| File | Purpose | Keep / Review |
|---|---|---|
| `job_radar/web_app.py` | Flask web application entry point and GUI route handlers. Route handlers should delegate tracker/history workflow actions to service-layer functions. | Keep / watch growth |
| `job_radar/templates/index.html` | Web app landing page. | Keep |
| `job_radar/templates/tracker.html` | Application tracker list, workflow filters, search, sorting, workflow display, and edit links. | Keep |
| `job_radar/templates/tracker_edit.html` | Application tracker edit form and quick actions. | Keep |
| `job_radar/templates/tracker_add.html` | Manual application tracker add form. | Keep |
| `job_radar/templates/history.html` | Job history/archive page for archived/history records, including search, filtering, sorting, and edit links. | Keep |
| `job_radar/templates/history_edit.html` | Job history edit form, including save, delete, and move-back-to-tracker workflow. | Keep |
| `job_radar/templates/reports.html` | Reports page for viewing existing generated reports and email previews. | Keep |
| `job_radar/templates/report_view.html` | In-app report viewer shell for opening generated reports inside the GUI. | Keep |
| `job_radar/templates/scan.html` | Scan page for manual command display and controlled local GUI scan execution. | Keep |

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
| `job_radar/collectors/jobsyn.py` | JobSyn collector. | Keep |
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

## Logs

| File / Pattern | Purpose | Keep / Review |
|---|---|---|
| `logs/.gitkeep` | Preserves log directory in Git. | Keep |
| `logs/*.log` | Runtime logs. | Local only / ignored |
| `logs/*.log.*` | Rotated runtime logs. | Local only / ignored |

## Tests

Collector tests intentionally mirror collector files. This makes source-specific failures easier to identify.

| Test Area | Files | Keep / Review |
|---|---|---|
| Collector tests | `tests/test_*_collector.py`, plus `tests/test_collector_registry.py` | Keep |
| Config/CLI/storage tests | `tests/test_config.py`, `tests/test_cli.py`, `tests/test_storage.py` | Keep |
| Scoring/recommendation/report tests | `tests/test_scoring.py`, `tests/test_reporting.py`, `tests/test_email_summary.py` | Keep |
| Profile/resume/history tests | `tests/test_candidate_profile.py`, `tests/test_resume_loader.py`, `tests/test_resume_match.py`, `tests/test_job_history.py`, `tests/test_history_match.py`, `tests/test_history_context.py`, `tests/test_history_summary.py` | Keep |
| Tracker tests | `tests/test_tracker_service.py`, `tests/test_tracker_storage.py` | Keep |
| Web app tests | `tests/test_web_app.py` | Keep |
| Utility tests | `tests/test_normalize.py`, `tests/test_compensation.py`, `tests/test_email_sender.py` | Keep |
| Integration tests | `tests/test_phase1a_integration.py` | Keep |

## Current Simplification Guidance

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

## Tracker / GUI Boundary

The spreadsheet is being phased out as the normal application-tracking interface. It remains a bridge for import/history data, but active application tracking now has a dedicated tracker module and a basic Flask GUI.

Current tracker structure:

```text
job_radar/tracker/
  __init__.py
  tracker_models.py
  tracker_storage.py
  tracker_service.py
```


Current web UI structure:

```text
job_radar/web_app.py
job_radar/templates/
  index.html
  tracker.html
  tracker_edit.html
  tracker_add.html
  history.html
  history_edit.html
  reports.html
  report_view.html
  scan.html
```

The tracker service owns application status/decision, follow-up timing, active outcomes, notes, workflow state, manual application tracking rules, tracker-to-history movement, history-to-tracker movement, and tracker/history delete workflow actions.

The spreadsheet/history importer owns external history intake, partitioning between active tracker records and archived history records, and historical context. The history GUI owns review/display controls for archived history. The spreadsheet should not be treated as the long-term source of truth for active application workflow.

Tracker and History are now expected to be mutually exclusive. Active rows belong in the tracker. Terminal, passed, withdrawn, rejected, closed, or archived rows belong in history.

The tracker should not be mixed into report rendering or collector code.

Future GUI growth should keep `job_radar/web_app.py` small by moving workflow/business logic into GUI-neutral service functions. If route/template volume keeps growing, split the Flask interface into a dedicated web package before it becomes hard to maintain.

The long-term packaging direction is:

```text
Windows packaged app
Linux packaged app
container/server mode
```

These launch targets should share the same service layer instead of becoming separate products.
