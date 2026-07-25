# Changelog

All notable changes to junior are documented here.

This project follows the spirit of [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Version numbers are currently managed in `pyproject.toml`.

## Unreleased

- Added automatic UKG Pro Recruiting/UltiPro company discovery and collection
  from complete public job-board URLs, including bounded pagination and full
  public job-detail extraction.
- Added a compact Review Needed display with at most 50 jobs per page,
  current-page-only Select all, top and bottom page navigation, repeated bulk
  actions, and a Back to top link that keeps the current page and selections.
  Every compact job retains the same expandable Save, Pass, Apply, Notes, and
  evidence controls.
- Fixed the profile editor's multiline work-exclusion field so its contents no
  longer overlap the Job requirements card.
- Fixed recognized `*.icims.com` career sites so company setup validates them
  with Junior's dedicated iCIMS collector instead of incorrectly falling back
  to generic webpage parsing or optional external lookup.
- Added GitHub Actions workflows for Windows/Python 3.13 Ruff and full-suite
  validation plus checksum-verified, redacted Gitleaks scanning of reachable
  Git history.
- Documented the automated validation boundaries, release requirements, and
  response required if secret scanning identifies a real credential.
- Added a reproducible third-party license audit with machine-readable package,
  platform-component, and reference-data records; bundled the audit, notices,
  and required upstream license material in every supported distribution.
- Added a plain-language privacy notice based on verified current network and
  storage behavior, plus a private vulnerability-reporting policy and official
  download, checksum, signed-tag, and future code-signing guidance.
- Licensed Junior under the GNU General Public License version 3.0 only
  (`GPL-3.0-only`) and included the complete license in Python, Windows, Linux,
  and container distributions.
- Fixed annual compensation extraction for common ATS description formats,
  including HTML headings, encoded dash characters, and USD labels before or
  after a clearly identified pay range. Confirmed compensation continues to
  enforce only the profile minimum and does not reward higher advertised pay.
- Ensured every structured scan-result classification, including Potential
  Top Matches and Passed / Not Recommended, retains individual notes, Save for
  later, Pass / don't show again, and application-tracking controls.
- Added optional shared Website, Careers, LinkedIn, and Glassdoor reference
  links to company detail pages. Junior opens these public links in the
  user's browser and never signs in to or scrapes the linked services.
  Editing links preserves the validated job collector and its health history.
- Added **Potential Top Matches** for jobs that satisfy the existing top-match
  score and strong-signal rules but still need practical facts confirmed. Top
  Matches remain strict, thresholds are unchanged, and normal pages show
  evidence and unresolved facts without exposing numeric scores.
- Improved conservative extraction of explicit workplace arrangements, common
  employment-type wording, and annual compensation embedded in job
  descriptions when an ATS omits the corresponding structured field. Missing
  schedule wording no longer implies a conflict; explicit schedule and on-call
  requirements remain enforced.
- Set the reviewed 1440 by 900 first-launch window size and added safe
  user-owned persistence of the native window's last size and screen position.
  Missing or invalid geometry returns to the reviewed default.
- Replaced the report-first post-scan path with an interactive Review Jobs
  workspace. Large result groups now render 20 jobs per page, supporting
  evidence is expandable, and job-decision controls use a balanced responsive
  layout. Static HTML and email reports remain available as read-only exports.
- Renamed the ambiguous recommendation label **Hold** to **Needs your review**
  without changing its scoring or eligibility behavior, including display
  compatibility for existing scan snapshots.
- Hid Junior-managed job IDs from normal forms and reports while preserving
  scan-linked identity and automatic IDs for manually entered applications.
- Added human-only notes of up to 300 characters directly to individual Save
  and Pass decisions, listed pass reasons, and atomic multi-select actions in
  the profile-owned Saved and Reviewed Jobs workflow. Notes do not affect
  scoring.
- Added a profile-owned Saved / Reviewed Jobs summary and direct workspace link
  to Home, and corrected spacing between the workspace introduction and lists.
- Strengthened practical eligibility explanations for explicit foreign
  locations, fixed contract durations, and work-authorization requirements
  without inventing a global preference against short contracts.
- Added a two-minute overall ceiling to unfamiliar company-source discovery.
  Timed-out discovery saves no employer or profile assignment, and the Add
  Company page continues to show an active checking indicator while it runs.
- Added a global, default-off Bing company-lookup setting with plain-language
  disclosure of its limited advantage, complete search payload, IP-address
  exposure, reliability risk, and strict separation from normal scans.
- Distinguished an unavailable optional lookup from a completed lookup with no
  independently verified source, without exposing raw failures or scheduling
  silent retries.
- Clarified directly on Windows Scan Schedule setup that Junior's window may be
  closed while the scheduled task runs, but the user must remain signed in and
  the computer must be awake and powered on.
- Added a Credits section to About Junior recognizing beta tester Dawn Peacock.
- Added a global, read-only Collector Catalog that is populated on fresh
  installations without adding employers to the global Employer Catalog.
- Added automatic setup for complete ADP Workforce Now and Recruitee careers
  URLs, plus a validated schema.org JobPosting fallback for unfamiliar public
  careers pages. Unsupported pages are not saved as broken scan sources and
  instead show privacy-safe support guidance.
- Expanded company setup to probe ATS links and metadata advertised behind
  branded careers pages, added automatic Workday, Oracle HCM, Phenom, and
  Eightfold setup, and required a real public job result before an unfamiliar
  source is saved.
- Added Retry setup and guarded Remove attempt actions for unfinished company
  submissions, editable shared company names that preserve source settings and
  history, a clean redirect after successful setup, and an in-page working
  indicator while Junior checks a careers source.
- Company confirmation now requires a successful bounded collector test,
  records the initial safe source-health result, and shows the recruiting
  platform, latest check, and returned-job count on the normal company page.
  Users can rerun that non-destructive test without Administration access.
- When explicitly enabled in Settings, blocked or separated employer landing
  pages can use an optional bounded Bing lookup containing only the submitted
  company name and domain. Junior probes only identity-related results, stores
  only a verified working source, and discards rejected candidates without
  creating database clutter.
- Replaced persistent company-result query strings with one-use, dismissible
  notifications and clarified that profile removal does not delete the shared
  employer.

## 0.2.0 - 2026-07-24

- Added profile-owned Saved and Reviewed Jobs decisions to structured scan
  results. Users can save a job, pass on the exact posting, reverse either
  choice, or explicitly move into the application workflow only after applying.
- Added protected SQLite migration version 27 for job decisions. Saved and
  passed jobs remain separate from Active Applications and Application History,
  and later reports omit only the exact decided job for the active profile.
- Removed the internal Job Radar ID from structured result cards while
  preserving it behind the scenes when a user tracks an application.
- Replaced the browser-branded bulk application confirmation with a
  Junior-styled in-app confirmation panel that preserves the same guarded move
  to Application History without exposing the local server address.
- Corrected report grouping so jobs with unresolved practical details appear
  under Review Needed instead of being contradicted by a "not recommended"
  category. Top Matches still require both strong role fit and confirmed
  practical eligibility.
- Added a guarded bulk action for moving selected Active Applications to
  History with a rejected, withdrawn, or closed outcome in one atomic,
  profile-owned operation.
- Prevented a newly requested scan from replaying the previous scan's
  completion notification before the new scan actually starts, and suppressed
  the redundant completion popup while the user is already on the Scan page.
- Polished the field-test interface with consistent page and table spacing,
  themed scrollbars, an obvious Back to Administration link on every guarded
  Administration subpage, and collapsed developer-only scan details.
- Added an explicit profile-owned security-clearance choice. Clear existing-active-clearance requirements now follow that choice, while ambiguous wording is sent to Needs Review.
- Added a direct portable backup download and verified cross-workspace restore
  path for safely moving development data into an installed Junior copy.
- Added unobtrusive Home dashboard actions for sharing a Junior story and
  making an entirely voluntary donation through the maintainer's public Venmo
  profile.

- Added a disposable long-term scale gate for 100 companies, 100,000 jobs,
  10,000 historical applications, 2,500 active applications, and five profiles;
  added profile-first and active-company database indexes; and corrected the
  shared SQLite boundary so context-managed operations release their database
  handles after commit or rollback.
- Added a repeatable release-candidate acceptance walkthrough for the exact
  publishable installer, covering isolated new-user setup, first report,
  application tracking, restart, update checking, backup, restore,
  repair/update, uninstall, and user-data preservation.
- Added clean-package validation that launches only a temporary installed Windows executable with isolated empty data and exercises the Linux archive in a Python-free Debian container, then confirms uninstall preserves synthetic user-data sentinels.
- Added one automated Windows release gate that runs the full suite, lint and whitespace checks, builds the current installer, and validates disposable install, repair/upgrade, uninstall, and user-data preservation across the tested first-run, setup, scan, restart, migration, backup, and restore lifecycle.
- Completed the Linux standalone, Linux systemd user-service, Docker/Compose, and Kubernetes operations guide, including persistence, scheduling, health, security, backup, upgrade, shutdown, and data-preserving removal boundaries.
- Completed the normal-user Windows guide for per-user installation, guided setup, profile and résumé management, companies, email, scheduling, backup and restore, troubleshooting, safe upgrades, and data-preserving uninstall.
- Added an operator-ready Kubernetes baseline with single-writer SQLite safety, persistent storage, non-root execution, private networking, privacy-safe health probes, externally supplied Secrets, disabled-by-default scheduled scans, verified scheduled backups, bounded scheduled-backup retention, and restart-preservation validation.
- Added non-root container/server mode with a persistent user-data volume, idempotent bootstrap, Gunicorn lifecycle handling, a privacy-safe health endpoint, localhost-only Compose defaults, and restart/upgrade preservation validation.
- Added a Docker-isolated Linux x86-64 tarball build with a portable Junior executable, dependency-aware launcher, per-user installation helper, and uninstall behavior that preserves profiles, résumés, settings, databases, reports, logs, backups, schedules, and credentials.
- Added a manual, read-only stable-release check on About that verifies Junior's official GitHub release link, explains whether an update is available, and never downloads, installs, migrates, or changes user data.
- Added repeatable Windows install, repair/upgrade, and uninstall validation that compares user-owned files byte for byte and confirms application removal never deletes settings, profiles, resumes, companies, databases, reports, backups, schedules, or credential references.
- Added a per-user Windows installer with Junior branding, Start Menu launch, optional desktop shortcut, silent test support, and uninstall behavior that removes application files while preserving user-owned data.
- Added a reproducible PyInstaller Windows desktop build that produces an unsigned `Junior.exe` bundle with Junior's native icon, packaged resources, webview runtime, and secure-credential backends without including user-owned data.
- Added a guarded developer tool that creates an isolated, deterministic fictional Junior workspace for documentation, demonstrations, and release validation; it refuses existing destinations and includes no real profile, resume, company, or job-search data.
- Added documentation screenshots generated only from the fictional demo workspace.
- Added guarded Administration workflows for verified private backups, pre-restore safety copies, readable JSON exports, and validated user-data recovery without copying credential values.
- Added automatic safety backups inside permanent profile and company deletion services, extending the existing backup-before-migration protection to every currently implemented destructive data operation.
- Added an operating-system-managed desktop instance lock so repeated launches reuse the same user-data workspace and local interface even when a different port was requested.
- Added a desktop-only Exit Junior control that stops the local server cleanly and waits for an active scan worker to finish protected writes before releasing the instance lock.
- Selected pywebview as Junior's native desktop shell, with PySide6/QWebEngineView as the defined fallback and a strict one-interface cross-platform consistency gate.
- Added Junior's native pywebview window with normal window controls, application icon support, safe graphical startup errors, deliberate browser/server launch options, and clean shell-owned shutdown.
- Verified that native desktop, browser-based local use, developer CLI scans, and scheduled scans share the same Flask application, scan service, storage, and product rules instead of maintaining mode-specific implementations.
- Kept parent navigation visibly active throughout profile, company, report, Settings, and Administration subpages, and standardized spacing around user-facing status messages.
- Fixed pending legacy-company imports so profile-owned company pages are populated before rendering, added honest profile-specific starter guidance when no verified named recommendation exists, compacted Profile troubleshooting details, corrected Settings card spacing and page-top restoration, and assigned the unpackaged Windows window a Junior taskbar identity.
- Added shared keyboard and scaling safeguards across Junior's pages, including a skip-to-content link, strong focus-visible indicators, current-page navigation semantics, responsive narrow-window behavior, forced-color borders, error announcements, labeled administrative matching controls, and screen-reader descriptions for every data table.
- Made profile occupation and location suggestions announce their open state and support Enter, Escape, arrow-key, Tab, and click interaction without requiring a mouse.
- Replaced developer-facing tracker and history deletion terms such as “row” and “terminal action” with explicit, plain-language descriptions of what will be permanently removed and how to preserve an application in history.
- Added repository-wide accessibility guards that require programmatic labels for visible form controls and WCAG AA contrast for Junior's shared text, link, status, and action colors.
- Removed employer recommendations from the normal Companies workflow. Users choose employers, while Junior focuses on making company and careers-page identification, confirmation, configuration, and scanning easy.

- Bounded in-app viewing for allowlisted sanitized Junior logs, a copyable privacy-safe troubleshooting summary, and a CSRF-protected Open Data Directory action using the resolved settings-owned workspace.
- Read-only Settings diagnostics for application configuration, latest scan, company-source, and email health, with plain-language configuration, collector, network, email, and unexpected-application categories; scan diagnostics no longer persist raw exception text.
- Configurable report and log retention with latest-only, latest-plus-previous, or a chosen 1-to-50-run limit; verified report-set archives, retained-report browsing, atomic settings updates, and pruning limited to clearly marked Junior-owned files.
- GUI scan scheduling configuration for enabled state, local start time, weekdays, scheduled email delivery, calculated next run, and safe last-run or failed-run visibility.
- Controlled Windows Task Scheduler integration that manages only Junior's named task, runs the shared scheduled-scan entry point with normal user privileges, stores no Windows password, and supports inspection, update, disable, and removal through Settings.
- Guarded Linux systemd user scheduling that atomically manages only Junior-marked service/timer files, rolls back failed updates, and reuses the same saved schedule and scan entry point for standalone or service-account operation.

### Added

- A normal-user Email Setup page with Gmail, Outlook, and Custom SMTP choices, secure credential status, atomically saved delivery settings, and a connection-only test card reporting provider, status, test time, and simple authentication, reachability, or TLS outcomes without sending mail.
- Operating-system credential-manager storage through `keyring`, with non-secret settings references and preserved environment-variable compatibility for server and container deployments.
- A read-only About page showing the installed Junior version, release channel, user-data location, database and profile schema versions, and safe support guidance.
- Administration controls for assigning or removing an employer from individual managed profiles, plus typed-confirmation deletion limited to employers with no profile assignments or collected jobs.
- Explicit confirmation for confidently detected Greenhouse, Lever, and Ashby career sites before Junior creates the employer or adds it to a profile; uncertain sources continue to use administrator review.
- Administrator-controlled company connection testing that runs the configured collector without importing jobs, records bounded source-health timestamps and returned-job counts, and shows safe configuration, network, source-response, collector, or unexpected-error guidance without retaining raw failures.
- SQLite migration version 22 for employer connection health, protected by backup-before-migration and atomic rollback behavior.
- A first-run setup test that checks the saved profile's minimum usable search rules, confirms at least one selected company collector can connect, explains corrections in plain language, and prevents setup completion until validation passes without importing or scoring jobs.
- SQLite migration version 23 for the durable first-run validation checkpoint, protected by backup-before-migration and atomic rollback behavior.
- First-run detection that sends only genuinely empty installations to a setup welcome page while leaving existing profiles, employers, jobs, Tracker records, and History records alone.
- A guided first-run path that reuses validated profile creation, app-owned résumé upload, profile-owned company selection, and setup review services without introducing duplicate save rules.
- Resumable first-run setup with a durable SQLite checkpoint after profile, résumé, and company steps, plus explicit completion from the review page.
- SQLite migration version 20 for first-run setup progress, protected by backup-before-migration and atomic rollback behavior.
- A complete first-run review showing the selected profile, résumé, preferences, locations, companies, user-data location, and plain-language scan behavior before setup is finished.
- Profile-owned work exclusions in profile creation and editing, with one responsibility or role per line, duplicate normalization, bounded input, and résumé/context-aware evaluation instead of title-synonym expansion.
- Profile-owned Role Discovery that suggests adjacent job titles only from résumé-backed O*NET responsibilities or jobs observed in that profile's scans, explains matched evidence, preserves employer-specific title context, and requires Relevant, Not relevant, or Different discipline feedback before approved mappings affect target-role recommendation boundaries.
- SQLite migration version 21 for durable role suggestions and per-profile, per-context feedback, protected by backup-before-migration and atomic rollback behavior.
- Guarded Recommendation Administration for global employer metadata and eligibility, profile/employer diagnostics, profile-specific feedback reset, bounded rebuilds, and a sanitized audit.
- SQLite migration version 19 for recommendation-administration metadata and audit records, protected by backup-before-migration and atomic rollback behavior.
- An Administration-only Employer Review Queue for matching unresolved submissions, prefilled new-employer setup, guarded profile assignment, unsupported/rejected/duplicate decisions, and a sanitized decision audit.
- Profile-specific, catalog-only company recommendations with plain-language reasons, deterministic ordering, one-click assignment, and durable Maybe later, Dismiss, and Not relevant feedback.
- Bounded recommendation evidence from recent profile-owned scans, including relevant-job counts, strong title matches, remote compatibility, and recency without reusing unowned legacy scans.
- Fresh outside-catalog employer suggestions from bounded profile-owned job data, with duplicate detection, confidence and source state, stale-evidence removal, and guarded Employer Review Queue handoff.
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

- Retired the legacy YAML-backed Companies GUI. The normal application now requires a managed profile while preserving protected one-time import and released CLI/server scan compatibility.
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

[Unreleased]: https://github.com/lordegraves/job-radar/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/lordegraves/job-radar/releases/tag/v0.2.0
[0.1.0]: https://github.com/lordegraves/job-radar/releases/tag/v0.1.0
