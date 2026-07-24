# junior

junior is a local-first job discovery, triage, reporting, and application-tracking tool.

It scans configured company career sites, normalizes and scores job postings, stores results in SQLite, and provides a local Flask interface for reviewing results, tracking active applications, and preserving application history.

junior does **not** apply to jobs automatically, contact employers, scrape LinkedIn, bypass authentication, or broadly crawl the internet.

## Status

- Current version: `0.1.0`
- MVP completed and acceptance-tested: July 14, 2026
- Current development branch: `feature/productization-foundation`
- Python requirement: 3.11 or newer

The current development build is a functional local application with up to five independent managed profiles. Python wheel, source-package, reproducible Windows executable, unsigned per-user Windows installer, Linux archive, container, and Kubernetes baselines are implemented and validated. A genuinely empty installation now opens a guided first-run path through profile creation, résumé upload, profile-owned work exclusions, company selection, and a final review. The setup checkpoint is stored safely in SQLite, so closing junior during setup returns the user to the last completed step instead of starting over. The review shows the profile, résumé, preferences, locations, companies, user-data location, and scan behavior. Finish setup remains unavailable until Junior verifies minimum usable profile rules and confirms at least one selected company collector can connect. This validation imports, scores, recommends, reports, and emails no jobs, and it explains corrections in plain language. Publicly signed release downloads, remaining editable configuration, and broader release-candidate work are still in progress.

See [CHANGELOG.md](CHANGELOG.md) for released and unreleased changes.

## Current capabilities

junior currently provides:

- configured-company scanning across multiple ATS and career-site formats
- Profile-owned active applications and application history stored safely in SQLite
- profile-owned scoring, occupation-neutral recommendation policy, compensation checks, and resume/profile matching
- structured scan snapshots and HTML reports
- plain-text and HTML email previews with guarded SMTP delivery
- a local Flask GUI with Home, Scan, Reports, Active Applications, Application History, Profile / Resume, Companies, and Settings pages
- GUI-managed profile creation, editing, selection, guarded deletion, and app-owned resume storage
- profile-owned related-role discovery with evidence explanations and explicit user approval
- unified Profile / Resume workflow for profile creation, résumé management, profile-owned role, location, workplace, schedule, compensation, and travel selections, and occupation-neutral scoring ownership for newly created managed profiles
- tracker workflow states, follow-up dates, quick actions, archive/restore workflows, and guarded deletion
- scan lifecycle records, progress state, cross-process locking, stage-specific failures, and bounded pagination
- non-blocking GUI scans with app-wide progress and completion notifications
- an installation-wide employer/source catalog with independent profile assignments and per-profile enable/disable control
- user-owned runtime paths and non-destructive configuration/database bootstrap
- versioned SQLite migrations, foreign-key enforcement, atomic tracker/history moves, and backup-before-migration protection
- clean wheel installation and installed-package rendering tests

Application History is a permanent app-native feature. It is stored in SQLite and remains available for review, filtering, scan-time matching, prior-decision context, reporting, and tracker/history restoration workflows.

Managed profiles have separate Active Applications and Application History records. Switching profiles changes which records the GUI, scans, reports, and CLI use. Existing tracker and history records are assigned to the active managed profile during the protected database migration. A profile that owns tracker or history records cannot be deleted, preventing accidental loss of job-search data.

## Quick start for development

```powershell
cd C:\dev\job-radar
.\.venv\Scripts\Activate.ps1
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m job_radar.web_app --settings config\settings.yaml
```

Open:

```text
http://127.0.0.1:5000/
```

The installed console entry point is also available:

```powershell
job-radar-web --settings config\settings.yaml
```

## Common commands

Validate configuration:

```powershell
.\.venv\Scripts\python.exe -m job_radar validate --config config\target-companies.yaml --settings config\settings.yaml --scoring config\scoring.yaml
```

Run a scan:

```powershell
.\.venv\Scripts\python.exe -m job_radar scan --config config\target-companies.yaml --settings config\settings.yaml --report reports\target-scan.html --email-preview reports\target-email-preview.txt
```

Summarize application history:

```powershell
.\.venv\Scripts\python.exe -m job_radar history summary --settings config\settings.yaml
```

List active applications:

```powershell
.\.venv\Scripts\python.exe -m job_radar tracker list --settings config\settings.yaml
```

Create a new user-owned junior workspace:

```powershell
.\.venv\Scripts\python.exe -m job_radar bootstrap-user-data
```

