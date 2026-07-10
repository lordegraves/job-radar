# Job Radar File Map

Last updated: 2026-07-10

## Purpose

This document owns repository structure and file ownership boundaries.

It should not duplicate current project state, roadmap details, or milestone history. Current capabilities and commands belong in `README.md`. Future direction belongs in `docs/product-roadmap.md`.

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

## Documentation

| File | Purpose | Keep / Review |
|---|---|---|
| `README.md` | Canonical project overview, current state, commands, capabilities, principles, and verification. | Keep |
| `docs/product-roadmap.md` | MVP finish line, future direction, post-MVP roadmap, and deferred scope. | Keep |
| `docs/file-map.md` | Repository map and file ownership guide. | Keep |
| `docs/current-state.md` | Retired as a long-form state ledger. Replace with a short pointer to README or remove after consolidation. | Retire / stub |

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
| `job_radar/templates/index.html` | Web app landing page with clickable tracker dashboard cards and section navigation. | Keep |
| `job_radar/templates/tracker.html` | Application tracker list, clickable summary filter cards, workflow filters, search, sorting, workflow display, Needs Review guidance, workflow badges, and edit links. | Keep |
| `job_radar/templates/tracker_edit.html` | Application tracker edit form, summary cards with wrapping Job Radar ID display, and grouped quick actions for refreshing activity, scheduling follow-up, marking workflow state, and moving terminal records to history. | Keep |
| `job_radar/templates/tracker_add.html` | Manual application tracker add form. Job Radar assigns the tracker ID when the record is saved. | Keep |
| `job_radar/templates/history.html` | Job history/archive page for archived/history records, including summary cards, quick filters, search, filtering, sorting, chip display, and edit links. | Keep |
| `job_radar/templates/history_edit.html` | Job history edit form, including save, delete, and move-back-to-tracker workflow. | Keep |
| `job_radar/templates/profile.html` | Profile/resume page for viewing profile state and uploading/replacing resumes through the GUI. | Keep |
| `job_radar/templates/reports.html` | Reports page for viewing existing generated reports and email previews, including latest scan result shortcut cards. | Keep |
| `job_radar/templates/companies.html` | Read-only Companies list page showing configured target companies, source types, enabled status, source details, notes, source/status filters, and search without writing config changes. | Keep |
| `job_radar/templates/company_detail.html` | Read-only company detail page showing the full YAML-derived company record for inspection before future edit flows. | Keep |
| `job_radar/templates/report_view.html` | In-app report viewer shell for opening generated reports inside the GUI with shared dark styling, copy support, and focused Ctrl+A report-content selection. | Keep |
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
