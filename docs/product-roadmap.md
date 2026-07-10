# Job Radar Product Roadmap

Last updated: 2026-07-10

## Purpose

This document owns Job Radar's future direction, MVP finish line, post-MVP roadmap, and deferred scope.

Current implementation state, setup commands, capabilities, and operating guidance belong in `README.md`. Repository structure belongs in `docs/file-map.md`.

## Product goal

Job Radar started as a personal job discovery, scoring, reporting, and application-tracking tool.

The long-term product direction is to make Job Radar a configurable local-first job search assistant that another user can install, configure, and use without editing source code.

The finish line is not a hosted SaaS product and not an automated job-application bot.

Job Radar is complete-enough when a user can install it, configure their own job search profile, add desired companies, run scans, review scored jobs, track applications, and receive reports without editing source code.

## Product principles

Job Radar should remain local-first, user-controlled, configured-company based, safe for manual review, transparent in scoring and recommendations, non-invasive, not dependent on broad crawling, not dependent on LinkedIn scraping, not responsible for contacting employers, and not responsible for submitting applications automatically.

The app should help the user decide where to spend time. It should not pretend to replace the user.

## MVP finish line

The immediate MVP target is a single-user local app that demonstrates disciplined execution and practical usefulness.

MVP is complete when:

1. A single local user can launch the GUI reliably.
2. The user can run or review scans from configured company sources.
3. The user can review Markdown/HTML reports and email previews.
4. The user can manage active applications in the GUI.
5. The user can add manual applications without inventing tracker IDs.
6. The user can edit tracker records and use common quick actions.
7. The user can move terminal applications from tracker to history.
8. The user can reopen history records back to tracker when needed.
9. The dashboard surfaces application follow-up work clearly.
10. Resume upload/replacement works through the GUI.
11. Settings and Companies pages provide safe read-only visibility.
12. The app preserves tracker/history mutual exclusivity.
13. The app preserves app-owned Job Radar IDs.
14. The app keeps private runtime data out of Git.
15. The test suite remains green.
16. Documentation is consolidated enough to stay maintainable.

## Current MVP shape

Current shape:

```text
Python CLI + SQLite + local Flask GUI + configured company scanners
```

Current strengths:

- configured target-company scanning
- multiple ATS/source collectors
- SQLite-backed scan and tracker storage
- rules-based scoring
- Markdown/HTML reports
- email preview/send guardrails
- application tracker CLI
- local Flask tracker/history/report/companies/scan/settings GUI
- clickable tracker dashboards and workflow navigation
- GUI tracker Needs Review queue
- GUI tracker quick actions
- GUI history/archive summary cards and quick filters
- GUI scan/report flow polish
- latest scan result shortcuts
- report viewer copy/select support
- user-facing reassurance for temporary source/company scan errors
- read-only GUI Companies page foundation with card-driven filters, search, service-layer config views, write-strategy readiness checks, and detail pages
- read-only GUI Settings page foundation
- GUI profile/resume upload support
- app-assigned tracker IDs for spreadsheet-imported and GUI-created manual application records
- legacy `posting-url:*` tracker ID repair
- spreadsheet import bridge
- sanitized example workbook

The main current limitation is that the app still depends on developer-style configuration and manual file editing for setup tasks such as company management, preference/scoring setup, email setup, scheduling, and runtime data location.

## Near-term MVP priorities

1. Dashboard follow-up focus for applications needing action.
2. MVP polish for the single-user local workflow.
3. Editable Settings page where safe and low-risk.
4. Email settings page with secret-safe validation.
5. Scheduled scan and scan-history retention settings page.
6. Complete profile/preference setup beyond resume upload.
7. Runtime data location setup.
8. Packaging/launcher preparation.

## Deferred until after MVP

The following are valid long-term goals, but are intentionally deferred until the single-user MVP is stable, polished, tested, and portfolio-ready:

- editable company management
- company/contact relationship tracking
- database-backed company inventory
- GUI company add/edit
- YAML-backed company writes
- multi-user login/password support
- full onboarding wizard
- LLM-assisted strengths/gaps analysis
- generalized multi-domain job-hunt workflows
- full knowledge-base attachment system
- hosted SaaS behavior
- automatic job applications
- employer outreach automation
- LinkedIn scraping
- mobile app
- native desktop GUI rewrite

## Long-term product vision

The long-term product vision is a full job-hunt operations system.

It should eventually help users manage the many moving pieces of a job search: profile creation, resume upload and analysis, strengths and gaps, preferred companies, email setup, scheduled scans, dashboard workflow, application tracking, follow-up reminders, company research, contacts, recruiter history, and interview preparation.

The application should eventually behave more like an IT ticket system than a static spreadsheet:

- applications requiring follow-up should be flagged
- stale items should surface on the dashboard
- active records should have workflow state
- terminal records should move to history/archive
- companies should act like an inventory/knowledge-base area
- contacts should be tracked when available, but not required

The app should eventually become useful beyond IT job hunts, but the current MVP should stay focused on the existing single-user workflow.

