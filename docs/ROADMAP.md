# Product Roadmap

This file is the authoritative product roadmap for junior. Session prompts, daily logs, and planning summaries must reference this file rather than maintaining a separate editable roadmap.

## Roadmap rules

- Priority numbers and task descriptions are static unless the user explicitly authorizes a change.
- Do not shorten, rewrite, merge, split, reorder, reinterpret, add, or delete tasks without approval.
- Normal roadmap maintenance changes only the status column using verified results.
- Allowed statuses are `Planned`, `In Progress`, `Completed`, `Parked`, and `Blocked`.
- Use `Completed` only when the entire task description has been satisfied and verified.
- Use `In Progress` when meaningful work has started but the complete task is not finished.
- Proposed wording or priority changes must be discussed separately before editing this table.

## Product goal

junior should become a configurable local-first job-search operations application that a non-developer can install, launch, configure, and use without editing source files or YAML by hand.

junior is a targeted scanner for companies the user deliberately selects. It is not a hosted job board, broad web crawler, automatic application bot, recruiter-outreach system, or LinkedIn scraper.

## Authoritative Product Roadmap / Next Project Steps

| Priority | Status Planned/Completed | Task |
|---|---|---|
| 1 | Completed | Finish GUI-native tracker/history workflows so normal application tracking no longer depends on the spreadsheet. |
| 2 | Completed | Add practical tracker/history search and filtering for company, role, status/decision, outcome, source, recruiter/contact, notes, and follow-up review. |
| 3 | Completed | Make the GUI the source of truth for active applications, archived history, passed roles, rejected applications, dormant roles, and follow-up state. |
| 4 | Completed | Complete a repository-wide maintainability review and add concise comments where they clarify module purpose, business rules, safety boundaries, compatibility behavior, and non-obvious decisions without making files noisy. |
| 5 | In Progress | Create and maintain `CHANGELOG.md`, semantic versioning rules, immutable release tags, and release notes for each stable product milestone. |
| 6 | In Progress | Document the post-MVP application architecture, including entry points, service boundaries, configuration ownership, data ownership, startup flow, shutdown flow, desktop mode, server mode, and developer CLI mode. |
| 7 | Completed | Separate user-owned data from application code by storing profiles, resumes, settings, company records, SQLite databases, reports, logs, backups, and runtime files in OS-appropriate user-data directories. |
| 8 | Completed | Preserve backward compatibility for existing repo-relative configuration and current user data while transitioning to external user-data paths. |
| 9 | In Progress | Add safe, versioned migrations for SQLite schema, settings, profiles, company records, and other persisted user data so upgrades never silently lose or corrupt data. |
| 10 | In Progress | Create a reusable application configuration service so GUI, CLI, desktop launcher, server mode, and packaged builds all load and save settings through the same tested interface. |
| 11 | Completed | Create a generic profile domain model with stable profile IDs, display names, resume ownership, preferences, company associations, scoring configuration, report settings, and active-profile selection. |
| 12 | In Progress | Add profile creation, editing, duplication, switching, archival, deletion, and validation through the GUI without requiring user accounts or authentication. |
| 13 | Completed | Preserve and migrate the existing MVP profile as a working managed profile without changing its current scoring or search behavior. |
| 14 | In Progress | Build user-friendly profile and preference configuration for target roles, seniority, skills, compensation floor and target, locations, remote/hybrid rules, exclusions, travel tolerance, employment type, clearance rules, and recommendation behavior. |
| 15 | Completed | Generalize scoring configuration so profiles unrelated to infrastructure, HPC, or SRE do not inherit another user's role, skill, location, or blocker assumptions. |
| 16 | Planned | Add optional profile templates that provide editable starting points for common job-search types without locking users into fixed scoring behavior. |
| 17 | Completed | Decide and document the final role of the spreadsheet bridge: one-time migration, optional bulk import, export-only compatibility path, or full retirement from normal use. |
| 18 | In Progress | Add safe import tools for bringing existing applications, history, resumes, profiles, and company lists into the app without duplicating or overwriting existing records. |
| 19 | Completed | Create a user-owned company persistence model that does not directly rewrite or risk corrupting the released grouped `target-companies.yaml` configuration. |
| 20 | In Progress | Add GUI company management for creating, editing, enabling, disabling, deleting, validating, and assigning companies to one or more profiles. |
| 21 | Planned | Add guided company-source detection from a company name or careers URL, with confirmation of detected ATS/source type before saving. |
| 22 | Planned | Add company connection testing, collector validation, last-success status, last-error status, and clear troubleshooting messages. |
| 23 | In Progress | Preserve support for shipped/default company definitions while allowing users to maintain their own company inventory and overrides safely. |
| 24 | In Progress | Add first-run detection so a new installation opens guided setup instead of failing because configuration, profiles, companies, or data directories do not yet exist. |
| 25 | Planned | Create a guided first-run setup wizard that collects profile name, resume, role preferences, compensation, locations, remote/hybrid rules, exclusions, and initial companies. |
| 26 | Planned | Add a first-run review step that clearly shows the generated profile, preferences, companies, data location, and scan behavior before the user saves the setup. |
| 27 | Planned | Add a first-run validation scan that tests configuration, confirms at least one working company source, and explains any setup problems in plain language. |
| 28 | Planned | Add resumable setup so an interrupted or incomplete first-run wizard can continue safely without starting over or leaving broken partial configuration. |
| 29 | In Progress | Build editable Settings pages for application paths, report behavior, scan behavior, retention, profile defaults, company defaults, logs, backups, and application version information. |
| 30 | Planned | Add safe credential storage using OS-appropriate secret handling so SMTP passwords, API keys, and tokens are never stored in committed files or plain-text application settings. |
| 31 | Planned | Add an email setup flow for SMTP server, port, security mode, sender, recipients, credentials, and clear validation errors. |
| 32 | Planned | Add a safe test-email workflow that does not accidentally trigger a full scan or send a normal production report. |
| 33 | Planned | Add scan scheduling configuration for enabled/disabled state, time of day, selected weekdays, email delivery, next scheduled run, last run, and failed-run visibility. |
| 34 | Planned | Implement Windows scheduling support through a controlled Task Scheduler integration that can be created, inspected, updated, disabled, and removed through the app. |
| 35 | Planned | Add Linux scheduling support for standalone and server installations using a documented, shared scheduling abstraction rather than separate product logic. |
| 36 | Planned | Add configurable report and log retention options such as latest only, latest plus previous, or retain the most recent configured number of runs. |
| 37 | In Progress | Add source-health, scan-health, and application diagnostics that clearly distinguish configuration errors, collector failures, network problems, email failures, and unexpected application errors. |
| 38 | Planned | Add an in-app logs and diagnostics page with safe log viewing, copyable troubleshooting details, and an Open Data Directory action. |
| 39 | In Progress | Add user-facing backup, restore, export, and recovery workflows for profiles, companies, settings, SQLite data, reports, and other user-owned application data. |
| 40 | In Progress | Add automatic safety backups before destructive migrations, major upgrades, profile deletion, company deletion, database repair, or data reset operations. |
| 41 | In Progress | Add a normal application launcher that starts Job Radar, waits for readiness, opens the interface, reports startup failures, and does not require the user to enter Python or Flask commands. |
| 42 | In Progress | Add single-instance handling so launching Job Radar twice focuses or reports the existing application instead of starting conflicting servers or opening duplicate databases. |
| 43 | In Progress | Add clean application shutdown that stops background services, closes database connections, completes pending writes safely, and prevents orphaned Flask or Python processes. |
| 44 | Planned | Evaluate and select the final desktop application shell, with preference for wrapping the existing Flask GUI in a lightweight native window rather than rewriting the interface without a clear need. |
| 45 | Planned | Implement the selected desktop shell with an application icon, native window, normal minimize/maximize/close behavior, startup error dialogs, and no visible Flask development console for normal users. |
| 46 | In Progress | Preserve browser-based local mode, developer CLI mode, desktop mode, and future server mode through shared service-layer code rather than maintaining separate implementations. |
| 47 | Planned | Add application About and Version views showing installed version, release channel, data location, database version, configuration version, and support/diagnostic information. |
| 48 | In Progress | Complete GUI consistency and polish across setup, profiles, companies, tracker, history, reports, scan, settings, dialogs, validation messages, empty states, loading states, and error states. |
| 49 | Planned | Review keyboard navigation, focus behavior, readable contrast, scaling, text wrapping, form labels, confirmation wording, and other accessibility concerns throughout the application. |
| 50 | In Progress | Add realistic demo/sample data and screenshots that can be used for documentation, release validation, and demonstrations without exposing private job-search data. |
| 51 | Completed | Define packaging architecture, bundled dependencies, application resources, default configuration, user-data creation, migrations, launch behavior, and upgrade behavior before producing installers. |
| 52 | Planned | Create a reproducible Windows packaged build with an `.exe` entry point that does not require the user to install Python, create a virtual environment, clone the repository, or run terminal commands. |
| 53 | Planned | Create a Windows installer with application icon, Start Menu entry, optional desktop shortcut, guided installation, clear install location, user-data preservation, and clean uninstall support. |
| 54 | In Progress | Ensure Windows upgrades preserve profiles, resumes, settings, companies, tracker/history data, reports, credentials, backups, and schedules while updating only application-owned files. |
| 55 | Planned | Add Windows installer repair, upgrade, and uninstall validation, including confirmation that uninstalling the application does not delete user data without explicit approval. |
| 56 | Planned | Add optional update checking that reports available stable releases without silently replacing the application or changing user data. |
| 57 | Planned | Package the application for Linux using a supported tarball-based distribution with launch scripts, dependency checks, user-data paths, migrations, logs, and clear install/uninstall instructions. |
| 58 | In Progress | Support standalone local PC operation on Windows and Linux for users who want Job Radar to run only when they launch it. |
| 59 | Planned | Support unattended service-style operation on Windows and Linux for users who want scheduled scans without keeping the desktop application open. |
| 60 | Planned | Add container/server mode with persistent user data, configuration injection, logs, health checks, controlled upgrades, and the same service-layer behavior as the desktop application. |
| 61 | Planned | Support Kubernetes deployment with persistent storage, Secrets, configuration, health checks, scheduled scans, backups, retention, and safe upgrade procedures. |
| 62 | In Progress | Write complete installation, guided setup, profile management, company management, email, scheduling, backup, restore, troubleshooting, upgrade, and uninstall documentation for Windows users. |
| 63 | Planned | Write complete installation and operations documentation for Linux standalone mode, Linux service mode, container mode, and Kubernetes mode. |
| 64 | In Progress | Add automated release validation for clean installation, first launch, guided setup, initial scan, application restart, upgrade, migration, backup, restore, and uninstall behavior. |
| 65 | Planned | Test packaged builds on clean Windows and Linux environments that do not contain the development repository, Python virtual environment, existing settings, or developer tools. |
| 66 | Planned | Add release-candidate acceptance testing using a new-user workflow from installer download through first report, application tracking, restart, update, backup, restore, and uninstall. |
| 67 | Planned | Resolve all release-blocking defects, incomplete setup paths, unexplained errors, broken migrations, packaging failures, data-loss risks, accessibility blockers, and documentation gaps found during release-candidate testing. |
| 68 | Planned | Publish the first fully productized stable release with installer downloads, checksums, release notes, screenshots, supported-platform details, upgrade instructions, known limitations, and verified documentation. |
| 69 | In Progress | Finalize the product finish line: a user can download Job Radar, run the installer, launch the application, complete guided setup, add their own profile and companies, run and schedule scans, review reports, manage applications, preserve and back up their data, upgrade safely, and use the product daily without editing code or YAML. |

