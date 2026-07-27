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

## Product principles

Junior is guided by these principles:

- **Local-first.** User data belongs to the user.
- **Targeted, not broad.** Users choose employers; Junior manages and monitors them.
- **Explain before automating.** Junior explains recommendations and discoveries rather than silently acting.
- **One implementation.** Browser, desktop, CLI, scheduling, and server modes share the same service layer.
- **Recoverable changes.** Every migration, destructive action, and upgrade is reversible or backed up.
- **Cross-platform consistency.** Junior behaves the same on Windows, Linux, and macOS except where operating systems naturally differ.
- **Privacy by default.** Junior does not require cloud services or centralized user data.
- **Honest capabilities.** Junior should never imply it knows more than it actually does.

## Authoritative Product Roadmap / Next Project Steps

| Priority | Status Planned/Completed | Task |
|---|---|---|
| 1 | Completed | Finish GUI-native tracker/history workflows so normal application tracking no longer depends on the spreadsheet. |
| 2 | Completed | Add practical tracker/history search and filtering for company, role, status/decision, outcome, source, recruiter/contact, notes, and follow-up review. |
| 3 | Completed | Make the GUI the source of truth for active applications, archived history, passed roles, rejected applications, dormant roles, and follow-up state. |
| 4 | Completed | Complete a repository-wide maintainability review and add concise comments where they clarify module purpose, business rules, safety boundaries, compatibility behavior, and non-obvious decisions without making files noisy. |
| 5 | In Progress | Create and maintain `CHANGELOG.md`, semantic versioning rules, immutable release tags, and release notes for each stable product milestone. |
| 6 | Completed | Document the post-MVP application architecture, including entry points, service boundaries, configuration ownership, data ownership, startup flow, shutdown flow, desktop mode, server mode, and developer CLI mode. |
| 7 | Completed | Separate user-owned data from application code by storing profiles, resumes, settings, company records, SQLite databases, reports, logs, backups, and runtime files in OS-appropriate user-data directories. |
| 8 | Completed | Preserve backward compatibility for existing repo-relative configuration and current user data while transitioning to external user-data paths. |
| 9 | Completed | Add safe, versioned migrations for SQLite schema, settings, profiles, company records, and other persisted user data so upgrades never silently lose or corrupt data. |
| 10 | Completed | Create a reusable application configuration service so GUI, CLI, desktop launcher, server mode, and packaged builds all load and save settings through the same tested interface. |
| 11 | Completed | Create a generic profile domain model with stable profile IDs, display names, resume ownership, preferences, company associations, scoring configuration, report settings, and active-profile selection. |
| 12 | Completed | Add profile creation, editing, switching, guarded deletion, validation, and a five-profile limit through the GUI without requiring user accounts or authentication. |
| 13 | Completed | Preserve and migrate the existing MVP profile as a working managed profile without changing its current scoring or search behavior. |
| 14 | Completed | Build user-friendly profile and preference configuration for target roles, seniority, resume-derived skills, minimum compensation, locations, remote/hybrid rules, exclusions, travel tolerance, employment type, schedule, on-call, security-clearance handling, and plain-language recommendation behavior. |
| 15 | Completed | Generalize scoring configuration so profiles unrelated to infrastructure, HPC, or SRE do not inherit another user's role, skill, location, or blocker assumptions. |
| 16 | Completed | Provide occupation-neutral guided profile creation that starts blank and lets each user define their own work, location, employment, and eligibility preferences without fixed scoring assumptions. |
| 17 | Completed | Decide and document the final role of the spreadsheet bridge: one-time migration, optional bulk import, export-only compatibility path, or full retirement from normal use. |
| 18 | Completed | Provide verified backup and restore tools for transferring complete Junior workspaces between development and installed environments without modifying the source or risking the destination's prior state. |
| 19 | Completed | Create a user-owned company persistence model that does not directly rewrite or risk corrupting the released grouped `target-companies.yaml` configuration. |
| 20 | Completed | Add GUI company management for creating, editing, enabling, disabling, deleting, validating, and assigning companies to one or more profiles. |
| 21 | Completed | Add guided company-source detection from a company name or careers URL, with confirmation of detected ATS/source type before saving. |
| 22 | Completed | Add company connection testing, collector validation, last-success status, last-error status, and clear troubleshooting messages. |
| 23 | Completed | Preserve support for shipped/default company definitions while allowing users to maintain their own company inventory and overrides safely. |
| 24 | Completed | Add profile-owned role discovery and title mapping based on demonstrated skills, tools, responsibilities, and domain evidence; explain adjacent-title suggestions in plain language, require approval before expanding scans, and record Relevant, Not relevant, or Different discipline feedback without relying on dictionary synonyms. |
| 25 | Completed | Add first-run detection so a new installation opens guided setup instead of failing because configuration, profiles, companies, or data directories do not yet exist. |
| 26 | Completed | Create a guided first-run setup wizard that collects profile name, resume, role preferences, compensation, locations, remote/hybrid rules, exclusions, and initial companies. |
| 27 | Completed | Add a first-run review step that clearly shows the generated profile, preferences, companies, data location, and scan behavior before the user saves the setup. |
| 28 | Completed | Add a first-run validation scan that tests configuration, confirms at least one working company source, and explains any setup problems in plain language. |
| 29 | Completed | Add resumable setup so an interrupted or incomplete first-run wizard can continue safely without starting over or leaving broken partial configuration. |
| 30 | Completed | Provide editable Settings workflows for email, scheduling, retention, backups, scan behavior, logs, and diagnostics; keep application paths and version information read-only; keep profile preferences under Profile / Resume and employer defaults under Administration. |
| 31 | Completed | Add safe credential storage using OS-appropriate secret handling so SMTP passwords, API keys, and tokens are never stored in committed files or plain-text application settings. |
| 32 | Completed | Add an email setup flow for SMTP server, port, security mode, sender, recipients, credentials, and clear validation errors. |
| 33 | Completed | Add a safe test-email workflow that does not accidentally trigger a full scan or send a normal production report. |
| 34 | Completed | Add scan scheduling configuration for enabled/disabled state, time of day, selected weekdays, email delivery, next scheduled run, last run, and failed-run visibility. |
| 35 | Completed | Implement Windows scheduling support through a controlled Task Scheduler integration that can be created, inspected, updated, disabled, and removed through the app. |
| 36 | Completed | Add Linux scheduling support for standalone and server installations using a documented, shared scheduling abstraction rather than separate product logic. |
| 37 | Completed | Add configurable report and log retention options such as latest only, latest plus previous, or retain the most recent configured number of runs. |
| 38 | Completed | Add source-health, scan-health, and application diagnostics that clearly distinguish configuration errors, collector failures, network problems, email failures, and unexpected application errors. |
| 39 | Completed | Add an in-app logs and diagnostics page with safe log viewing, copyable troubleshooting details, and an Open Data Directory action. |
| 40 | Completed | Add user-facing backup, restore, export, and recovery workflows for profiles, companies, settings, SQLite data, reports, and other user-owned application data. |
| 41 | Completed | Add automatic safety backups before destructive migrations, major upgrades, profile deletion, company deletion, database repair, or data reset operations. |
| 42 | Completed | Add a normal application launcher that starts Job Radar, waits for readiness, opens the interface, reports startup failures, and does not require the user to enter Python or Flask commands. |
| 43 | Completed | Add single-instance handling so launching Job Radar twice focuses or reports the existing application instead of starting conflicting servers or opening duplicate databases. |
| 44 | Completed | Add clean application shutdown that stops background services, closes database connections, completes pending writes safely, and prevents orphaned Flask or Python processes. |
| 45 | Completed | Ensure Junior’s application interface remains visually and functionally consistent across Windows, Linux, and macOS. Platform-native window chrome, file dialogs, notifications, and keyboard conventions may differ, but Junior’s pages, layouts, controls, navigation, validation, spacing, typography, and workflows must not develop platform-specific artifacts or require separate implementations. Evaluate desktop-shell candidates in this order: pywebview, PySide6/QWebEngineView, Electron, then Tauri. |
| 46 | Completed | Implement the selected desktop shell with an application icon, native window, normal minimize/maximize/close behavior, startup error dialogs, and no visible Flask development console for normal users. |
| 47 | Completed | Preserve browser-based local mode, developer CLI mode, desktop mode, and future server mode through shared service-layer code rather than maintaining separate implementations. |
| 48 | Completed | Add application About and Version views showing installed version, release channel, data location, database version, configuration version, and support/diagnostic information. |
| 49 | In Progress | Complete GUI consistency and polish across setup, profiles, companies, tracker, history, reports, scan, settings, dialogs, validation messages, empty states, loading states, and error states. |
| 50 | Completed | Review keyboard navigation, focus behavior, readable contrast, scaling, text wrapping, form labels, confirmation wording, and other accessibility concerns throughout the application. |
| 51 | Completed | Add realistic demo/sample data and screenshots that can be used for documentation, release validation, and demonstrations without exposing private job-search data. |
| 52 | Completed | Define packaging architecture, bundled dependencies, application resources, default configuration, user-data creation, migrations, launch behavior, and upgrade behavior before producing installers. |
| 53 | Completed | Create a reproducible Windows packaged build with an `.exe` entry point that does not require the user to install Python, create a virtual environment, clone the repository, or run terminal commands. |
| 54 | Completed | Create a Windows installer with application icon, Start Menu entry, optional desktop shortcut, guided installation, clear install location, user-data preservation, and clean uninstall support. |
| 55 | Completed | Ensure Windows upgrades preserve profiles, resumes, settings, companies, tracker/history data, reports, credentials, backups, and schedules while updating only application-owned files. |
| 56 | Completed | Add Windows installer repair, upgrade, and uninstall validation, including confirmation that uninstalling the application does not delete user data without explicit approval. |
| 57 | Completed | Add optional update checking that reports available stable releases without silently replacing the application or changing user data. |
| 58 | Completed | Package the application for Linux using a supported tarball-based distribution with launch scripts, dependency checks, user-data paths, migrations, logs, and clear install/uninstall instructions. |
| 59 | Completed | Support standalone local PC operation on Windows and Linux for users who want Job Radar to run only when they launch it. |
| 60 | Completed | Support unattended service-style operation on Windows and Linux for users who want scheduled scans without keeping the desktop application open. |
| 61 | Completed | Add container/server mode with persistent user data, configuration injection, logs, health checks, controlled upgrades, and the same service-layer behavior as the desktop application. |
| 62 | Completed | Support Kubernetes deployment with persistent storage, Secrets, configuration, health checks, scheduled scans, backups, retention, and safe upgrade procedures. |
| 63 | Completed | Write complete installation, guided setup, profile management, company management, email, scheduling, backup, restore, troubleshooting, upgrade, and uninstall documentation for Windows users. |
| 64 | Completed | Write complete installation and operations documentation for Linux standalone mode, Linux service mode, container mode, and Kubernetes mode. |
| 65 | Completed | Add automated release validation for clean installation, first launch, guided setup, initial scan, application restart, upgrade, migration, backup, restore, and uninstall behavior. |
| 66 | Completed | Test packaged builds on clean Windows and Linux environments that do not contain the development repository, Python virtual environment, existing settings, or developer tools. |
| 67 | Completed | Add release-candidate acceptance testing using a new-user workflow from installer download through first report, application tracking, restart, update, backup, restore, and uninstall. |
| 68 | Completed | Resolve all release-blocking defects, incomplete setup paths, unexplained errors, broken migrations, packaging failures, data-loss risks, accessibility blockers, and documentation gaps found during release-candidate testing. |
| 69 | Completed | Verify junior remains responsive with large real-world datasets, including 100 or more companies, 100,000 or more scanned jobs, several years of application history, and multiple profiles; identify and fix performance bottlenecks before the first stable release. |
| 70 | Planned | Publish the first fully productized stable release with installer downloads, checksums, release notes, screenshots, supported-platform details, upgrade instructions, known limitations, and verified documentation. |
| 71 | In Progress | Finalize the product finish line: a user can download Job Radar, run the installer, launch the application, complete guided setup, add their own profile and companies, run and schedule scans, review reports, manage applications, preserve and back up their data, upgrade safely, and use the product daily without editing code or YAML. |