This creates safe starter settings, an empty company list, and occupation-neutral scoring structure. It does not copy a profile, résumé, database, credentials, another user's occupational scoring rules, or the repository's live company list.

Existing settings, companies, scoring rules, profiles, or a database can be brought over only by supplying the matching optional `--source-*` argument.

junior uses bootstrapped user settings by default when they are present. The established `JOB_RADAR_DATA_DIR` compatibility name remains unchanged so existing installations and user data continue to work.

## Validation

Run Ruff:

```powershell
.\.venv\Scripts\python.exe -m ruff check job_radar tests
```

Run the full test suite:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests
```

Run the complete automated Windows release gate:

```powershell
.\scripts\validate_release.ps1
```

This runs the full suite and lint checks, builds a fresh unsigned installer,
and validates install, repair/upgrade, uninstall, and synthetic user-data
preservation without using the active Junior workspace.

Validate the finished Windows and Linux packages in clean environments:

```powershell
.\scripts\validate_clean_packages.ps1
```

This launches the installed Windows executable with isolated empty data and
runs the Linux archive in a Python-free Debian container.

Packaging validation is covered by `tests/test_packaging.py`, including clean-wheel installation, installed desktop-launcher startup, and installed web rendering outside the source tree.

Build the unsigned Windows desktop bundle:

```powershell
.\scripts\build_windows.ps1
```

The reproducible PyInstaller recipe creates
`artifacts\windows\Junior\Junior.exe` plus its required private runtime files.
It does not contain profiles, resumes, databases, credentials, reports, logs,
or other user-owned data.

Build the unsigned per-user Windows installer:

```powershell
.\scripts\build_windows_installer.ps1
```

The resulting `artifacts\installer\Junior-Setup-0.1.0.exe` installs under the
current user's local application area, adds a Start Menu shortcut, and offers
an optional desktop shortcut. Uninstall removes application files but preserves
Junior's separate user-data directory. Code signing and public release
distribution remain later release work.

Validate install, repair/upgrade, and uninstall preservation using only
disposable data:

```powershell
.\scripts\validate_windows_upgrade.ps1
```

The validation hashes representative user-owned files before and after each
operation. It fails if any file is added, removed, or changed.

Build the Linux x86-64 tarball from Windows using Docker Desktop's Linux
engine:

```powershell
.\scripts\build_linux_tarball.ps1
```

The resulting `artifacts\linux\Junior-linux-x86_64.tar.gz` contains Junior's
portable application bundle plus `launch-junior.sh`, `install.sh`, and
`uninstall.sh`. The Docker context explicitly excludes configuration,
databases, profiles, résumés, reports, logs, and other user-owned data.

On Linux, extract the archive and run:

```sh
sh Junior/install.sh
~/.local/bin/junior
```

The launcher checks for Linux and a WebKit GTK desktop library before opening
Junior. Uninstall with `sh Junior/uninstall.sh` from the extracted archive, or
the installed copy, to remove application files while preserving user data.

### Container/server mode

Run Junior with its included Compose definition:

```powershell
docker compose -f packaging\container\compose.yaml up --build
```

The example exposes Junior only at `http://127.0.0.1:8000`, runs as a non-root
user, and stores all durable state in the `junior-data` volume mounted at
`/var/lib/junior`. Recreating or upgrading the application container preserves
that volume. Startup creates only missing safe defaults and then uses Junior's
normal database migrations and shared Flask/service code.

`GET /health` returns only the application name, readiness state, and installed
version. Container logs go to standard output/error while Junior-owned logs
remain under the mounted data root. Credential values must be injected through
approved environment-variable references or an external secrets mechanism;
never bake them into an image or Compose file.

Junior's web interface does not currently provide user authentication. Keep
container mode bound to localhost or behind a separately secured private
network boundary. Do not publish port 8000 directly to the public internet.

### Kubernetes mode

The operator-ready baseline is under `packaging/kubernetes`. Apply it with
Kustomize only after replacing `junior:0.1.0` with the exact immutable image
tag or digest being deployed:

```powershell
kubectl apply -k packaging\kubernetes -n junior
```

The baseline uses one non-root application replica, a persistent volume,
private ClusterIP networking, privacy-safe health probes, and suspended scan
and backup CronJobs. The single replica and `Recreate` upgrade strategy are
deliberate: Junior uses SQLite and must not have multiple application pods
writing to the same database. Create secret values outside source control and
enable each CronJob only after reviewing its schedule.

