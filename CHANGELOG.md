# Changelog

All notable changes to Job Radar are documented here.

This project follows the spirit of [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Version numbers are currently managed in `pyproject.toml`.

## Unreleased

### Added

- Versioned SQLite schema migrations.
- SQLite foreign-key enforcement.
- Database backup-before-migration protection.
- Atomic tracker-to-history and history-to-tracker moves.
- A shared scan service with durable scan-run records.
- Cross-process scan locking, stage-specific failures, progress state, and bounded pagination.
- Structured scoring evidence, recommendation-policy boundaries, report snapshots, and shared report view models.
- User-owned runtime paths and `JOB_RADAR_DATA_DIR` override support.
- Safe packaged bootstrap defaults for starter settings, an empty company list, and starter scoring rules.
- Optional non-destructive migration of existing settings, company configuration, scoring configuration, profiles, and a SQLite database.
- Bootstrap protection that rejects imported settings containing literal credential values while allowing environment-variable references.
- Packaging tests for wheel and source-distribution contents, clean installation outside the source tree, installed desktop-launcher startup, first-time bootstrap, and installed Flask rendering.
- A managed-profile storage foundation with stable profile IDs, profile-owned preferences, company associations, scoring/report settings, and app-owned resume filenames.
- A common user-owned `resumes` directory that prevents managed profiles from depending on files in Documents, Downloads, or other external locations.
- SQLite migration version 4 for empty managed-profile tables, protected by the existing pre-migration backup and atomic rollback behavior.

### Changed

- Split Flask routes into dedicated route modules.
- Split report models and HTML rendering into dedicated modules.
- Centralized collector HTTP behavior and pagination support.
- Separated email readiness from application startup.
- Moved private profile/resume data out of source-tree assumptions.
- Moved the application-history record model into `history_models.py`.
- Made structured snapshots and HTML the application-facing report path.
- Simplified runtime path resolution for CLI and web execution.
- Made pending SQLite schema migrations atomic so a failed upgrade rolls back incomplete changes.
- Made the desktop launcher resolve database, report, log, and profile paths from the user-owned workspace instead of its launch directory.

### Removed

- Markdown scan-output generation.
- Legacy reporting compatibility facades and dead Markdown helpers.
- Automatic spreadsheet imports during scans.
- Manual Excel history-import CLI commands.
- The Excel workbook parser, workbook tests, sample workbook, and `openpyxl` dependency.

Application History itself was not removed. It remains a core SQLite-backed application feature.

## 0.1.0 - 2026-07-14

### Added

- Configured-company collection across Greenhouse, Lever, Ashby, Workday, USAJobs, iCIMS, Jibe, Jobsyn, Oracle HCM, SmartRecruiters, SelectMinds, Phenom, Dayforce, ADP Workforce Now, Activate, WEKA, Rippling, SchoolSpring, and HTML sources.
- SQLite-backed job storage, application tracker, and application history.
- Rules-based scoring, location classification, compensation-floor handling, recommendation actions, risk flags, and resume/profile matching.
- Markdown and HTML reports, plain-text and HTML email previews, and guarded email delivery.
- Local Flask GUI for Home, Scan, Reports, Active Applications, Application History, Profile / Resume, Companies, and Settings.
- Active-application workflow states, follow-up guidance, dashboard attention queues, quick actions, archive/restore workflows, and guarded deletion.
- Resume upload and replacement for PDF, DOCX, Markdown, and plain text.
- App-owned Job Radar IDs and repair of older URL-based tracker identities.
- Tracker/history mutual exclusion and round-trip preservation of dates and record details.
- Read-only Companies and Settings visibility.
- Manual MVP acceptance workflow and no-regression test coverage.

### Security

- Private runtime data kept out of Git.
- SMTP delivery disabled unless explicitly configured and requested.
- SMTP password values excluded from YAML and source control.

[Unreleased]: https://github.com/lordegraves/job-radar/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/lordegraves/job-radar/releases/tag/v0.1.0
