# Changelog

All notable changes to junior are documented here.

This project follows the spirit of [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Version numbers are currently managed in `pyproject.toml`.

## Unreleased

### Added

- An Administration-only Employer Review Queue for matching unresolved submissions, prefilled new-employer setup, guarded profile assignment, unsupported/rejected/duplicate decisions, and a sanitized decision audit.
- Profile-specific, catalog-only company recommendations with plain-language reasons, deterministic ordering, one-click assignment, and durable Maybe later, Dismiss, and Not relevant feedback.
- Plain-language Setup pending, Ready to add, and Unsupported company-submission states scoped to the requesting profile.
- SQLite migration version 15 for employer review decision auditing without raw collector errors or profile contents.
- A normal-user Add Company workflow accepting a company name or careers URL, with exact catalog/alias matching, centralized career-site detection, conservative scan-ready creation, ambiguous-match confirmation, and safe pending-review requests.
- Unicode-aware company-name and normalized public-URL identity, duplicate source constraints, employer aliases, and pending employer-review storage in SQLite migration version 14.
- A guarded Administration Employer Catalog for structured employer creation and editing, bounded local validation, global enable/disable/retire controls, assignment counts, filters, and a sanitized change audit.
- SQLite migration version 13 for reversible employer lifecycle and validation metadata, protected by backup-before-migration and atomic rollback behavior.
- A safe Add Company page where the active profile can search Junior's existing catalog and add only globally available, scan-ready employers, defaulting the new assignment to Scanning.
- Guarded profile-company removal that stops future scans for only the active profile while preserving the shared employer, other profiles, collected jobs, applications, and history.
- Profile-specific Pause and Resume controls in the Company Workspace, with assignment validation that leaves the shared employer catalog and other profiles unchanged.
- Session-bound CSRF protection for every existing web mutation, including Administration, scans, profiles, résumés, job-fit preferences, Tracker, and History, with safe HTML and JSON failure responses.
- Shared domain-error types for upcoming profile-company assignment, employer catalog, Administration, and recommendation services.
- A session-scoped Administration shell with explicit `ADMIN` confirmation, safe local redirects, a visible mode indicator and exit action, and an installation-local Flask session signing key.
- A read-only Company Workspace showing the active profile's company count and per-profile Scanning or Paused state, with a matching Profile / Resume summary link.
- Profile-specific employer assignment state, allowing each managed profile to independently assign and enable or disable employers from the shared installation-wide employer catalog.
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
- Database-backed active-profile selection with an unchanged YAML fallback when no managed profile is selected.
- GUI workflows for managed profile creation, editing, switching, guarded permanent deletion, and managed resume upload.
- SQLite migration version 5 for the optional active-profile selection record; the migration does not select or change existing profile data.
- A controlled legacy-profile migration service with read-only planning, private recovery bundles, destination-collision checks, atomic profile selection, and managed-file rollback on failure.
- GUI-managed profile preferences that save normalized occupations, structured locations and commute radii, job levels, employment types, schedules, workplace arrangements, compensation minimums, and travel percentages to the active managed profile without changing existing scoring behavior.
- SQLite migration version 6 for structured occupation, location, and schedule preferences, protected by backup-before-migration and atomic rollback behavior.
- Dedicated profile creation and editing pages with duplicate-name protection, atomic creation and selection, safe cancellation, explicit save actions, and managed résumé replacement.
- Occupation-neutral scoring ownership for newly created managed profiles, preventing unrelated profiles from inheriting infrastructure, SRE, Kubernetes, HPC, Slurm, GPU, location, or title-exclusion assumptions.

### Changed

- Employer records referenced by a profile or collected job can no longer be permanently deleted; global disable and retirement preserve assignments and history.
- Included nested Administration templates in wheel and source packages and extended installed-package rendering coverage.
- Classified ordinary Settings separately from installation-wide Administration without moving or enabling technical configuration controls yet.
- Replaced technical employer-source details on the managed-profile Companies page with a normal-user workspace while preserving the legacy YAML view when no managed profile is active.
- Replaced personal identities and nonessential real-company names in repository policy, roadmap history, and general-purpose test fixtures with neutral examples while preserving the approved support contact and source-specific collector coverage.
- Removed the remaining global infrastructure, SRE, Kubernetes, employer, title-family, and Northern Colorado recommendation assumptions. Recommendation actions, risks, report grouping, resume gaps, and history-title matching now use profile-owned evidence and occupation-neutral rules, with explicit food-service coverage.
- Renamed user-facing "technical match" wording to "role fit" while preserving the existing stored history field for backward compatibility.
- Replaced the repository scoring fallback with the same neutral structure used for new profiles; existing managed-profile scoring data remains unchanged.
- Made `docs/ROADMAP.md` the single authoritative product roadmap, updated its verified task statuses, and synchronized repository documentation with profile-owned Tracker/History and current profile behavior.
- Replaced the packaged starter scoring rules with an occupation-neutral structure while preserving existing managed-profile scoring.
- Active Applications and Application History are now owned by the active profile across the GUI, scans, reports, and CLI; existing records migrate to the active profile, and profiles with job-search activity cannot be deleted.

- GUI-started scans now run without blocking the rest of junior and report progress, completion, source warnings, or failure throughout the interface.

- Integrated profile preferences into Profile / Resume, removed the separate navigation page and informational banner, added dedicated create and edit pages with explicit save controls and first-profile guidance, and combined résumé insights with the plain-English search summary.
- Replaced profile archiving controls with a compact five-profile manager supporting selection, editing, creation, and guarded permanent deletion of a profile and its Junior-managed résumé.
- Renamed the user-facing application from Job Radar to junior and added the official logo to the shared interface and packaged application assets while preserving established package, command, environment-variable, and user-data compatibility names.
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
