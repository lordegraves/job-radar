# Job Radar Product Roadmap

Last updated: 2026-07-09

## Purpose of this document

This file owns Job Radar's future direction, finish-line definition, and remaining milestones.

It should not duplicate the detailed current-state ledger from `docs/current-state.md`.

Use the documentation set this way:

- `README.md` — quick project overview, common commands, and user-facing capabilities
- `docs/current-state.md` — detailed current behavior and completed milestone state
- `docs/product-roadmap.md` — future direction, finish-line definition, and remaining milestones
- `docs/file-map.md` — repository structure and file ownership boundaries

## Product goal

Job Radar started as a personal job discovery, scoring, reporting, and application-tracking tool.

The long-term product direction is to make Job Radar a configurable local-first job search assistant that another user can install, configure, and use without editing source code.

The finish line is not a hosted SaaS product and not an automated job-application bot.

Job Radar is complete-enough when a user can install it, configure their own job search profile, add desired companies, run scans, review scored jobs, track applications, and receive reports without editing source code.

## Product principles

Job Radar should remain:

- Local-first
- User-controlled
- Configured-company based
- Safe for manual review
- Transparent in scoring and recommendations
- Non-invasive
- Not dependent on broad crawling
- Not dependent on LinkedIn scraping
- Not responsible for contacting employers
- Not responsible for submitting applications automatically

The app should help the user decide where to spend time. It should not pretend to replace the user.

## Current product shape

Current shape:

```text
Python CLI + SQLite + local Flask GUI + configured company scanners
```

Current strengths:

- Configured target-company scanning
- Multiple ATS/source collectors
- SQLite-backed scan and tracker storage
- Rules-based scoring
- Markdown/HTML reports
- Email preview/send guardrails
- Application tracker CLI
- Local Flask tracker/history/report/companies/scan/settings GUI
- Clickable tracker dashboards and workflow navigation
- GUI tracker Needs Review queue
- GUI tracker quick actions
- GUI history/archive summary cards and quick filters
- GUI scan/report flow polish
- Latest scan result shortcuts
- Report viewer copy/select support
- User-facing reassurance for temporary source/company scan errors
- Read-only GUI Companies page foundation with card-driven filters, search, service-layer config views, and detail pages
- Read-only GUI Settings page foundation
- GUI profile/resume upload support
- App-assigned tracker IDs for spreadsheet-imported and GUI-created manual application records
- Legacy `posting-url:*` tracker ID repair
- Spreadsheet import bridge
- Sanitized example workbook

Current limitation:

The app still depends on developer-style configuration and manual file editing for too many setup tasks, especially company management, preference/scoring setup, email setup, scheduling, and runtime data location.

Detailed current state belongs in `docs/current-state.md`.

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

The user should eventually be able to:

- Install Job Radar
- Open Job Radar from the Start Menu or application launcher
- Create or edit their search profile
- Add target companies
- Define preferred roles
- Define salary expectations
- Define location rules
- Define blocker rules
- Define positive match signals
- Run scans manually
- Schedule scans
- Configure scan history retention
- Review results
- Track applications
- Review job history
- Configure email reports
- Export or back up local data

## Finish line definition

Job Radar is complete-enough when these are true:

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

The app should eventually support user-specific configuration for:

- User name or profile label
- Desired role titles
- Desired seniority levels
- Desired companies
- Excluded companies
- Preferred industries
- Excluded industries
- Positive keywords
- Negative keywords
- Hard blockers
- Soft risk signals
- Salary floor
- Ideal salary
- Acceptable locations
- Preferred locations
- Remote/hybrid/on-site rules
- Relocation openness
- Travel tolerance
- Security clearance tolerance
- Employment type preference
- Resume/profile text
- Report preferences
- Scan history retention
- Email preferences
- Scan schedule

## Desired companies

Users need a way to add desired companies without editing YAML manually.

Required long-term behavior:

- Add company from GUI
- Edit company from GUI
- Disable company without deleting it
- Delete company if needed
- Choose source type when known
- Store company career page URL
- Store ATS/source-specific identifier when needed
- Validate company source configuration before saving when possible
- Show whether the source works
- Show last scan result per company
- Show collector errors per company
- Allow targeted company/source rescan when practical
- Allow import/export of company lists

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

