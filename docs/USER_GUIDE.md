# junior User Guide

This guide describes the current local application and its supported Windows
and Linux packaging paths.

## Windows installation

Junior's Windows installer is a per-user installer. Close Junior, run the
trusted `Junior-Setup-0.2.0.exe` installer, and keep the default installation
location unless you have a specific reason to change it. Administrator access
is not required.

The installer:

- installs Junior under `%LOCALAPPDATA%\Programs\Junior`
- adds **Junior** to the Start Menu
- optionally creates a desktop shortcut
- keeps user data separately under `%LOCALAPPDATA%\JobRadar`

The current development installer is unsigned, so Windows may show an
unrecognized-app warning. Confirm that the installer came from the trusted
Junior release or build process before continuing. Public code-signed release
downloads remain future release work.

Launch Junior from the Start Menu or optional desktop shortcut. A normal user
does not need Python, PowerShell, a virtual environment, a localhost address,
or repository access.

## Linux installation

The Linux archive targets x86-64 desktop distributions. Extract
`Junior-linux-x86_64.tar.gz`, open a terminal in the extracted directory, and
run:

```sh
sh Junior/install.sh
~/.local/bin/junior
```

The install does not require root access. It copies application files to
`${XDG_DATA_HOME:-$HOME/.local/share}/junior/application` and creates the
launcher `$HOME/.local/bin/junior`. If that directory is not on `PATH`, use the
full launcher path shown above.

Junior checks for a WebKit GTK desktop library and explains when it is missing.
Install the `webkit2gtk` package provided by the Linux distribution, then
launch Junior again. Package names differ by distribution.

Profiles, résumés, settings, databases, reports, logs, backups, schedules, and
credential references remain separate from application files. The current
packaged application keeps its complete workspace under
`${XDG_DATA_HOME:-$HOME/.local/share}/job-radar`.

To upgrade the standalone archive:

1. Create a verified Junior backup and copy it to separate protected storage.
2. Close Junior.
3. Extract the newer archive into a new temporary directory.
4. Run that archive's `Junior/install.sh`. It replaces application files only.
5. Launch Junior and verify the active profile, companies, Tracker, History,
   and latest Reports before scanning.

To remove the application while keeping all user data:

```sh
sh Junior/uninstall.sh
```

The uninstall script removes only the launcher and application directory that
Junior installed. It preserves both Linux user-data roots and does not remove
operating-system credential-manager entries.

## Linux unattended scans

Open **Settings > Scan schedule**, save the desired local time and weekdays,
then choose **Apply schedule to Linux**. Junior creates only these marked
systemd user units:

```text
${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/junior-scan.service
${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/junior-scan.timer
```

The units call Junior's shared scheduled-scan entry point; they do not contain
separate scanning or scoring rules. Junior refuses to overwrite unmarked files
with those names and restores the prior marked files if systemd rejects an
update.

Useful operator checks are:

```sh
systemctl --user status junior-scan.timer
systemctl --user list-timers junior-scan.timer
journalctl --user-unit junior-scan.service
```

The user service manager must be available. On many desktops it runs while the
user is signed in. A server operator who needs scans after logout may enable
systemd user lingering for a dedicated Junior account according to the
distribution's security policy. Do not run Junior's desktop workspace
simultaneously under root and a normal user.

**Disable Linux schedule** stops future runs but keeps Junior's marked unit
files. **Remove Linux schedule** stops the timer and deletes only those marked
files. Neither action deletes profiles, companies, jobs, reports, or backups.

## Container/server operation

Container mode is for an operator who deliberately manages Docker. From the
repository or release operations directory, build and start it in the
background:

```powershell
docker compose -f packaging\container\compose.yaml up --build --detach
```

Open `http://127.0.0.1:8000`. The supplied configuration stores Junior data in
a named persistent volume, so replacing the container does not replace the
profiles, résumés, settings, companies, database, reports, or logs.

Common operations:

```powershell
docker compose -f packaging\container\compose.yaml ps
docker compose -f packaging\container\compose.yaml logs --follow junior
docker compose -f packaging\container\compose.yaml stop
docker compose -f packaging\container\compose.yaml up --build --detach
```

The container runs as UID/GID 10001, uses Gunicorn rather than Flask's
development server, and reports readiness at `/health`. Startup creates only
missing safe defaults under `/var/lib/junior`; it does not replace an existing
workspace.

Before an image upgrade, create a verified Junior backup and export a separate
protected copy from the `junior-data` volume. Rebuild or pull the exact trusted
image, then run `docker compose ... up --detach` to recreate the application
while retaining the named volume. Confirm `/health`, profiles, companies,
Tracker, and History afterward.

Junior does not currently ask for a username or password before displaying the
web interface. Keep this mode on the same computer or behind a separately
secured private network. Do not expose it directly to the internet.

Supply credentials through the deployment environment or another external
secret mechanism only when settings contain the matching non-secret reference.
Never put a password in the Dockerfile, Compose file, image, or version
control.

`docker compose down` removes containers and the private network but normally
preserves the named volume. Do not add `--volumes` unless a separately verified
backup exists and permanent deletion of the entire container workspace is
intentional.

## Kubernetes operation

Kubernetes mode is for an experienced cluster operator. The supplied resources
in `packaging/kubernetes` run one non-root Junior application pod, keep all
user-owned data on a persistent volume, expose only a private ClusterIP
Service, and provide health checks.

Before applying the resources:

1. Build or obtain a trusted Junior image and replace `junior:0.2.0` with an
   immutable release tag or image digest.
2. Select a storage class and size appropriate for the installation.
3. Create SMTP Secret data outside source control if email is enabled. The
   committed `junior-secrets` manifest intentionally contains no value.
4. Review the private-network and independent-backup plan.
5. Render the final resources with `kubectl kustomize packaging/kubernetes`
   and inspect them before applying.

Create a dedicated namespace, then apply the reviewed resources:

```powershell
kubectl create namespace junior
kubectl apply -k packaging\kubernetes -n junior
kubectl rollout status deployment/junior -n junior
kubectl get pod,pvc,service,cronjob -n junior
```

The Deployment uses one replica and `Recreate` upgrades because Junior's SQLite
database has one application writer. Do not scale it horizontally. The
ClusterIP Service is private, and readiness/liveness probes use the sanitized
`/health` response.

Scan and backup CronJobs are included but suspended by default. Review each
schedule, the active profile, company sources, email behavior, and cluster time
zone before setting `suspend: false` in maintained deployment configuration.
The jobs forbid overlap and retain bounded Kubernetes job history. Scheduled
Junior backups keep the 14 newest scheduler-created bundles without deleting
manual or pre-change safety backups.

Useful operator checks are:

```powershell
kubectl logs deployment/junior -n junior
kubectl get cronjob,job -n junior
kubectl describe pvc junior-data -n junior
```

Before an upgrade, create and independently copy a verified Junior backup,
take a storage-system snapshot when available, and confirm the PVC is healthy.
Update the maintained image tag or digest, apply the resources, and wait for
the rollout. The `Recreate` strategy stops the old application pod before the
new one opens the same SQLite database. If the new pod fails, preserve the PVC
and logs; do not delete or recreate the database.

Junior does not provide web login protection. Use an authenticated ingress on
a trusted private network if remote access is needed. Also copy backups to
protected storage outside Junior's persistent volume; in-volume backups cannot
recover a lost volume. Upgrades must preserve and independently back up that
volume.

Deleting the Deployment leaves the PVC unless the operator separately deletes
it. Deleting the namespace normally deletes the PVC and may permanently remove
all Junior data, depending on the storage class reclaim policy. Never delete
the namespace or PVC as a routine upgrade or repair action.

## First-time setup

A new Windows installation creates its user-owned workspace automatically and
opens guided setup. No command line is required.