## Future product shape

Target shape:

```text
Cross-platform local-first application + SQLite + guided setup + configurable job search profile
```

Job Radar should support three launch/deployment targets without becoming three separate products:

```text
Windows packaged app
Linux packaged app
Container/server mode
```

The current Flask GUI is the shared web/server interface. It should remain usable directly in browser/server mode and should also be able to sit behind a future desktop wrapper or launcher for normal click-to-open desktop use.

The final product should hide developer launch commands from normal users. A user should eventually open Job Radar from a Start Menu shortcut, Linux application launcher, packaged executable, or container/service URL depending on how they choose to run it.

The user should eventually be able to install Job Radar, open it from a normal launcher, create/edit their search profile, add target companies, define preferred roles, salary expectations, location rules, blocker rules, positive match signals, run scans manually, schedule scans, configure scan history retention, review results, track applications, review job history, configure email reports, and export or back up local data.

## Complete-enough product definition

Longer-term complete-enough means:

1. A non-developer user can install and launch the app.
2. A user can configure their own companies without editing source code.
3. A user can configure their own ATS/source settings without editing source code.
4. A user can configure their own preferences without editing source code.
5. A user can configure their own salary floor and ideal salary.
6. A user can configure their own acceptable locations and remote/hybrid/on-site rules.
7. A user can configure their own role interests, seniority targets, and avoid rules.
8. A user can configure email reporting through a user-friendly setup flow.
9. A user can run a scan from the GUI.
10. A user can review scan results from the GUI.
11. A user can track active applications from the GUI.
12. A user can review historical, passed, skipped, rejected, and archived jobs from the GUI.
13. A user can create manual applications from the GUI without manually inventing tracker IDs.
14. A user can schedule recurring scans.
15. Runtime data is stored outside the source/repo directory.
16. Real user data is not committed to Git.
17. The app can run as a standalone program on a user's PC.
18. The app can run unattended as a service on a user-controlled system.
19. The app can run in Kubernetes when that matches the user's setup.
20. The app can be packaged for Windows with an `.exe` entry point and installer.
21. The app can be packaged for Linux using a `.tar` or tarball-based distribution.
22. Documentation clearly separates developer setup from user setup.
23. Existing CLI/test/report behavior does not regress.

## User configuration requirements

Job Radar must stop assuming one hard-coded user profile.

The app should eventually support user-specific configuration for user name/profile label, desired role titles, seniority levels, desired/excluded companies, preferred/excluded industries, positive/negative keywords, hard blockers, soft risk signals, salary floor, ideal salary, acceptable/preferred locations, remote/hybrid/on-site rules, relocation openness, travel tolerance, security clearance tolerance, employment type preference, resume/profile text, report preferences, scan history retention, email preferences, and scan schedule.

## Desired companies

For MVP, the Companies page remains read-only scan/source inventory.

Long term, users need a way to add desired companies without editing YAML manually.

Required long-term behavior:

- add company from GUI
- edit company from GUI
- disable company without deleting it
- delete company if needed
- choose source type when known
- store company career page URL
- store ATS/source-specific identifier when needed
- validate company source configuration before saving when possible
- show whether the source works
- show last scan result per company
- show collector errors per company
- allow targeted company/source rescan when practical
- allow import/export of company lists

The GUI should eventually support a company setup flow:

```text
Company name
Career page URL
Source type
Remote/location relevance
Notes
Enabled yes/no
Test source button
Save
```

Normal GUI company data should eventually live in SQLite or user data, not as risky direct YAML mutation. YAML may remain useful for seed/default source definitions. If YAML writes are ever supported, they require a comment-preserving writer such as `ruamel.yaml`.

## Preferences and scoring setup

Users need guided preference setup for salary floor, ideal salary, acceptable/preferred locations, remote-only or remote-preferred behavior, target roles, acceptable seniority levels, positive keywords, negative keywords, blockers, review-needed signals, and avoid-company or avoid-industry rules.

The GUI should eventually explain what each setting does in plain language.

## Profile and resume setup

The current profile and resume flow has started moving into the GUI, but broader profile setup is still too user-specific.

Long-term behavior:

- create a user profile from the GUI
- add, paste, upload, or replace resume/profile text from the GUI
- preserve the current GUI resume upload/replacement flow
- keep PDF, DOCX, Markdown, and plain-text resume loading supported
- store resume/profile text in the user data directory
- allow the user to update it
- use it for match signals
- avoid committing private profile/resume data to Git
- mirror the existing CLI resume/profile process instead of creating a separate GUI-only resume system
- reuse the same resume loader/profile logic used by scans and CLI commands

Future user-data layout should separate shipped app files from personal data.

Windows target:

```text
%LOCALAPPDATA%\JobRadar\
  settings.yaml
  profile.yaml
  companies.yaml
  preferences.yaml
  job_radar.sqlite3
  reports\
  logs\
```

Linux target:

```text
~/.config/job-radar/
  settings.yaml
  profile.yaml
  companies.yaml
  preferences.yaml

~/.local/share/job-radar/
  job_radar.sqlite3
  reports/
  logs/
```

## Cross-platform app direction

Job Radar should be built as one core application with multiple launch targets, not as separate desktop, web, and server products.

Supported target modes:

- Windows packaged app
- Linux packaged app
- Container/server mode
- Developer CLI mode

Recommended path:

1. Keep Flask as the shared web/server UI.
2. Keep workflow/business logic in GUI-neutral services.
3. Add a friendly GUI launch command.
4. Add a local launcher that starts the app and opens the UI automatically.
5. Add container/server deployment.
6. Add desktop wrapper or packaged launcher for Windows and Linux.
7. Package Windows and Linux distributions.

## Installer and packaging roadmap

The long-term Windows target is `JobRadarSetup.exe`.

The Windows installation path should be simple enough for a non-developer user to install, launch, configure, and run a first scan without manually editing source files.

Likely Windows packaging path:

```text
PyInstaller + Inno Setup
```

Possible later alternatives include Nuitka, Briefcase, MSIX, NSIS, and WiX Toolset.

Linux should remain supported, but Windows packaging comes first. The required Linux packaging path is a `.tar` or tarball-based distribution. Possible later Linux formats include AppImage, `.deb`, systemd user service/timer, and Docker/container deployment.

## Deployment flexibility roadmap

Job Radar should be flexible enough to run in different user-controlled environments: Windows packaged desktop/local app, Linux packaged desktop/local app, unattended service on a local machine or small server, containerized web/server mode, Kubernetes service in a user-managed cluster, and developer CLI mode.

Deployment work must preserve one core service layer so CLI, Flask UI, desktop launcher/wrapper, scheduler, packaged deployments, and container/server deployments do not become separate products.

## Scheduler roadmap

Scheduled scans should eventually be configurable without editing scripts.

Windows target: Task Scheduler integration, user-selectable schedule, local logs, and safe failure behavior.

Linux target: systemd user timer, local logs, and safe failure behavior.

The scheduler should run the same scan pipeline as manual scans.

Scan history retention should be configurable from Settings. The default should favor the latest scan outputs, with optional retention such as latest plus previous scan or a configured number of retained scans.

## Data ownership and privacy

Job Radar should assume job search data is private.

Private data includes user profile, resume text, target companies, application history, tracker notes, recruiter/contact details, email settings, local reports, and logs that may contain job/application details.

Private data should live in the user data directory and stay out of Git.

The repo may include demo config, example config, sanitized workbook, documentation, tests, and non-private sample data.

## Staged roadmap

### Stage 1: Finish Current GUI Workflow

- Finish GUI-native tracker/history workflows so normal application tracking no longer depends on the spreadsheet.
- Preserve completed tracker workflow improvements.
- Make the GUI the source of truth for active applications, archived history, passed roles, rejected applications, dormant roles, and follow-up state.
- Preserve Tracker/History mutual exclusivity.
- Preserve app-owned tracker identity.
- Keep tracker/history workflow actions in GUI-neutral services.
- Decide the final role of the spreadsheet bridge.
- Keep scan/report behavior stable while GUI tracker/history behavior improves.

### Stage 2: User Configuration

- Build user-friendly configuration for desired companies, ATS sources, role preferences, compensation, location rules, exclusions, and email settings.
- Add configuration screens or guided setup so users do not need to hand-edit YAML for basic use.
- Add preference setup page.
- Add company management page.
- Add salary/location setup.
- Add resume/profile setup that mirrors the existing CLI resume/profile process.
- Move user-specific runtime config out of repo assumptions.

### Stage 3: Scheduling and Email

- Add email setup flow.
- Configure email from GUI.
- Support SMTP settings, sender/recipient configuration, safe test email, and clear failure messages.
- Configure scheduled scans from GUI.
- Keep secrets out of config files.
- Add clear validation and failure messages.

### Stage 4: Packaging and Deployment

- Prepare the app to run as a standalone desktop/local program.
- Keep the Flask GUI usable as the shared web/server interface.
- Add a friendly GUI launch command.
- Add a launcher that starts Job Radar and opens the UI automatically.
- Store user data in OS-appropriate location.
- Build Windows executable.
- Build Windows installer.
- Build Linux `.tar` / tarball distribution.
- Add container/server deployment.
- Support standalone PC operation.
- Support service-style operation.
- Support Kubernetes deployment.
- Add deployment-friendly configuration for persistent data, reports, logs, backups, retention, and safe upgrades.

### Stage 5: First-Run Experience and Stabilization

- Keep the app single-user by default, while leaving room for multiple profiles if useful.
- Create a simple first-run experience from installation to first scan/report.
- Improve user-facing error messages.
- Add backup/export path.
- Add import path for companies/preferences.
- Add onboarding documentation.
- Add recovery/troubleshooting documentation.
- Add installation and operations documentation for Windows desktop, Linux standalone/server, and Kubernetes service modes.
- Add release validation for packaged builds.
- Run no-regression validation.