Scheduled backups retain the 14 newest scheduler-created bundles on the Junior
volume and never prune manual or pre-change safety backups. Because those
bundles share the same persistent volume, the cluster operator must also copy
backups to independent protected storage. A backup on a lost volume is not
disaster recovery.

Junior has no built-in web authentication. Keep the Service private or place
it behind an authenticated ingress on a trusted network; never expose it
directly to the public internet. Preserve and independently back up the
persistent volume during upgrades.

### Fictional demo workspace

Documentation, demonstrations, and release checks must never use a real
profile, resume, employer list, application, or job-search database. From a
development checkout, create a separate fictional workspace at a new path:

```powershell
.\.venv\Scripts\python.exe scripts\create_demo_workspace.py C:\temp\junior-demo
```

The command refuses any destination that already exists. It does not inspect
or copy the normal Junior user-data directory. The generated workspace contains
the fictional Jordan Rivera profile, fictional employers, a short fictional
resume, sample scan records, active applications, and application history.

Run Junior against only that workspace:

```powershell
cd C:\temp\junior-demo
C:\dev\job-radar\.venv\Scripts\python.exe -m job_radar.web_app --settings C:\temp\junior-demo\config\settings.yaml
```

Use a different empty destination for each validation run. Delete only the
disposable destination after confirming it is the generated fictional
workspace.

![Junior fictional profile overview](docs/images/junior-demo-profile.png)

![Junior fictional company workspace](docs/images/junior-demo-companies.png)

![Junior fictional active applications](docs/images/junior-demo-tracker.png)

The desktop launcher holds one operating-system lock per Junior user-data workspace. Launching Junior again reads the first process's local-only address, waits for it to become ready when necessary, and opens that interface instead of starting another server against the same database. A crash releases the operating-system lock; the small lock file itself is not treated as proof that Junior is running.

Desktop-launched sessions show **Exit Junior** in Settings. The action requests a clean local-server shutdown and confirms that the window can be closed. If a GUI scan is active, Junior keeps the process and instance lock alive until the scan worker finishes its protected database and report writes. Browser/server mode does not present a process-exit control it cannot safely own.

The desktop launcher now uses pywebview to place the same local Flask interface inside a normal native window. It does not create a second UI. Windows, Linux, and macOS must share the same pages, controls, layouts, validation, typography, and workflows; only genuinely native window chrome, dialogs, notifications, and keyboard conventions may differ. Use `job-radar-desktop --browser` when deliberate browser-based local use is preferred, or `--no-browser` for an externally managed local server. PySide6/QWebEngineView remains the documented fallback if cross-platform testing proves system webview rendering cannot satisfy that shared-interface requirement.

The shared page shell supports keyboard users with a visible-on-focus skip link, strong focus indicators on interactive controls, and a programmatically identified current navigation page. It also provides a mobile/zoom viewport, narrow-window wrapping, forced-color control borders, and screen-reader captions for application data tables. Profile occupation and location suggestions expose their expanded state and work with Enter, Escape, arrow keys, Tab, or a pointer. Automated checks require every visible form control to have a programmatic label and protect WCAG AA contrast for shared text, links, statuses, and actions.

## Configuration and private data

Safe starter files included in the install package:

- `job_radar/bootstrap_defaults/settings.yaml`
- `job_radar/bootstrap_defaults/scoring.yaml`
- `job_radar/bootstrap_defaults/target-companies.yaml`

Development and live-validation configuration remains under `config/` and is not used as the installed application's automatic starting data.

Runtime databases, reports, logs, private settings, resumes, profiles, and credentials must remain outside source control.

Managed profiles and uploaded resumes are stored inside junior's user-data area. Uploaded resume files receive stable app-owned names, so renaming or moving the original file does not break the active profile. Existing YAML profiles remain supported when no managed profile is selected; junior does not automatically migrate or replace them.

A controlled migration service can prepare an existing YAML profile for managed storage, but migration is not automatic or exposed as a normal GUI action yet. It creates a private recovery bundle containing the source profile, resume files, and a consistent SQLite backup before creating or selecting the managed profile. Real user-data migration requires a separate backup-and-rehearsal step and explicit approval.