Near-term version can still write to config files or a local database, but the user should not need to know the internal YAML format.

## Preferences and scoring setup

Users need guided preference setup.

Required long-term behavior:

- Set salary floor
- Set ideal salary
- Set acceptable locations
- Set preferred locations
- Set remote-only or remote-preferred behavior
- Set target roles
- Set acceptable seniority levels
- Set positive keywords
- Set negative keywords
- Set blockers
- Set review-needed signals
- Set avoid-company or avoid-industry rules

The GUI should eventually explain what each setting does in plain language.

Example setup questions:

```text
What roles are you looking for?
What titles should be treated as strong matches?
What titles should be avoided?
What locations are acceptable?
Is remote required?
What is your minimum salary?
What salary would make a role especially attractive?
What technologies or domains are strong positives?
What technologies or job duties are blockers?
Are there companies or industries you do not want?
How much travel is acceptable?
Are clearance-required roles acceptable?
```

## Profile and resume setup

The current profile and resume flow has started moving into the GUI, but broader profile setup is still too user-specific.

Long-term behavior:

- Create a user profile from the GUI
- Add, paste, upload, or replace resume/profile text from the GUI
- Preserve the current GUI resume upload/replacement flow
- Keep PDF, DOCX, Markdown, and plain-text resume loading supported
- Store resume/profile text in the user data directory
- Allow the user to update it
- Use it for match signals
- Avoid committing private profile/resume data to Git
- Mirror the existing CLI resume/profile process instead of creating a separate GUI-only resume system
- Reuse the same resume loader/profile logic used by scans and CLI commands

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

## GUI roadmap

The current Flask GUI should continue as the near-term interface.

Recently completed GUI work:

- History/archive summary cards and quick filters
- Rejected and withdrawn history quick-filter behavior
- Reports latest scan result shortcut cards
- Scan completion links to the main generated outputs
- Report viewer copy/select support
- User-facing reassurance for temporary source/company scan errors
- Read-only Settings page showing active runtime paths, retention settings, GUI scan defaults, and email status
- Read-only Companies page showing configured target companies, source types, enabled status, source details, notes, card-driven filters, search, and per-company detail pages
- Manual application add form no longer asks for Job Radar ID
- Tracker edit summary layout polish for long/generated IDs
- Legacy `posting-url:*` tracker ID repair surfaced through the GUI
- `/tracker/` redirect to `/tracker`

Near-term GUI priorities:

1. Editable company management page
2. Editable Settings page
3. Preference setup page
4. Email settings page
5. Scheduled scan and scan-history retention settings page
6. Complete profile/preference setup beyond resume upload
7. Runtime data location setup
8. Packaging/launcher preparation

The GUI should keep using the same service layer as the CLI.

The GUI must not become a separate source of truth.

Resume/profile GUI work must follow this same rule. Uploading or updating a resume through the GUI should feed the same profile/resume path and loader used by CLI scans.

## Cross-platform app direction

Job Radar should be built as one core application with multiple launch targets, not as separate desktop, web, and server products.

Supported target modes:

- Windows packaged app
- Linux packaged app
- Container/server mode
- Developer CLI mode

The current Flask GUI remains the near-term shared interface because it works for both local browser use and server/container use. A future desktop launcher or wrapper can start the same local app and display it in a normal desktop window.

Recommended path:

1. Keep Flask as the shared web/server UI.
2. Keep workflow/business logic in GUI-neutral services.
3. Add a friendly GUI launch command.
4. Add a local launcher that starts the app and opens the UI automatically.
5. Add container/server deployment.
6. Add desktop wrapper or packaged launcher for Windows and Linux.
7. Package Windows and Linux distributions.

This preserves current work while moving toward normal click-to-open desktop use and always-on server/container operation.

## Installer and packaging roadmap

The long-term Windows target is:

```text
JobRadarSetup.exe
```

The Windows installation path should be simple enough for a non-developer user to install, launch, configure, and run a first scan without manually editing source files.

The installer should eventually:

- Install Job Radar
- Create a Start Menu shortcut
- Create required local user data folders
- Install default/example config files
- Avoid overwriting existing user config
- Include the sanitized example workbook only as an import/template bridge
- Provide an `.exe` entry point or launcher
- Support first-run setup
- Support desired company setup
- Support ATS/source setup
- Support preference, compensation, and location setup
- Support email setup
- Support manual scan from the GUI
- Optionally configure scheduled scans
- Store runtime data outside the install directory

Likely Windows packaging path:

```text
PyInstaller + Inno Setup
```

Possible later alternatives:

- Nuitka
- Briefcase
- MSIX
- NSIS
- WiX Toolset

## Linux roadmap

Linux should remain a supported direction, but Windows packaging comes first.

The required Linux packaging path is a `.tar` or tarball-based distribution.

Possible later Linux formats:

- AppImage
- .deb package
- systemd user service/timer
- Docker/container deployment

Linux needs:

- Documented install path
- User config under `~/.config/job-radar/`
- User data under `~/.local/share/job-radar/`
- `.tar` / tarball install documentation
- Optional systemd timer for scheduled scans
- Optional service-style operation
- Clear no-root local mode where possible

## Deployment flexibility roadmap

Job Radar should be flexible enough to run in different user-controlled environments.

Supported target modes:

- Windows packaged desktop/local app
- Linux packaged desktop/local app
- unattended service on a local machine or small server
- containerized web/server mode
- Kubernetes service in a user-managed cluster
- developer CLI mode

The app does not need to support more than one user at a time. Multiple profiles may be useful later, but multi-user SaaS behavior is not required.

Deployment work must preserve one core service layer so CLI, Flask UI, desktop launcher/wrapper, scheduler, packaged deployments, and container/server deployments do not become separate products.

Flask is the current UI/server interface, not the whole product. Business workflow logic should live in reusable services that can be called by CLI commands, web routes, future desktop launchers, and scheduled jobs.

## Scheduler roadmap

Scheduled scans should eventually be configurable without editing scripts.

Windows target:

- Task Scheduler integration
- User-selectable schedule
- Local logs
- Safe failure behavior

Linux target:

- systemd user timer
- Local logs
- Safe failure behavior

The scheduler should run the same scan pipeline as manual scans.

Scan history retention should be configurable from Settings. The default should favor the latest scan outputs, with optional retention such as latest plus previous scan or a configured number of retained scans.

## Data ownership and privacy

Job Radar should assume job search data is private.

Private data includes:

- User profile
- Resume text
- Target companies
- Application history
- Tracker notes
- Recruiter/contact details
- Email settings
- Local reports
- Logs that may contain job/application details

Private data should live in the user data directory and stay out of Git.

The repo may include:

- Demo config
- Example config
- Sanitized workbook
- Documentation
- Tests
- Non-private sample data

## Complete-enough milestones

The finish line can be reached in stages.

### Stage 1: Finish Current GUI Workflow

- Finish GUI-native tracker/history workflows so normal application tracking no longer depends on the spreadsheet.
- Preserve the completed tracker workflow improvements: clickable dashboard cards, Needs Review queue, grouped quick actions, tracker-to-history movement, history-to-tracker reopening, history/archive quick filters, scan/report flow shortcuts, and app-assigned manual tracker IDs.
- Make the GUI the source of truth for active applications, archived history, passed roles, rejected applications, dormant roles, and follow-up state.
- Preserve Tracker/History mutual exclusivity: active rows belong in Tracker, archived or terminal rows belong in History.
- Preserve app-owned tracker identity: posting URLs are evidence/source links, not tracker primary keys.
- Keep tracker/history workflow actions in GUI-neutral services so Flask, CLI, desktop launcher/wrapper, scheduler, and container/server mode can reuse them.
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

## Not yet required

The following are not required for complete-enough:

- Hosted SaaS
- Multi-user server
- Employer outreach automation
- Automatic job applications
- LinkedIn scraping
- Mobile app
- Native desktop GUI rewrite
- LLM-driven scoring as the primary scoring engine

LLM-assisted review can be added later, but rules-based behavior should remain stable and explainable first.