## RC5 field-test acceptance requirements

These corrections must be implemented and verified before RC5 is accepted:

- Normal users must never be asked to enter or generate Junior's internal job
  ID. Creating an application from a scan must preserve the scan-owned ID;
  creating one manually from LinkedIn or any other outside source must generate
  an app-owned ID when Save is selected. Internal IDs may remain available to
  CLI diagnostics and compatibility code but must not appear as normal form
  fields or user-facing report content.
- Company discovery must use a broad but bounded tool chest: known ATS URL
  patterns, redirects and canonical links, career-page links, scripts and
  structured data, sitemaps where appropriate, custom ATS domains, multiple
  compatible collector probes, and the consent-controlled external
  company-source lookup defined below when the submitted corporate page is
  separated from the real careers system.
- Junior must show understandable progress while discovery runs, verify that
  the selected collector returns credible public jobs before saving the
  employer, and retain only the final working source and safe health summary.
  Rejected URLs, probe responses, failed configurations, and temporary search
  evidence must not accumulate in SQLite, logs, or company setup requests.
- Discovery must be tested against a varied acceptance set covering major ATS
  platforms, branded custom domains, corporate landing pages, client-rendered
  sites, redirects, blocked pages, empty job boards, malformed URLs, unrelated
  search results, and genuinely unsupported sources. No single successful
  employer or collector family is sufficient evidence that discovery is
  release-ready.