## Protected wording notes

- Priority 12 still contains the earlier duplication and archival requirements. The current product deliberately uses a compact five-profile selector and guarded deletion instead of user-facing profile archiving, and duplication is not implemented. Changing that task description requires explicit approval.
- Priority 19 uses “user-owned” to mean data stored in the user's application-data area. Employer organizations and source definitions are installation-wide; profiles independently select from that shared catalog.
- Historical `Job Radar` references remain inside protected task descriptions. The user-facing product name is junior, while repository, package, command, environment-variable, durable Job Radar ID, and existing user-data names remain unchanged for compatibility.

## Current status summary

Completed foundations include durable SQLite migrations and backups, shared scan lifecycle services, structured reporting, user-owned runtime paths, distribution-readiness validation, managed profiles and resumes, profile-owned employer selections, profile-owned Tracker and History records, background GUI scans, and the retirement of normal spreadsheet tracking.

Foundation 7A established the Company Workspace: profile-specific Scanning and Paused state, a matching Profile summary, and removal of technical employer-source data from the normal managed-profile view. Employer resolution, URL detection, suggestions, and an administrative Employer Catalog remain part of later company-management work.

Foundation 7B is complete: ordinary Settings remains available, installation-wide controls are classified under a session-scoped Administration boundary, the Administration shell requires explicit `ADMIN` confirmation, and an unlocked session is visibly identified and can always be exited. Employer editing and all other global mutations remain deferred.