The guided workflow:

1. Introduces Junior's local-first storage and targeted-company scan model.
2. Creates the first profile and records the work, job levels, employment
   types, schedule, on-call availability, security-clearance handling,
   workplace arrangements, locations, compensation floor,
   travel tolerance, and optional exclusions the user chooses.
3. Accepts a PDF, DOCX, Markdown, or plain-text résumé, or allows that step to
   be skipped and completed later.
4. Adds at least one employer the user wants Junior to monitor.
5. Shows a plain-language review of the profile, résumé, preferences,
   locations, employers, data location, and expected scan behavior.
6. Tests that the minimum profile information and at least one selected
   employer source are usable before enabling **Finish setup**.

Junior saves the current setup step. Closing the application during setup does
not erase completed work; reopening Junior returns to the saved step. The
validation check does not import, score, recommend, report, or email jobs.

For an established installation, Junior opens the existing workspace rather
than replacing it or restarting setup. Importing repository-era data is an
advanced migration operation and is never performed silently.

## Launching the application

The Start Menu or desktop shortcut creates the user-owned workspace when
needed, starts Junior locally, waits for the interface to become ready, and
opens it in a normal application window. If Junior is already running for that
workspace, the launcher reports the existing instance instead of starting
another server against the same data.

Launching Junior again does not start another copy against the same data, even if the second shortcut or command requests a different local port. The second launch waits for the first copy when it is still starting, then opens the first copy's interface. If Junior previously stopped unexpectedly, the operating system releases the instance lock automatically.

To close a desktop-launched session, open **Settings** and choose **Exit Junior**. The confirmation page means the local server received the shutdown request. You may close the window. If a scan is running, Junior finishes its protected writes before the process fully exits. This control is intentionally absent in browser/server mode, where another process owns the server lifecycle.

Advanced users may deliberately run `job-radar-desktop --browser` to use the
same local interface in the default browser. Developers and externally managed
processes may use `job-radar-desktop --no-browser`. These are not required for
normal Windows use.

From an activated development environment:

```powershell
.\.venv\Scripts\python.exe -m job_radar.web_app --settings config\settings.yaml
```

Open `http://127.0.0.1:5000/`.

When bootstrapped user settings exist, junior can use them by default:

```powershell
.\.venv\Scripts\python.exe -m job_radar.web_app
```

## Database upgrade recovery

junior creates a backup before changing an existing database structure. The established default Windows workspace remains `%LOCALAPPDATA%\JobRadar`, and migration backups are stored in its `data\backups` directory.

If an upgrade fails:

1. Close junior.
2. Do not delete, rename, replace, or repeatedly reopen the active database or any backup.
3. Preserve the complete junior `data` directory.
4. Contact Clayton Graves at `claytonmgraves@outlook.com` with the displayed technical details and diagnostic-log location.

Do not send your database, résumé, profile, passwords, access tokens, or other credentials unless an approved secure support process is provided.

Unlocked **Administration → Backup and recovery** can create a private, restorable `.jrbackup` file. It protects the database, profiles, résumés, settings, company/scoring configuration, reports, and sanitized logs. Passwords remain in Windows Credential Manager or their configured environment variable and are not copied. A readable JSON export is also available, but it is not a restore file.

To restore, choose a Junior `.jrbackup` file and type `RESTORE`. Junior validates the bundle and database, creates a separate safety backup of the current state, and only then replaces approved user data. Restart Junior after a successful restore. If validation fails, the current workspace is not changed.

Junior automatically creates a safety backup before it permanently deletes an eligible profile or employer. A refused deletion does not create a backup or change data. Database upgrades retain their separate pre-migration backups.

## Home

The Home page summarizes the latest scan and active application work.

It includes:

- latest scan status
- Top Matches, Review Needed, Tracked Applications, New Jobs, and Collector Errors
- active workflow counts
- follow-ups due
- applications needing date review
- stale or dormant records
- recently active applications