- When automatic discovery cannot establish a credible job source, Junior must
  leave no half-configured employer, explain what it tried in normal language,
  and provide safe retry, removal, and support paths without exposing raw
  network or collector failures.

### External company-source lookup (Release Requirement)

Junior remains local-first. It must exhaust local source detection and its
packaged collector catalog before contacting an external search provider.

| Requirement | Status Planned/Completed | Release behavior |
| --- | --- | --- |
| Local-first trigger | Completed | An external lookup may run only after local source detection and packaged collector probes cannot identify a working source. |
| Service disclosure | Completed | Junior must identify the specific external service before sending a request and must document any future provider change. |
| Exact payload disclosure | Completed | Junior must disclose the exact request payload, including every transmitted field, and the network metadata the provider may observe, including the user's IP address. |
| Data minimization | Completed | Only the minimum public company identity may be sent: company name and public domain. Profile information, résumé contents, desired roles, locations, application history, contact details, database contents, URL paths, query parameters, and fragments must not be sent. |
| User consent and control | Completed | External Bing lookup must be controlled by one installation-wide on/off setting that defaults to **Off**. Settings must clearly explain its limited advantage, transmitted data, privacy tradeoffs, and lack of guaranteed availability. Changing it must affect only future company setup attempts, never existing companies or normal scans. |
| Bounded timing | Completed | Public page and search requests have individual timeouts, unfamiliar-source discovery stops after two minutes, and the Add Company page shows an animated checking state. A timeout writes no employer or profile assignment. |
| Offline and unavailable-service behavior | Completed | Junior must explain that local discovery completed but the optional external lookup could not run. It must not silently retry later, create an unfinished company, or imply that the source works. |
| Independent validation | Completed | External lookup results are never authoritative. They may propose candidate career sources, but Junior independently validates every suggested source using its normal collector validation before saving anything. |
| Transient working data | Completed | Candidate sources, failed probes, intermediate search results, and external-search responses are transient. They do not become durable application data unless a final company source has been independently validated and accepted. |
| Visible lookup outcome | Completed | Junior must tell the user when an external lookup was used and whether it found a source, without exposing raw search responses or unsafe diagnostics. |