The Profile / Resume page is a read-only home for selecting profiles and reviewing the active profile, résumé insights, and a plain-English summary of what junior is intended to find during targeted company scans. A compact profile selector supports switching, editing, creating, and guarded permanent deletion. junior supports up to five profiles; deleting one also removes its Junior-managed résumé and requires the same typed `DELETE` confirmation used for application deletion. Dedicated create and edit pages keep data entry separate from the summary; Cancel and Back return without saving, and only an explicit Create profile, Save changes, or Save résumé action writes the corresponding change. When no profile exists, the summary page directs the user to create the first one. This workflow does not run a search and is not a broad job-board filter. It stores normalized occupation identities, structured U.S. locations and commute radii, job levels, employment types, schedule, workplace arrangements, minimum compensation, travel percentage, and optional work exclusions in SQLite. Exclusions describe roles or responsibilities the user does not want; duplicate lines are normalized and the existing profile evidence boundary evaluates them without assuming that similar-sounding titles mean the same work. Selected locations use approximate straight-line distance to define acceptable hybrid and on-site commutes. Truly remote jobs ignore commuting distance, while an employer's remote residency restriction must match a location where the user lives or genuinely plans to move. Newly created managed profiles own an occupation-neutral scoring configuration instead of inheriting another user's role, skill, location, or exclusion assumptions. The saved practical preferences do not yet generate the complete scoring and recommendation policy; that integration remains in progress. The former `/preferences` address redirects to Profile / Resume for compatibility. Occupation suggestions use the O*NET 30.3 Database under CC BY 4.0; location suggestions and radius coverage use the U.S. Census Bureau 2025 Gazetteer Files, with display prioritization from the Census Bureau Vintage 2025 Population Estimates. junior includes only the reference fields needed by this workflow and has modified their packaging and presentation.

The active managed profile also has a Related Roles workspace. Junior can suggest adjacent titles from packaged O*NET occupation descriptions when the profile's résumé contains supporting work evidence, or from job descriptions previously observed during that profile's own scans. Similar wording alone is not enough. Suggestions tied to an observed employer retain that company context because one title can describe different disciplines at different companies. Every suggestion shows a plain-language explanation and the matched evidence terms. The user must choose **Relevant**, **Not relevant**, or **Different discipline**; only Relevant mappings join the existing target-role boundaries used by company recommendations. No internal score is shown, no suggestion is approved automatically, and the feature does not alter the established job-scoring formula. Junior stores the suggestion, short displayed evidence terms, and feedback in the profile-owned database; it does not store another raw copy of the résumé.

Each profile owns its own company search list. The Companies workspace shows only the active profile's employers and labels each one Scanning or Paused according to that profile's assignment. Existing upgrades complete their pending one-time YAML company import during application startup, before Profile, Companies, or Recommendations can show an empty profile-owned workspace. A user can add a company using its ordinary name or public careers URL. Junior first checks exact catalog names, aliases, normalized careers URLs, and known source identifiers. Exact existing matches require the user to choose the employer. For a small set of confidently recognizable public career sites, Junior shows the detected provider and company identity and requires explicit confirmation before creating or assigning anything. The confirmation request is rechecked on the server instead of trusting hidden technical settings from the page. Ambiguous names require the user to choose an exact match, and uncertain or unsupported sites create a safe administrator-review request instead of guessing. Detection is local and does not contact the submitted website. The Companies workspace shows only that profile's review state as Setup pending, Ready to add, or Unsupported. The new profile assignment starts as Scanning. Employers that are already assigned, unavailable, or missing required administrator setup cannot be added. The normal-user view otherwise keeps source slugs, collector configuration, notes, internal identifiers, and raw collector failures hidden. A user can pause, resume, or remove an assigned company without changing the shared employer definition or another profile's choice. Removal requires typing `REMOVE`, stops future scans only for the active profile, and preserves collected jobs, applications, history, reports, and other historical records. The Profile / Resume summary shows the same company count and links to the workspace. When no managed profile is active, the Companies page directs the user to create or select one and does not display legacy YAML configuration. Released CLI/server YAML scan compatibility remains available.

Junior does not present its local Employer Catalog as a comprehensive recommendation or employer-discovery system. Users choose the employers they want to monitor. The Companies workflow is designed to make that addition easy: enter an ordinary company name or public careers-page URL, review Junior's locally detected match or supported career platform, confirm it, and begin scanning. Junior does not invent employer names, silently add companies, broadly crawl the public web, or claim to know the full market for a profession or region. Existing recommendation metadata and Administration services remain available for compatibility and technical maintenance, but they are not part of the normal-user company workflow.