Dashboard cards link to focused views rather than duplicating entire reports.

## Scan

The Scan page runs the shared scan pipeline.

Starting a scan from this page returns control immediately. You may continue using other junior pages while the scan runs. A status indicator remains available throughout the interface, and junior displays an app-wide notification when the scan completes, completes with source warnings, or fails. The notification links to the latest results or scan details.

A scan:

1. loads settings, company sources, scoring configuration, profile, and resume
2. acquires the cross-process scan lock
3. creates a durable scan-run record
4. collects and normalizes postings
5. scores jobs and applies recommendation policy
6. loads tracker and application-history context
7. stores postings and structured results
8. writes the HTML report, structured snapshot, and email preview
9. records completion or stage-specific failure

Occasional company or network errors may be temporary. The interface preserves error details and does not imply that one collector failure invalidates the entire scan.

## Diagnostics

Open **Settings > Diagnostics** for a plain-language health summary of:

- application configuration
- the latest scan
- company job sources
- email delivery

Each card shows its current state, problem category, summary, and next step. Categories distinguish configuration, collector, network, email, and unexpected application problems. Junior stores safe scan summaries rather than raw exception text, and the page does not display credentials, profile contents, or résumé contents.

The page also lists up to 20 recognized sanitized Junior logs. Opening one shows only the newest 200,000 bytes so an unexpectedly large file cannot overwhelm the browser. Arbitrary filenames and nested paths are rejected. **Copy details** copies version, schema, data-location, and health state without copying log text or private profile information. **Open Data Directory** opens the workspace that owns the active settings; it does not expose arbitrary server paths through the browser.

## Reports

The Reports page opens the latest successful scan outputs.

Current scan artifacts are:

- HTML scan report — the primary user-facing report
- plain-text email preview — the message that can be reviewed before delivery
- structured JSON snapshot — internal structured data used by the application

The latest outputs keep the same fixed filenames. In **Settings > Report and log retention**, choose:

- latest only
- latest plus the previous run
- a chosen total from 1 through 50

When history is enabled, Junior copies and verifies the previous complete report set before replacing the latest files. Older HTML reports and email previews appear under **Retained report history** on the Reports page. Lower limits take effect during the next successful scan. Junior removes only marked report archives and recognized dated Junior logs; the active startup log and unrelated files remain untouched.

## Active Applications

Active Applications is the source of truth for live application tracking.

Tracker records belong to the active managed profile. Switching profiles shows that profile's applications only. Two profiles may independently track the same job without changing each other's status, dates, or notes.

Typical actions include:

- add a manual application
- search, sort, and filter records
- update status, outcome, and dates
- record follow-up dates and notes
- use workflow-aware quick actions
- move terminal applications to Application History
- delete a record through explicit confirmation

junior assigns app-owned IDs to manual records. Posting URLs remain source evidence, not primary identity.

## Application History

Application History is a permanent SQLite-backed part of junior.

History records also belong to the active managed profile and remain with that profile when moved to or restored from Active Applications. Scans use only the active profile's tracker and history context.

History contains terminal, passed, withdrawn, rejected, closed, and archived records. It supports:

- search, sorting, and filters
- record detail and editing
- prior-decision context during scans
- history summaries
- restoration to Active Applications
- preservation of company, role, URL, source/contact context, notes, and workflow dates

Tracker and History are mutually exclusive. A record should not exist in both at the same time.

## Profile / Resume

The Profile / Resume page shows candidate readiness and resume-derived fit information. It also allows you to create, edit, select, and safely delete managed profiles without editing YAML. A profile that owns Active Applications or Application History cannot be deleted because those job-search records must be preserved.

When a managed profile is selected, future scans use its candidate-fit signals, compensation values, and managed resume. If no managed profile is selected, the existing YAML profile remains in use. junior does not automatically convert, overwrite, or remove an existing YAML profile.

Supported resume formats:

- PDF
- DOCX
- Markdown
- plain text