### Current implementation (RC5 observations)

- RC5 uses Bing only when the installation-wide setting is enabled and the
  submitted public page, local source detection, packaged collector probes,
  and generic HTML collection do not produce a working source. The setting
  defaults to Off, and normal scans never use Bing.
- The Bing request currently sends a search phrase derived from the submitted
  company name and public hostname plus the words `official careers jobs`, and
  requests an RSS response.
- The search request currently has a 20-second timeout. Failed requests return
  no candidates and do not create a company.
- The complete unfamiliar-source discovery operation stops after two minutes.
  The interface shows an animated checking message while it runs. If the limit
  is reached, Junior saves no employer or profile assignment and offers a safe
  retry.
- Junior independently runs normal collector validation against candidate
  sources and saves only a source that returns a credible public job.
- Candidate URLs, rejected search results, failed configurations, probe
  responses, and the external-search response remain temporary and are
  discarded after the request.
- The installation-wide setting, default-Off behavior, service identity,
  exact-payload disclosure, and separation from normal scans are implemented,
  covered by focused tests, and verified in an isolated browser review.
  The interface now distinguishes an unavailable service from a completed
  lookup with no independently verified source, creates no unfinished company,
  never schedules a silent retry, and is covered by the same two-minute
  end-to-end limit as local discovery.
- Company detail pages now accept optional shared Website, Careers, LinkedIn,
  and Glassdoor reference links. They are browser shortcuts only: Junior does
  not authenticate to or scrape those services, and link edits preserve the
  validated collector and its connection-health history.

- Scan collectors and practical-eligibility evaluation must retain and inspect
  explicit posting facts such as work location, remote or on-site requirements,
  employment type, temporary or contract duration, work schedule, compensation,
  and work authorization when the source provides them.
- A clearly Amsterdam-based role must not be treated as having unknown location.
  It must be compared with the active profile's allowed workplace arrangements,
  locations, residency plans, and relocation choices.
- A stated duration such as **3 months** must be identified and shown in the
  plain-language explanation. Any decision to reject short-term work must come
  from an explicit profile-owned preference rather than a global assumption
  that short contracts are unsuitable for everyone.
- Every visible scan result must offer a clear **Pass / don't show again**
  action. Confirming it must create a durable, profile-owned decision and omit
  that exact source job from future reports and notifications.
- Every visible scan result must also offer **Save for later** without implying
  that the user applied. Saved jobs must have a profile-owned workspace of
  their own and must not inflate Active Applications, application-history
  counts, or applied-job metrics.