Foundation 7C is complete: every current state-changing web request requires a valid session-bound CSRF token, mutation GET routes remain unavailable, invalid submissions fail before business logic runs, and normal forms and background requests receive consistent safe recovery responses. Shared domain errors are ready for later company and recommendation services.

Foundation 7D is complete: the active profile can pause or resume any assigned company from the Company Workspace or company detail page. The operation validates active-profile ownership, changes only that profile's assignment, preserves the shared employer catalog and other profiles, and leaves legacy company configuration read-only.

Foundation 7E is complete: a guarded `REMOVE` confirmation lets the active profile remove a company from its own list without deleting the shared employer or affecting another profile. Future scans omit the removed assignment while collected jobs, Tracker records, application history, reports, and other historical records remain intact.

Foundation 7F is complete: the active profile can search a normal-user-safe view of the existing Employer Catalog and add an available, centrally validated scan-ready employer. New assignments default to Scanning, duplicates and cross-profile leakage are prevented, incomplete or globally unavailable employers are blocked with plain-language guidance, and technical collector details remain hidden.

Foundation 7G is complete: the Administration-only Employer Catalog provides searchable global employer records, structured source forms, bounded local validation, reversible global enable/disable/retire controls, preserved profile assignments, protected hard deletion, assignment counts, and a sanitized change audit. Validation does not run a scan or contact an employer.