Resume replacement is written to the active user-data area. For a managed profile, junior copies the upload under `resumes/<profile-id>/` using an app-owned filename such as `resume.pdf`; moving or renaming the original uploaded file cannot break the profile. To use a revised resume, upload it again through the Profile / Resume page. Private resumes and profiles must not be committed to the repository.

Managed profiles store target roles, locations, work arrangements, employment types, schedules, on-call and security-clearance choices, compensation minimums, travel tolerance, and related job-fit preferences. Current scans use the implemented workplace, location, employment, schedule, on-call, clearance, compensation, and practical-eligibility rules. A clearly stated requirement for an existing active clearance follows the profile's choice; unclear clearance language goes to Needs Review. Recommendation actions and risks are occupation-neutral: junior does not globally favor or penalize a particular industry, employer, job title, skill, or region. Profile-owned fit terms, resume evidence and gaps, exclusions, compensation, location eligibility, and that profile's application history supply the relevant context. Some broader scoring configuration still uses the established scoring boundary, so the application continues to explain recommendations in plain language rather than treating every saved field as an independent score boost.

### Related roles

Open **Profile / Resume**, then select **Review related-role suggestions** for the active managed profile. Select **Find related roles** to refresh the list from the résumé and profile-owned scan evidence currently available.

Junior does not use dictionary synonyms to decide that two roles are equivalent. A packaged suggestion must share concrete résumé evidence with an O*NET occupation description. A suggestion from a previously observed job must share concrete résumé and job-description evidence and retains the employer where that meaning was observed. Weak evidence produces no suggestion.

Each suggestion explains why it appeared and requires one decision:

- **Relevant** approves that mapping for the profile's existing target-role recommendation boundaries.
- **Not relevant** records that the role does not belong in this profile.
- **Different discipline** records that the title sounds related but represents different work in that context.

Viewing or refreshing suggestions never approves them. The feature does not change the established numerical scoring formula.

Existing YAML profiles are not migrated automatically. junior now has an internal backup-first migration service, but it is not yet a normal GUI action. Do not manually move, rename, delete, or rewrite your working profile, resume, or database in an attempt to migrate it. Migration of real data should occur only after a rehearsal on copies and an explicit backup confirmation.

## Companies

Employer organizations and source definitions are shared once per local junior installation, while each managed profile has its own company list. The normal Companies workspace shows the active profile's employers and whether each one is Scanning or Paused. You can pause, resume, or remove a company for that profile without changing another profile.

Junior does not recommend where you should work or claim that its local catalog represents the complete employer market. You choose the employers to monitor. Select **Add company**, enter an ordinary company name or public careers-page URL, and review the match Junior finds locally. When Junior recognizes an existing employer or a supported career platform, it asks you to confirm before adding it. Ambiguous or unsupported sources go to controlled review rather than being guessed. Junior never silently adds or scans a company.

To add a company, enter its ordinary name or public careers URL. Junior looks for an exact known company first. If more than one company may match, Junior asks you to choose instead of merging them. Junior can safely configure a limited set of clearly recognizable career sites; other names and sites are sent for administrator review. This check does not visit the submitted website. A company awaiting review is not scanned. Its requesting profile may see Setup pending, Ready to add, or Unsupported; another profile does not see that request.

Technical job-source settings do not appear in the normal Companies workspace. They are managed in the session-guarded Administration area after typing `ADMIN`. This confirmation is a safety boundary, not a password.

Administration's Employer Catalog supports global employer creation and editing through labeled fields, local configuration validation, and global enable, disable, and retire controls. The Employer Review Queue lets an administrator match a submitted company to an existing employer, begin a prefilled new-employer setup, optionally assign an available employer to the requesting profile, or close the request as unsupported, rejected, or duplicate. Review history excludes raw collector errors and private profile contents. Validation does not run a scan or contact the employer. A new or edited employer must pass validation before it can be enabled. Disabling or retiring an employer keeps profile assignments and collected history, but prevents scans from using it. An employer with profile assignments or collected jobs cannot be permanently deleted.