- Saved Jobs and Reviewed Jobs must remain job-decision records, not application
  records. They may share one compact workspace with separate **Saved for
  later** and **Reviewed / passed** views, but neither view may be counted as
  Active Applications or Application History.
- From Saved Jobs, the user must be able to open the posting, add notes, select
  **I applied — track application** to move the job into Active Applications,
  or select **Pass** to move it into Reviewed Jobs. Each transition must
  preserve the scan-owned job ID and source evidence rather than create a
  duplicate.
- Active Applications must contain only jobs the user says they applied for.
  Application History must contain only completed applications, such as
  rejected, withdrawn, or closed applications. Passing on a job before applying
  must not create an application or application-history record.
- Junior's recommendation label **Needs your review** must remain separate
  from the user's saved state. It means Junior recommends more review; Save
  for later means the user deliberately bookmarked the job. The interface
  must explain the distinction in plain language.
- Report groups and Saved Jobs must support practical multi-select actions so a
  user can save or pass several reviewed jobs without opening each one. The
  operation must be profile-specific, explicit, and all-or-nothing.
- Passing a job must not delete the shared collected job, hide it from another
  profile, penalize the employer, or suppress unrelated jobs with similar
  titles. Matching should prefer the source job ID and use Junior's durable
  canonical identity only when the source does not supply an ID.
- The action must explain what will happen, allow cancellation before saving,
  and remain reviewable through the profile's Reviewed Jobs view so an
  accidental pass can be corrected.
- Reviewed Jobs may retain a bounded profile-owned reason such as location,
  compensation, contract duration, responsibilities, experience level, lack of
  interest, duplicate or stale posting, or Other. RC5 may store this feedback,
  but it must not silently change scoring or recommendation rules until that
  learning behavior is separately designed, explained, tested, and approved.
- Before adding storage or migrations, implementation must inventory existing
  Tracker, Application History, report, scan-history, and profile-decision
  services and reuse their ownership and identity boundaries. It must not
  create overlapping job copies or a second application tracker.
- Any existing Passed record must be classified from verified evidence before
  migration. A record with no evidence that the user applied may move to
  Reviewed Jobs; a completed real application remains in Application History.
  Migration must be backed up, reversible, idempotent, and preserve uncertain
  records for review instead of guessing or deleting them.
- Focused tests must cover explicit foreign location, short contract duration,
  profile isolation, repeat scans, saved-to-applied transitions, saved-to-pass
  transitions, application-history boundaries, duplicate prevention, bulk
  actions, changed postings, missing source IDs, cancellation, migration, and
  restoration. Full release validation and a normal-user visual check remain
  required.

### Current job-decision implementation (RC5)

| Requirement | Status | Verified behavior |
| --- | --- | --- |
| Individual report actions | Completed | Every structured scan-result classification, including Potential Top Matches and Passed / Not Recommended, offers notes, Save for later, Pass / don't show again, and I applied — track application. |
| Profile-owned Saved and Reviewed workspace | Completed | Saved and passed jobs remain separate from Active Applications and Application History and are isolated to the active profile. |
| Exact-job suppression | Completed | Saved and passed job IDs are omitted from later reports for that profile without deleting the shared posting. |
| Reversible decisions | Completed | A saved bookmark can be removed, a saved job can be passed, and a passed job can be allowed in future scans again. |
| Saved-to-passed reliability | Completed | A saved job's notes, pass reason, and Pass action share one explicit form. The transition stores the current details, reports validation problems to the user, and writes only bounded privacy-safe troubleshooting fields. |
| Scan-owned application identity | Completed | Choosing I applied preserves Junior's scan-owned job ID and source evidence in the application form. |
| Notes and decision reasons | Completed | Individual Save and Pass decisions accept human-only notes up to 300 characters. Passing supports a bounded listed reason, stores both per profile, and neither notes nor reasons alter scoring. |
| Multi-select report actions | Completed | Report groups can save or pass selected jobs in one profile-owned transaction; any invalid selected job rolls back the complete operation. |
| Responsive Review Jobs workflow | Completed | Scan completion leads to an undecided-only Review Jobs inbox. Every group removes saved, applied, and passed jobs while durable profile-owned actions continue across later scans. Each group renders at most 20 full cards per page; Review Needed can instead show 50 collapsed summaries with current-page-only bulk selection and navigation at both ends. Applying returns to the originating group. Reports is a separate page for the latest read-only outputs and optional retained history. |
| Complete report exports | Completed | Reports provides direct downloads for current and retained readable reports plus a compressed plain-text raw scan containing every public posting collected in the run. New installations retain 10 successful report runs by default, existing saved policies remain unchanged, and normal pages do not render thousands of raw job cards. |
| Practical-detail extraction | Completed | Conservative parsing fills missing ATS fields only from explicit workplace, employment-type, and annual-pay wording, including common HTML pay headings, encoded dash characters, and USD range labels. Concrete cities, named offices, and city/state title suffixes are evaluated as location-bound unless the posting explicitly states remote work; arrangement and location are shown separately on review cards. Missing schedule wording is neutral while explicit conflicts remain enforced. Jobs meeting existing top-match score and strong-signal rules with unresolved practical facts appear as Potential Top Matches with evidence and waiting-on explanations; thresholds remain unchanged. |