Foundation 7H is complete: a normal user can enter a company name or public careers URL. Junior normalizes the input, checks exact catalog identity and aliases, prevents silent ambiguous merges, recognizes supported career-site families centrally, creates and assigns only confidently complete sources in one transaction, and otherwise records a safe pending administrator-review request. Resolution makes no network request and rejects local or private destinations.

Foundation 7I is complete: the Administration-only Employer Review Queue can inspect safe unresolved submissions, match an existing employer, prefill new-employer setup, optionally assign an available employer to the requesting profile, or mark a request unsupported, rejected, or duplicate. Decisions are audited without raw collector failures or profile content, while normal users see only their own plain-language request state.

Foundation 7J1 is complete: the active profile can view deterministic recommendations from scan-ready employers already in the local Employer Catalog. Assigned and unavailable employers are excluded, grounded catalog overlap is explained in plain language, numeric ranking remains internal, and Add, Maybe later, Dismiss, and Not relevant responses persist independently per profile with bounded cooldowns where appropriate.

Foundation 7J2 is complete: future scan runs record their owning profile, and recommendation ranking can use a bounded 90-day window of up to 500 recent postings per employer from that profile's scans. Junior transparently explains relevant-job counts, strong title matches, compatible remote jobs, workplace or location conflicts, sufficiently reliable below-floor compensation patterns, and recency. Applications and rejections do not automatically imply employer interest. Unowned legacy scans are ignored, evidence remains deterministic and profile-isolated, and the existing feedback rules continue to control visibility.

The next company milestone is Foundation 7J3, which adds carefully bounded external employer discovery without turning Junior into a broad public job board. Other major product areas include completing profile configuration, guided first-run setup, editable Settings and credential workflows, scheduling, user-facing backup and recovery, and final desktop packaging.

The projected full-product target remains September 30, 2026. Milestone quality, user-data safety, and dependency order take precedence over the date.