## Settings and Administration boundary

Settings remains the normal-user home for safe personal and product preferences. Its About page shows the installed version, release channel, user-data location, database and profile schema versions, and safe support guidance without exposing profile contents or credentials. A manual update check reads only the latest stable release from Junior's official GitHub project and reports the result; it never downloads or installs software, runs migrations, or changes user data. Email setup stores credentials through the operating system rather than ordinary settings or SQLite. Scan schedule setup stores an enabled state, local start time, selected weekdays, and email-delivery choice; it shows the calculated next run and safe status from the most recent scheduled scan. On Windows, the same page manages Junior's single `\Junior Scheduled Scan` Task Scheduler entry with normal user permissions and no stored Windows password. On Linux, it atomically manages only the marked `junior-scan.service` and `junior-scan.timer` files in the current user's systemd directory and refuses to overwrite similarly named files it does not own. Both platforms start the same `job-radar-scheduled` entry point and shared scan service. The Linux user timer can also run under a dedicated server service account with that account's explicit Junior data root; full logged-out service installation guidance remains part of the later Linux operations milestone. Administration is a separate, session-scoped safety boundary for installation-wide and technical controls. Unlocking Administration requires typing `ADMIN`; this is an explicit confirmation, not a password or protection from someone who already controls the local computer. Administration unlock state is limited to the current browser session and Junior process, and restarting Junior invalidates it. The Flask session signing key is generated locally under the user-owned database runtime directory. It is never committed or stored in YAML or SQLite; deleting it invalidates existing browser sessions.

| Classification | Controls |
|---|---|
| Normal Settings | Email setup, report retention, scan preferences, ordinary interface preferences, scheduling preferences, and safe user-facing defaults |
| Administration | Employer Catalog and collector configuration, runtime paths, database operations, backup and restore, legacy import and migration, raw diagnostics, support bundles, and installation-wide defaults affecting every profile |
| Undecided / future | The final placement of support links, bounded diagnostic summaries, and recovery guidance will be decided when those workflows become editable |

The Settings page keeps runtime paths read-only while providing normal-user controls for email, scheduling, retention, and safe diagnostics. Its Diagnostics page summarizes application configuration, the latest scan, company sources, and email delivery with green, yellow, red, or neutral status cards. Problems are categorized as configuration, collector, network, email, or unexpected application failures and include a plain-language next step. The same page lists only recognized sanitized Junior logs, limits each view to the newest 200,000 bytes, provides a bounded copyable troubleshooting summary, and can open the resolved Junior data directory through the operating system. It is not a general file browser: nested paths, arbitrary logs, editing, deletion, and unrestricted downloads are rejected. Raw exceptions, credentials, profile contents, and résumé contents are neither stored as scan diagnostics nor displayed. Administration includes the global Employer Catalog, where an unlocked administrator can create and edit structured employer-source settings, run bounded local validation, test the real collector connection without importing jobs, and enable, disable, or retire an employer. A connection test records the last attempt, last success, last problem, returned-job count, and a safe troubleshooting category. It never stores raw collector or network error text, and editing source settings clears stale connection health. The employer detail page can assign an available, validated employer to any managed profile or remove one profile's assignment without affecting another profile or deleting collected history. Permanent deletion requires typing `DELETE` and is permitted only when no profile assignment or collected job references the employer; otherwise the administrator must disable or retire it. The Employer Review Queue lets unresolved profile submissions be matched to an existing employer, used to prefill a new employer, assigned after availability checks, or closed as unsupported, rejected, or duplicate. Recommendation Administration provides employer/profile diagnostics, global employer recommendation metadata and eligibility, profile-specific feedback inspection and guarded reset, and explicitly bounded rebuilds for one profile, one employer, or every profile. Recommendation maintenance has a sanitized audit and does not silently override profile feedback. Review decisions have a sanitized audit trail. New and edited employers must validate before they can be globally enabled. Disabling or retiring preserves profile assignments and collected history; an unavailable employer is omitted from scans until it is enabled again. Packaged company defaults are empty for new installations. Existing legacy definitions import only once into the active profile, never replace a user-edited database employer with the same stable ID, and remain separate from later user-owned catalog changes. Other Administration categories remain planned.

Every state-changing web form and background action uses a session-bound CSRF token. Junior rejects missing, invalid, or stale tokens before route business logic runs, so the attempted change is not written. Normal forms receive a plain-language recovery page; background requests receive a bounded JSON error. Refreshing the page creates or loads the current token and allows the user to review and resubmit. GET routes remain read-only.