## Planned RC6 distribution and support improvements

RC6 is reserved for stabilization work discovered during RC5 field testing and
the following distribution and support improvements. These items are planned;
they are not part of SP5 Build 1.4 unless marked Completed:

| RC6 work item | Status | Required result |
|---|---|---|
| Build-aware update checking | Completed | Identify newer field-test builds even when the application version is unchanged. Checking remains read-only. In the installed Windows desktop app, a separate explicit user action downloads only the exact installer and checksum from Junior's official GitHub release, verifies the SHA-256 checksum, closes Junior, installs the update, and reopens it. Browser, server, and development modes use the verified release link instead. User-owned data remains outside the installation and is not replaced by the updater. Keep Microsoft Store and direct GitHub update paths clearly distinguished. |
| Privacy-safe support workflow | Planned | Add a **Contact support** action that prepares a sanitized diagnostic bundle, opens the user's default email client with the approved support address, subject, installed build, operating system, and safe instructions pre-filled, and tells the user exactly which file to attach. Never attach or send anything automatically. Explicitly warn users not to send résumés, databases, credentials, tokens, profile contents, or other private data. |
| Microsoft Store and MSIX distribution | Planned | Create and validate an MSIX distribution suitable for Microsoft Store certification while keeping Junior free to users. Use Microsoft-managed Store signing and update delivery where available. Verify first install, launch, icon and desktop behavior, external links, notifications, clean shutdown, user-data paths, SQLite access, credentials, scheduled scans, upgrade, rollback/recovery, and uninstall without risking existing user-owned data. Keep the GitHub distribution channel available. |
| GitHub release signing | Planned | Apply for the free SignPath Foundation open-source signing program and design a verifiable GitHub Actions build-and-sign workflow that satisfies its review, identity, provenance, approval, privacy-policy, and code-signing-policy requirements. If Junior is not accepted, reassess Microsoft Artifact Signing before purchasing a commercial certificate. Do not treat checksums as a replacement for code signing. |
| Release authenticity and signing gate | Planned | Document the publisher identity, official download locations, checksum verification, signing policy, certificate ownership, timestamping, key custody, renewal, revocation, and recovery behavior. Test signed installation, in-place upgrade, repair, uninstall, and signature verification before making signing a stable-release requirement. |

The Microsoft Store path must use MSIX if Junior is to receive Store-managed
signing without purchasing a separate certificate. Submitting the existing EXE
installer directly would still require Junior to provide its own trusted
Authenticode signature. Store distribution must not replace the open-source
repository or the direct GitHub release channel.

## Planned RC7 language assistance

After the RC6 stabilization and distribution work, RC7 introduces one
deliberately narrow language-model capability under this governing product
rule:

> **Junior explains. Junior does not decide.**

The first and only RC7 language-model capability is **Explain this job**.

| Requirement | Status | Required behavior |
| --- | --- | --- |
| Provider-neutral boundary | Planned | Junior uses one internal language-assistance service so normal workflows never depend directly on a particular model or provider. |
| Local-first setup | Planned | Local processing is recommended and setup is performed through the GUI without terminal commands, model-server addresses, or manual configuration files. |
| Online processing default | Planned | Every online provider is disabled by default. Enabling one requires clear disclosure of the provider, exact transmitted fields, purpose, credential storage, retention implications, timeout, and offline behavior. |
| Explain this job | Planned | On explicit request, Junior explains the current posting using the posting, relevant profile evidence, and Junior's existing structured findings in plain language. |
| Evidence and uncertainty | Planned | The explanation identifies its supporting evidence, distinguishes known facts from interpretation, and plainly states when information is missing or uncertain. |
| No decisions | Planned | Language assistance does not change scores, eligibility, recommendations, profiles, preferences, target titles, company selections, saved or passed state, application state, or scan scope. |
| No learning | Planned | RC7 does not infer or learn preferences from notes, reviewed jobs, application outcomes, or language-model responses. |
| Optional operation | Planned | Scanning, scoring, review, tracking, reports, and every existing workflow continue to work when language assistance is disabled, offline, unavailable, or removed. |
| Privacy and storage | Planned | Junior sends only data explicitly required for the requested explanation, stores no provider response as a new source of truth, and never includes credentials, unrelated profiles, unrelated applications, or the complete database. |
| User control | Planned | The user starts each explanation. Junior does not silently call a model during scans or background work and never acts on an explanation without a separate explicit user action. |