## Settings

Settings surfaces active runtime paths, the current latest-scan-only report policy, scan defaults, profile paths, and email readiness without displaying secrets. Runtime paths remain read-only, while Email Setup and Scan Schedule have dedicated editing pages.

## Scan scheduling

Open **Settings**, then **Set up scan scheduling**. Choose whether scheduling is on, the local start time, at least one weekday, and whether a completed scheduled scan should email its report. Save the schedule before applying it to the operating system.

On Windows, **Apply schedule to Windows** creates or updates only `\Junior Scheduled Scan`. Junior can inspect, disable, or remove that task from the same page. It runs with normal privileges while the Windows user is signed in and stores no Windows password.

On Linux, the equivalent controls manage `junior-scan.service` and `junior-scan.timer` in the current user's systemd directory. Junior marks both files, refuses to overwrite unmarked files with the same names, writes updates atomically, and restores the prior files if systemd rejects an update. A dedicated Linux server account can use the same user timer and `job-radar-scheduled --user-data-root <path>` entry point; it does not have a separate scan implementation.

Disabling an operating-system schedule leaves its definition available for later use. Removing it deletes only Junior's own task or marked unit files. Neither action deletes profiles, scan history, reports, companies, or application data.

## Email

Email delivery requires explicit configuration. Open **Settings**, then **Set up email delivery** to choose Gmail, Outlook, or Custom SMTP, store the credential through the operating system, save delivery details, and test the connection without sending a report. The GUI Scan page currently creates the email preview but does not send email; a saved schedule can request email delivery after its scan.

On Windows, a password entered through Email Setup is stored in Windows
Credential Manager. Junior's settings keep only a non-secret reference.
**Test Connection** reports Connected, Not configured, Authentication failed,
Server unreachable, or TLS negotiation failed without displaying raw SMTP
errors. Gmail or Outlook may require an app password or provider-side SMTP
permission.

To run a scan and deliberately request configured SMTP delivery:

```powershell
.\.venv\Scripts\python.exe -m job_radar scan --config config\target-companies.yaml --settings config\settings.yaml --report reports\target-scan.html --email-preview reports\target-email-preview.txt --send-email
```

The application can still launch and perform unrelated work when email is disabled or a credential is unavailable.

SMTP password values must be supplied through a supported credential source. The current implementation supports environment-variable references and must never store the password value in YAML, SQLite, logs, reports, previews, or source control.

## Backup and restore

Open **Settings**, choose **Unlock Administration**, type `ADMIN`, and open
**Backup and recovery**. The confirmation protects technical controls from
accidental use; it is not an account password.

- **Create and download backup** writes a verified private `.jrbackup` bundle
  inside Junior's data directory and downloads a portable copy through the
  application.
- **Create readable export** writes JSON for inspection or portability, but
  that JSON cannot be restored.
- **Restore** accepts a `.jrbackup` file only after the user types `RESTORE`.

A restore validates the archive and its database before changing active data.
Junior creates a separate safety backup of the current workspace first, then
replaces only recognized Junior-owned data. Restart Junior after a successful
restore. Credentials remain in Windows Credential Manager or the configured
environment and are not included in either backup or export.

Store an additional copy of important backups on a different protected disk or
backup service. A backup kept only on the same computer cannot recover a lost
or failed computer.

### Move development data into an installed copy

The repository is a development environment. A normal installed copy runs from
its installed application directory and owns data under
`%LOCALAPPDATA%\JobRadar`; it does not need the repository.

To move an existing development workspace into an installed copy:

1. In the development copy, open **Settings**, unlock **Administration**, then
   open **Backup and recovery**.
2. Choose **Create and download backup** and keep the downloaded `.jrbackup`
   file in protected storage.
3. Install and launch the standalone Junior release.
4. Before restoring, confirm the installed copy is using the expected data
   directory on **Settings > About Junior**.