A successful scan writes fixed-name outputs in the user-owned `reports` directory. The latest HTML report, structured snapshot, and email preview keep stable filenames. Settings can retain only the latest run, the latest plus the previous run, or a chosen total from 1 through 50. Before a successful scan replaces the current files, Junior copies and verifies the prior complete set in its marked `reports/archive` directory; the Reports page lists retained HTML reports and email previews. The same Settings page limits recognized dated Junior logs while preserving the active startup log and unrelated files. Reduced limits are enforced on the next successful scan.

Scans started from the GUI run in the background. The rest of junior remains available while a scan is running, and every page monitors the same durable scan status. An app-wide notification reports completion, completion with source warnings, or failure and links to the appropriate results or details.

SMTP passwords must not be stored in YAML, SQLite, logs, reports, previews, bootstrap files, packages, or source control. Junior can store desktop credentials in the operating system's credential manager through the packaged `keyring` adapter; settings retain only the non-secret `smtp_credential_key` reference. The established `smtp_password_env` environment-variable reference remains supported for existing installations, servers, containers, and automated deployments. If the operating system has no usable secure credential backend, Junior reports that credential storage is unavailable and does not fall back to a plain-text file.

Settings includes an Email Setup page with Gmail, Outlook, and Custom SMTP choices, username and password entry, sender and recipient delivery details, and a clear credential-storage status. Gmail and Outlook use their standard SMTP server, port, and transport-security defaults; provider policy may require an app password or separately enabled SMTP access. Saving validates a complete replacement settings file before atomically activating it, preserves unrelated and newer settings keys, and writes a newly entered password only to the operating-system credential manager. **Test Connection** connects, negotiates TLS when configured, and authenticates without sending a message, launching a scan, or producing a normal report. A session-scoped status card shows the tested provider, result, time, credential-storage method, and a short reason. Ordinary results are limited to Connected, Not configured, Authentication failed, Server unreachable, or TLS negotiation failed; the browser session contains no password or raw SMTP failure.

## Database upgrade recovery

Before changing an existing database structure, junior creates a backup in the `backups` directory beside the active database. The established default Windows location remains `%LOCALAPPDATA%\JobRadar\data\backups`. Backup filenames identify the database and migration range, for example `job_radar.sqlite3.pre-migration-v1-v3-<timestamp>.bak`.

If junior reports an upgrade failure, close junior and do not delete, rename, replace, or repeatedly reopen the active database or its backups. Preserve the complete `data` directory and contact Clayton Graves at `claytonmgraves@outlook.com`. Include the displayed technical details and diagnostic-log location, but do not send the database, résumé, profile, passwords, access tokens, or other credentials unless an approved secure support process is provided.

Unlocked Administration provides a **Backup and recovery** screen. A restorable `.jrbackup` bundle contains a consistent SQLite copy plus Junior-owned settings, company/scoring configuration, managed profile and résumé files, reports, and sanitized logs. Junior validates the manifest, file paths, sizes, checksums, and database before restoring. It creates a separate pre-restore safety backup first and tells the user to restart after success. Credentials remain in Windows Credential Manager or their configured environment variable and are never included. The same screen can download a readable JSON database export; that export is for review and portability and cannot be used as a restore bundle.

Junior also creates safety backups automatically immediately before an eligible permanent profile or company deletion. Profile deletion preserves the complete workspace because the profile and managed résumé span SQLite and files; company deletion preserves a verified SQLite copy because the employer catalog is database-owned. Invalid confirmations and in-use records are rejected before a backup or deletion occurs. Existing schema upgrades continue to create their established pre-migration backups.

## Documentation

- [User Guide](docs/USER_GUIDE.md)
- [Development Guide](docs/DEVELOPMENT.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Security and Privacy](docs/SECURITY.md)
- [Roadmap](docs/ROADMAP.md)
- [Release Checklist](docs/RELEASE_CHECKLIST.md)
- [Changelog](CHANGELOG.md)

## Product boundaries

junior is designed to remain:

- local-first and user-controlled
- based on configured companies rather than broad crawling
- transparent in scoring and recommendations
- safe for manual review
- independent of automatic applications or recruiter outreach
- usable through one shared service layer across CLI, browser, packaged, and service modes

The long-term target is a configurable cross-platform application that a non-developer can install, launch, configure, and operate without editing source files by hand.