## Protected wording notes

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

Foundation 7H is complete: a normal user can enter a company name or public careers URL. Junior normalizes the input, checks exact catalog identity and aliases, prevents silent ambiguous merges, recognizes supported career-site families centrally, creates and assigns only confidently complete sources in one transaction, and rejects local or private destinations. Later release-candidate work added bounded public source probing: Junior follows public redirects, inspects advertised ATS links and metadata, tries only collector configurations it can derive safely, and saves any newly detected source only after its collector returns a credible public posting. When a submitted landing page is blocked or separated from the real job site, Junior can perform a limited public lookup using only the company name and domain, reject unrelated results, validate the candidate collector, and discard all unsuccessful candidates without creating database records. The normal company detail page now exposes safe source health, recruiting-platform identity, last-check time, and returned-job count, with a non-destructive retest action that does not require Administration access.

Guided source confirmation is complete: when a public Greenhouse, Lever, or Ashby URL contains enough information for scan-ready setup, Junior displays the detected provider and company identity but writes nothing until the user explicitly confirms. Confirmation re-normalizes and re-detects the submitted public URL on the server, then uses the existing atomic create-and-assign boundary. Existing catalog matches still require a direct choice, while uncertain and unsupported sites remain in administrator review.

GUI company management is complete: the unlocked Employer Catalog can create, edit, locally validate, connection-test, enable, disable, retire, and inspect every shared employer. An administrator can assign an available validated employer to any managed profile or remove one profile's assignment without changing another. Permanent deletion requires typed confirmation and remains blocked while any profile assignment or collected job references the employer.

Shipped and user-owned company boundaries are complete: new installations receive an empty packaged company list, while an existing legacy list can be imported once for the active profile. Import conflicts preserve the database employer, so a packaged or legacy definition cannot overwrite a user's later catalog edits. Subsequent GUI changes stay in the user-owned database and do not rewrite shipped or legacy YAML.

About and Version information is complete: Settings links to a read-only page showing the installed application version, stable or pre-release channel, resolved user-data location, current database migration version, profile schema version, and approved support contact. The page shows no profile content, résumé content, credential value, or raw diagnostic failure.

Safe credential storage is complete: desktop secrets can be stored, retrieved, and removed through the operating system credential manager using the packaged `keyring` adapter. Ordinary settings contain only a non-secret stable reference. Existing environment-variable references remain supported for automation, servers, containers, and upgrades. Missing or unavailable secure backends fail with sanitized guidance and never fall back to YAML, SQLite, logs, reports, or a home-grown credential file.

Email setup and connection testing are complete: normal users can choose Gmail, Outlook, or Custom SMTP; enter sender, recipients, username, and a credential; review where the credential is stored; and atomically save validated settings without putting the password in YAML or SQLite. Test Connection performs only network connection, TLS negotiation, and authentication. It sends no message and starts no scan or report. A session-scoped card shows the provider, last test time, result, storage method, and plain-language reason without retaining a password or server response. The ordinary interface reports only Connected, Not configured, Authentication failed, Server unreachable, TLS negotiation failed, or secure-storage unavailability, never a raw SMTP exception. This card is the first instance of the reusable green/yellow/red service-health pattern planned for diagnostics and GUI consistency work.

Foundation 7I is complete: the Administration-only Employer Review Queue can inspect safe unresolved submissions, match an existing employer, prefill new-employer setup, optionally assign an available employer to the requesting profile, or mark a request unsupported, rejected, or duplicate. Decisions are audited without raw collector failures or profile content, while normal users see only their own plain-language request state.

Foundation 7J1 is complete: the active profile can view deterministic recommendations from scan-ready employers already in the local Employer Catalog. Scan readiness alone never qualifies an employer; matching desired-role metadata or profile-owned matching-job evidence is mandatory. Assigned, unrelated, and unavailable employers are excluded, grounded catalog overlap is explained in plain language, numeric ranking remains internal, and Add, Maybe later, Dismiss, and Not relevant responses persist independently per profile with bounded cooldowns where appropriate.