5. In the installed copy, unlock **Administration**, open **Backup and
   recovery**, select the downloaded bundle, type `RESTORE`, and restore it.
6. Restart the installed copy. Confirm the active profile, résumé, companies,
   applications, history, settings, and reports before running a scan.

Restore validates the bundle before changing the installed workspace and first
creates a separate backup of the installed copy's prior state. It does not
modify or delete the source development workspace. Credentials are intentionally
not transferred; configure them again through the installed copy's secure
credential workflow.

## Windows upgrades

1. Create a Junior backup and copy it to separate protected storage.
2. Close Junior through **Settings > Exit Junior**.
3. Run the trusted newer installer. Installing over the existing per-user
   installation is the supported repair or upgrade path.
4. Launch Junior and allow its automatic, backup-protected data migrations to
   finish.
5. Confirm the active profile, companies, Tracker, History, Settings, and
   latest Reports before starting a new scan.

Installer repair and upgrade replace application files, not
`%LOCALAPPDATA%\JobRadar`. Never delete the database or profile as an upgrade
step. If startup or migration fails, stop and follow **Database upgrade
recovery** above instead of repeatedly reopening or manually replacing files.

## Windows uninstall

Close Junior, then use **Windows Settings > Apps > Installed apps > Junior >
Uninstall**.

Uninstall removes the application and its shortcuts. It deliberately preserves
profiles, résumés, settings, companies, application history, databases,
reports, logs, backups, schedules, and credential references under
`%LOCALAPPDATA%\JobRadar`. This allows a later reinstall to recover the same
workspace.

Junior does not currently provide a normal-user option to erase the complete
workspace. Do not manually remove it unless you have separately backed it up
and deliberately intend to permanently delete all Junior data. Windows
Credential Manager entries are a separate operating-system boundary and are
not exposed or recovered by the uninstaller.

## Troubleshooting on Windows

Start with **Settings > Diagnostics**. It reports safe application, scan,
company-source, and email health without exposing résumé or profile contents,
credentials, or raw exception text. **Open Data Directory** opens the active
workspace, and **Copy details** copies safe version and health information for
support.

Common situations:

- **Junior says it is already running:** use the existing window. If no window
  is visible, wait briefly and launch Junior once more; do not start multiple
  copies against the same database.
- **The window does not open:** close any stale Junior process through Task
  Manager, then try once more. If Windows reports a web-rendering component
  problem, repair or install Microsoft Edge WebView2 Runtime.
- **A company source fails:** open Companies or Diagnostics and review the
  plain-language source status. Other healthy companies can still complete.
- **A scheduled scan did not run:** confirm scheduling is enabled, at least one
  weekday is selected, and **Apply schedule to Windows** reports the
  `\Junior Scheduled Scan` task as installed. The current task runs only while
  that Windows user is signed in.
- **Email authentication fails:** verify the provider, username, app password,
  and provider SMTP policy, then use **Test Connection**. Do not paste a
  password into logs or support messages.
- **An upgrade fails:** close Junior, preserve `%LOCALAPPDATA%\JobRadar`, and
  follow **Database upgrade recovery**. Do not delete or hand-edit the
  database.

For an unexpected problem that these steps do not resolve, contact Clayton
Graves at `claytonmgraves@outlook.com` with the copied safe details and the
diagnostic-log location. Never include passwords, access tokens, or
credentials.

## CLI fallbacks

Summarize history:

```powershell
.\.venv\Scripts\python.exe -m job_radar history summary --settings config\settings.yaml
```

List applications:

```powershell
.\.venv\Scripts\python.exe -m job_radar tracker list --settings config\settings.yaml
```

List records needing action:

```powershell
.\.venv\Scripts\python.exe -m job_radar tracker list --needs-action --settings config\settings.yaml
```

The CLI remains useful for validation, testing, automation, and fallback operation. The GUI is the normal daily interface.