Foundation 7J2 is complete: future scan runs record their owning profile, and recommendation ranking can use a bounded 90-day window of up to 500 recent postings per employer from that profile's scans. Junior transparently explains relevant-job counts, strong title matches, compatible remote jobs, workplace or location conflicts, sufficiently reliable below-floor compensation patterns, and recency. Applications and rejections do not automatically imply employer interest. Unowned legacy scans are ignored, evidence remains deterministic and profile-isolated, and the existing feedback rules continue to control visibility.

Foundation 7J3 is complete: Junior can suggest up to 50 fresh employers from the last 90 days of profile-owned discovered job data even when they are absent from the Employer Catalog. Candidates require jobs matching the profile's desired roles; profiles without desired roles receive no speculative suggestions. Candidates record discovery source and time, identify likely catalog matches and unsupported sources, remain isolated per profile, and expire with stale evidence. Review never silently creates or scans a weak candidate; unresolved employers flow into the existing Employer Review Queue. Candidate generation performs no uncontrolled network calls.

Foundation 7K is complete: guarded Recommendation Administration can maintain global employer aliases, industries, occupation families, employer type, geographic presence, remote-hiring information, and recommendation eligibility. An administrator can inspect stored score, positive and negative evidence, feedback, availability, and timestamps for one profile/employer pair without exposing numeric ranking to normal users. Feedback reset is explicitly confirmed, profile-specific, and audited. Rebuilds are bounded to one profile or one employer unless the administrator types `REBUILD ALL`; rebuilds preserve saved feedback.

Foundation 7L is complete: Role Discovery and Title Mapping suggests adjacent work only when profile-owned résumé evidence supports packaged O*NET responsibilities or a job description already observed during that profile's scans. Similar wording alone is insufficient, guarded technical disciplines require explicit résumé evidence, and weak evidence yields no suggestion. Every suggestion explains the matched evidence, observed-job suggestions retain employer context, and feedback remains profile- and context-specific. Relevant is the only decision that joins the existing target-role recommendation boundaries; Not relevant and Different discipline remain durable rejections. No suggestion is approved automatically, no internal score is displayed, and the established job-scoring formula is unchanged.

Foundation 7M is complete: the normal Companies GUI no longer exposes or manages legacy `target-companies.yaml` records. A user without an active managed profile receives a clear profile setup action, and direct legacy-company detail routes are unavailable. Protected one-time import remains available to existing upgraded profiles, while released CLI/server scans without a managed profile retain YAML compatibility to avoid an unapproved breaking change.

Company connection testing is complete: an administrator can separately validate stored setup and run the employer's real collector without importing or scoring returned jobs. Junior records the last attempt, last successful connection, last problem, returned-job count, and a bounded troubleshooting category. Raw collector, HTTP, response-body, and exception text is not persisted or displayed. Editing source configuration clears stale health so an old success cannot describe new settings.

The company workspace, employer-recommendation, and profile-owned Role Discovery sequences are complete. Other major product areas include guided first-run validation, editable Settings and credential workflows, scheduling, user-facing backup and recovery, and final desktop packaging.

First-run detection and resumable setup are complete: after safe desktop bootstrap, a genuinely empty database opens a dedicated setup welcome page. Existing profiles, employers, jobs, Tracker records, or History records prevent first-run mode, so upgrades and established installations are not redirected into onboarding. Once setup starts, SQLite records the current profile, résumé, companies, or review checkpoint. Restarting returns to that checkpoint, and setup is completed only through the explicit review action. Existing user data is not inferred, replaced, or removed.

The first-run review is complete: before finishing setup, the user can verify the active profile, résumé status, target work, job and employment preferences, workplace arrangements, compensation, travel, selected locations, company counts, local data location, and plain-language scan behavior. Review links return to the existing profile and company workflows instead of introducing a second set of save rules.

The first-run validation scan is complete: setup checks that the active setup profile has target work and workplace choices, requires commute locations when hybrid or on-site work is selected, and uses the shared company connection service to confirm at least one selected Scanning source works. It imports, scores, recommends, reports, and emails no jobs. Finish setup stays unavailable until the test passes, and failed profile or source checks remain visible in plain language for correction and retry.

The guided first-run profile step is complete: it collects the profile name, target occupations, job levels, employment and schedule preferences, workplace arrangements, commute locations, compensation floor, travel tolerance, and optional roles or responsibilities to avoid. Exclusions remain profile-owned and bounded; they do not introduce dictionary-synonym title expansion or change the established scoring formula.

The projected full-product target remains September 30, 2026. Milestone quality, user-data safety, and dependency order take precedence over the date.
