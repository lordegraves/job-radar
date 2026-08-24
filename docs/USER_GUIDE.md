# junior User Guide

This guide describes the current local application and its supported Windows,
macOS, and Linux packaging paths.

Junior is licensed under the GNU General Public License version 3.0 only
(`GPL-3.0-only`). Every supported distribution includes the complete terms in
its `LICENSE` file. Third-party components and reference data retain their own
licenses.

## Windows installation

Junior's Windows installer is a per-user installer. Close Junior, run the
trusted `Junior-Setup-0.2.0-RC5-build-1.exe` installer, and keep the default installation
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

## macOS installation

Open the verified
`Junior-0.2.0-RC6-build-1.25-macos-<arch>.dmg`, drag **Junior** to the
Applications shortcut, eject the installer, and open Junior from Applications
or Launchpad. The application bundle supplies Junior's normal Dock and Finder
icon. A normal user does not need Python, Terminal, a virtual environment, a
localhost address, or repository access.

Junior stores profiles, résumés, settings, databases, reports, logs, backups,
and runtime files separately under:

```text
~/Library/Application Support/JobRadar
```

Replacing `Junior.app` during an update replaces application files only and
does not remove that user-data directory. Create and verify a Junior backup
before testing an update. After replacement, launch Junior and verify the
active profile, companies, Tracker, History, and latest Reports before
scanning.

Local field-test builds are ad-hoc signed. Public downloads require a verified
checksum, an approved Developer ID signature, and Apple notarization before
they can provide the normal downloaded-app trust experience. Do not bypass a
macOS security warning for an artifact whose origin and checksum are unknown.
Uninstalling the application means closing Junior and moving `Junior.app` from
Applications to Trash. That does not delete Junior's separate user data.

Junior uses local port 5050 on macOS because AirPlay Receiver commonly uses
port 5000. Users do not need to know or enter this address.

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
4. Opens Job Fit. Exact résumé-backed suggestions begin in Needs Review and
   remain inactive until the user classifies and saves them. At least one
   Strong Match or Needs Review item is required to finish setup.
5. Adds at least one employer the user wants Junior to monitor.
6. Shows a plain-language review of the profile, résumé, preferences,
   locations, employers, data location, and expected scan behavior.
7. Tests that the minimum profile information and at least one selected
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

Advanced users may deliberately run `junior-desktop --browser` to use the
same local interface in the default browser. Developers and externally managed
processes may use `junior-desktop --no-browser`. These are not required for
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

The Scan page keeps the normal workflow prominent. Advanced command and path
information remains available under **Show technical scan details** when it is
needed for troubleshooting.

A scan:

1. loads settings, company sources, scoring configuration, profile, and resume
2. acquires the cross-process scan lock
3. creates a durable scan-run record
4. collects and normalizes postings
5. scores jobs and applies recommendation policy
6. loads tracker and application-history context
7. stores postings and structured results
8. writes the HTML report, structured snapshot, and email preview

## Review Jobs

Needs Review separates unanswered questions from confirmed rejection reasons.
If Junior cannot prove that a job conflicts with the profile, the job remains
reviewable. Résumé evidence, Job Fit signals, and description completeness
determine its rank; weak or missing evidence is not an omission reason. The
queue is ranked into four collapsible groups:

A clearly unrelated title can still be omitted when Junior's profile-owned
title check records the exact reason. For example, an Accountant posting does
not become uncertain merely because Junior avoided downloading its full
description for an infrastructure profile.

- **Likely matches — confirm details:** strong résumé evidence with one or more
  unresolved qualifications or practical facts.
- **Plausible matches:** relevant work with important questions that need the
  user's judgment.
- **Low-confidence matches:** enough relevance to ask the user, but little
  qualification evidence Junior can verify.
- **Incomplete postings:** the collected description lacks enough detail for a
  reliable comparison.

Each ranked group is organized by company. Company groups and ranked groups
start collapsed so the page remains readable. Each ranked group has its own
pagination, so expanding a group always shows that group's current jobs.
Navigating a group keeps it open and does not move the other groups. Compact
review, visible-job bulk selection, notes, Save for later, Pass, Open job
posting, and application tracking continue to work within these groups. Several unverified
qualifications never become a rejection merely because there are several of
them. A hard rejection requires an auditable affirmative reason, such as an
explicit profile conflict, proven practical incompatibility, prior user
decision, or clearly unrelated occupation.
9. records completion or stage-specific failure

The first scan after installing Build 1.6 creates an incremental cache of
complete public source records, including jobs that are not actionable. Later
Workday and Eightfold scans reuse a fresh complete description when the public
listing identity, title, location, and source path are unchanged. New, changed,
missing-cache, and stale records still retrieve full details. A failed or
incomplete company collection never replaces that company's last valid cache
or marks its previously observed jobs absent.

The Scan page shows a live `HH:MM:SS` clock, the current company and recruiting
platform, and the active collection step. Eightfold description retrieval is
limited to five minutes per employer and stops after three consecutive detail
failures. Junior still retains valid listings, reuses previously verified
descriptions, and treats jobs without enough description text as incomplete
weak matches instead of guessing. The final duration is retained on Scan and
Latest Scan Details. Privacy-safe diagnostics record the time spent on each
company, local evaluation, report generation, and the number of source details
reused without storing descriptions or profile contents.

After completion, the Scan page summarizes the run without requiring a report
download: duration, companies completed, jobs collected, top matches,
potential top matches, jobs needing review, jobs omitted as not actionable,
new/previously seen/changed jobs, and company-source warnings.

Occasional company or network errors may be temporary. The interface preserves error details and does not imply that one collector failure invalidates the entire scan.

## Diagnostics

Open **Settings > Diagnostics** for a plain-language health summary of:

- application configuration
- the latest scan
- company job sources
- email delivery

Each card shows its current state, problem category, summary, and next step. Categories distinguish configuration, collector, network, email, and unexpected application problems. Junior stores safe scan summaries rather than raw exception text, and the page does not display credentials, profile contents, or résumé contents.

The page also lists up to 20 recognized sanitized Junior logs. Opening one shows only the newest 200,000 bytes so an unexpectedly large file cannot overwhelm the browser. Arbitrary filenames and nested paths are rejected. **Copy details** copies version, schema, data-location, and health state without copying log text or private profile information. **Open Data Directory** opens the workspace that owns the active settings; it does not expose arbitrary server paths through the browser.

Open **Companies > Company Source Health** when one company needs attention,
when sources have not been tested, or when selected companies should be
rescanned without replacing the latest full-scan report. This workspace keeps
the latest full-scan result separate from the latest connection test and shows
the safe explanation for each result directly. Common explanations distinguish
an unreachable source, denied public request, missing address, temporary
request limit, recruiting-service problem, and a collector that could not
interpret the returned job list.

The recognized sanitized logs use plain-language names and descriptions.
Download saves one of these text files through the operating system's normal
download workflow. Arbitrary filenames and nested paths remain rejected.

## Reports

The Reports page opens the latest successful scan outputs.

Current scan artifacts are:

- HTML scan report — the primary user-facing report
- plain-text email preview — the message that can be reviewed before delivery
- plain-text evaluation audit — one bounded record for every evaluated job,
  explaining why it was surfaced or omitted
- structured JSON snapshot — internal structured data used by the application
- compressed raw-scan ZIP — a downloadable plain-text record of every public
  posting collected in that run

The evaluation audit records public job identity, classification, role and
résumé fit, recognized gaps, and bounded decision reasons. It excludes job
descriptions, profile contents, résumé contents, credentials, and raw
exceptions, so it can be shared for troubleshooting without exposing those
private contents.

The normal HTML and email reports summarize the jobs worth presenting and do
not create thousands of full cards for unrelated or omitted jobs. The raw ZIP
is not displayed inside Junior. Download and open it only when a complete raw
scan record is needed for troubleshooting or offline review.

New installations retain the latest 10 successful report runs. Existing
installations keep their previously saved choice. In **Settings > Report and
log retention**, choose:

- latest only
- latest plus the previous run
- a chosen total from 1 through 50

When history is enabled, Junior copies and verifies the previous complete report set before replacing the latest files. Older HTML reports, email previews, evaluation audits, and raw-scan ZIPs appear under **Retained report history** on the Reports page with direct Download controls. Raw ZIPs are compressed, but installations scanning many employers can still use meaningful disk space; lower the retained-run count when long history is unnecessary. Lower limits take effect during the next successful scan. Junior removes only marked report archives and recognized dated Junior logs; active logs and unrelated files remain untouched.

## Active Applications

Active Applications is the source of truth for live application tracking.

Tracker records belong to the active managed profile. Switching profiles shows that profile's applications only. Two profiles may independently track the same job without changing each other's status, dates, or notes.

Typical actions include:

- add a manual application
- search, sort, and filter records
- update status, outcome, and dates
- record follow-up dates and notes
- use workflow-aware quick actions
- select several applications and move them to History with one terminal
  outcome; the entire selection succeeds or nothing changes
- move terminal applications to Application History
- delete a record through explicit confirmation

Junior assigns internal app-owned IDs automatically. An application created
from a scan keeps the scan's existing ID, while a manually entered application
receives a new Junior-managed ID when it is saved. Normal users never need to
enter, create, or maintain this value. Posting URLs remain source evidence, not
primary identity.

RC5 structured result cards no longer display the internal value. The
underlying compatibility ID remains managed by Junior and is preserved when a
user chooses **I applied — track application**.

RC5 structured scan-result pages now provide **Save for later**, **Pass /
don't show again**, and **I applied — track application**. A saved job can later
be moved into Active Applications with **I applied — track application**, or
moved into the Reviewed Jobs view with **Pass** so the exact posting is omitted
from future reports. The Saved and Reviewed Jobs page also lets you reverse a
bookmark or pass so the posting may appear in a later scan. Active
Applications and Application History will remain limited to jobs the user
actually applied for. Saved Jobs and Reviewed Jobs will preserve profile-owned
job decisions without becoming a second application tracker. The user bookmark
remains separate from Junior's recommendation label **Needs your review**.

Review Needed uses the full 20-job card view by default. **Compact review**
shows up to 50 collapsed summaries per page so company, title, and location can
be checked quickly. Expand any summary to use the same Save, Pass, Apply,
Notes, and evidence controls available in the full view. **Select all on this
page** never selects unseen jobs on another page. Previous and Next navigation
appears above and below the jobs. **Back to top** moves only within the current
page and does not reload it, change pages, or clear selections.

Scan results use **Review Needed** whenever Junior cannot confirm a practical
requirement such as workplace arrangement, job type, schedule, or
compensation. Here, **job type** means full-time, part-time, contract,
temporary, seasonal, or internship; workplace arrangement separately means
remote, hybrid, on-site, or flex. This does not mean the role is a poor fit. Every
full review card shows strengths supported by the résumé and possible résumé
gaps before the practical recommendation. **Top Match** remains
reserved for roles that have both strong role evidence and enough confirmed
practical information to support applying.

On **Saved and Reviewed Jobs**, a saved job's notes, reason, and **Pass — don't
show again** action belong to one decision form. Passing a saved job stores the
current reason and notes, moves it to Reviewed and passed, and prevents that
exact posting from returning in later scans. If a decision cannot be saved,
Junior keeps the job in place and shows an understandable error instead of
silently appearing to do nothing.

The RC5 **Pass / don't show again** control is durable and profile-specific.
Stronger extraction of explicit location and short-contract details remains an
RC5 acceptance requirement. Until that work is complete, treat Review Needed
as a request for human confirmation rather than proof that Junior extracted
every practical detail in the posting.

RC5 also requires broader company-source acceptance testing. A company should
be saved only after Junior identifies a working public source and receives
credible jobs from the selected collector. Failed candidate URLs and probe
results must be discarded rather than left as unfinished company data.
Complete public UKG Pro Recruiting/UltiPro job-board URLs are recognized
directly and use Junior's shipped UKG collector without optional external
lookup.

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

An effective profile describes both the jobs you want and the work you can demonstrate:

1. Choose a focused group of related target roles rather than every role you might consider.
2. Select every practical limit you would accept, including job level, employment type, workplace arrangement, location, schedule, travel, and compensation. Director, Head, Vice President, and similar leadership roles are usually classified as Executive.
3. Upload a current résumé so Junior can compare the posting with evidence from your work history.
4. Open **Job Fit** after saving. Put clearly demonstrated skills and responsibilities in **Strong Match**, related work that needs closer review in **Needs Review**, and unwanted work in **Avoid**.

Uploading a résumé extracts text for comparison; it does not choose strengths or Job Fit preferences automatically. Junior may place bounded exact phrases from clearly labeled résumé skills or competency sections into Needs Review as suggestions. These suggestions do not affect scans until you review and save them. Every optional blank profile field means **Any** and does not filter jobs. Removing target roles, levels, employment types, workplace arrangements, locations, or Job Fit signals therefore broadens the search. Selected filters remain enforced, and missing facts needed to evaluate a selected filter go to Needs Review. Junior warns on Profile and Scan when saved choices conflict.

When a target title contains Director, Head, Vice President, or VP and Executive is not selected, the profile form displays a warning and an **Include Executive** action. Keep Executive excluded only when you intentionally do not want Junior to consider that level.

When a managed profile is selected, future scans use its candidate-fit signals, compensation values, and managed resume. If no managed profile is selected, the existing YAML profile remains in use. junior does not automatically convert, overwrite, or remove an existing YAML profile.

Supported resume formats:

- PDF
- DOCX
- Markdown
- plain text

Resume replacement is written to the active user-data area. For a managed profile, junior copies the upload under `resumes/<profile-id>/` using an app-owned filename such as `resume.pdf`; moving or renaming the original uploaded file cannot break the profile. To use a revised resume, upload it again through the Profile / Resume page. Private resumes and profiles must not be committed to the repository.

Managed profiles store target roles, locations, work arrangements, employment types, schedules, on-call and security-clearance choices, compensation minimums, travel tolerance, and related job-fit preferences. Current scans use the implemented workplace, location, employment, schedule, on-call, clearance, compensation, and practical-eligibility rules. A clearly stated requirement for an existing active clearance follows the profile's choice; unclear clearance language goes to Needs Review. Recommendation actions and risks are occupation-neutral: junior does not globally favor or penalize a particular industry, employer, job title, skill, or region. Profile-owned fit terms, resume evidence and gaps, exclusions, compensation, location eligibility, and that profile's application history supply the relevant context. Missing résumé evidence is an unanswered question, not proof that the qualification is absent. Only an affirmative conflict with the profile or a clearly unrelated occupation can create a hard professional-fit rejection. Some broader scoring configuration still uses the established scoring boundary, so the application continues to explain recommendations in plain language rather than treating every saved field as an independent score boost.

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

Junior does not recommend where you should work or claim that its local catalog represents the complete employer market. You choose the employers to monitor. Select **Add company** and enter an existing catalog name or paste any official company URL. A homepage, careers page, department page, search page, or public job posting is acceptable. When Junior recognizes an existing employer or validates a supported career platform, it asks you to confirm before adding it. Junior never silently adds or scans a company.

To add a company, enter its ordinary name or any official company URL. A name searches the existing local catalog only; new installations include the 50-employer starter catalog described below. For a URL, Junior follows a bounded set of relevant public pages and redirects, inspects recruiting-platform links and metadata, derives compatible collector settings, and validates the source using normal pagination. Junior saves the source only after a collector returns actual public job postings. Rejected candidates and failed probe details do not create company or review records. If automatic setup fails, the problem is a Junior compatibility limitation rather than a request for the user to locate an ATS URL. Use the displayed support contact and include the public company URL. Never send passwords, access tokens, résumés, or other private data with a support request.

Walmart is intentionally profile-aware. Its public catalog contains roughly
45,000 Walmart, Sam's Club, and Vizio openings, most unrelated to an individual
professional search. Junior asks Walmart for the active profile's declared
target roles and preferred locations, exhausts that scoped result set, and
downloads complete descriptions for those jobs. Changing profiles changes the
scope used by the next scan; the preferences are never stored in Walmart's
shared company definition.

USAJOBS requires API access before Junior can test or scan a configured federal
organization. Request a key from the USAJOBS Developer site, then open
**Settings → USAJOBS API access** and enter the registered contact email and
authorization key. Junior stores the key in the operating-system credential
manager and never writes it to settings, SQLite, logs, diagnostics, backups, or
support packages. The email is a required USAJOBS request header and is stored
as ordinary non-secret configuration. Leave the key field blank when saving
later changes to retain the current key. Use **Test USAJOBS access** to verify
the saved values, or **Remove saved USAJOBS access** to delete the key. Advanced
CLI and server deployments may continue using the documented environment
variables instead.

An unfinished setup attempt created by an earlier Junior build appears in **Company setup requests**. **Retry setup** reruns current discovery, while **Remove attempt** hides the legacy attempt after confirmation without deleting a working company, job, application, or history record. New failed submissions do not add rows to this queue. After a company is added successfully, Junior returns to **Your Companies** with a temporary, dismissible confirmation instead of leaving the old URL in the form. Open a company to see whether its job source is connected, which recruiting platform it uses, when it was last checked, and how many jobs the latest check returned. **Test job source** safely reruns that public read without importing jobs or requiring Administration access. Background test completion refreshes the saved source-health summary automatically. Open the same page to correct a spelling mistake in the shared name; this changes the installation-wide display name but preserves the working collector configuration and existing history. **Remove from this profile** removes only the active profile's scanning assignment. Permanent global employer deletion remains protected in Administration.

The global **Collector Catalog** is available from Settings and Administration
on every installation and describes the job platforms Junior knows how to
scan. The separate **Employer Catalog** starts with 50 release-tested employers.
Junior adds no starter employer to a profile automatically: choose only the
ones you want scanned. Upgrades append a missing starter catalog version without
overwriting an existing employer, changing profile assignments, or restoring a
starter employer that was later removed.

During first-run setup, select **Open and test the starter catalog**. Use
**Test every source not tested yet** to check the complete untested group; this
action requires no row checkboxes. Use **Choose specific sources to test** only
when you intend to check or recheck particular employers. After testing, turn
on **Scanning** only for employers you want in the active profile, then return
to setup. Catalog-wide testing is recommended, while the final setup validation
separately requires at least one enabled company source to connect successfully.

The RC6 Build 1.25 starter set is: Affirm, Airbnb, Anduril Industries, Asana,
Block, Brex, Canonical, Carta, Carvana, Chime, Cloudflare, Coinbase, Coursera,
Datadog, Discord, DoorDash, Dropbox, Duolingo, Elastic, Figma, Ford Motor
Company, GitLab, Google, Grafana Labs, Gusto, HelloFresh, HubSpot, Instacart,
Khan Academy, Lucid Motors, Lyft, Microsoft, MongoDB, Mozilla, Okta, Oscar
Health, Peloton, Pinterest, Reddit, Relativity Space, Robinhood, Samsara, SoFi,
Stripe, Sweetgreen, Toast, Vox Media, Walmart, Waymo, and Wikimedia Foundation.
This is also the field-test list. Testers should add only relevant employers,
run **Test job source**, and verify that a normal scan returns current jobs with
complete descriptions and more than the first results page where applicable.

### Company-discovery field-test matrix

Testers should paste the entry URL shown below, not search for a more technical
ATS address. Record the detected platform, job count, elapsed time, and whether
Junior added the company. Public sites change, so a changed result is useful
test evidence rather than something to work around.

| Company | Entry URL | Expected result for this build |
|---|---|---|
| NetApp | `https://careers.netapp.com/` | TalentBrew; add succeeds; completeness baseline was 302 jobs on 2026-08-10 |
| Lockheed Martin | `https://www.lockheedmartin.com/en-us/careers/index.html` | TalentBrew; add succeeds when public jobs are available |
| Microsoft | `https://careers.microsoft.com/` | Eightfold; add succeeds when public jobs are available |
| Google | `https://www.google.com/about/careers/applications/jobs/results/` | Google Careers; add succeeds when public jobs are available |
| Nintendo | `https://careers.nintendo.com/` | Standard public page; add succeeds when public jobs are available |
| Walmart | `https://careers.walmart.com/` | Walmart Careers; add succeeds when the active profile has target roles; live synthetic scope returned 14 of 14 jobs with complete descriptions on 2026-08-10 |
| Nutanix | `https://careers.nutanix.com/en/jobs/` | Standard public page currently returns actual jobs; record the count because full pagination remains a field-test target |

For each successful case, open the company afterward and run **Test job
source**. A healthy result must identify the same platform and return actual
jobs. For a failure, create a diagnostic package and report the entry URL and
time of the attempt. Do not include passwords, tokens, résumés, or private
profile data.

Technical job-source settings do not appear in the normal Companies workspace. They are managed in the session-guarded Administration area after typing `ADMIN`. This confirmation is a safety boundary, not a password.

Administration's Employer Catalog supports global employer creation and editing through labeled fields, local configuration validation, and global enable, disable, and retire controls. The Employer Review Queue lets an administrator match a submitted company to an existing employer, begin a prefilled new-employer setup, optionally assign an available employer to the requesting profile, or close the request as unsupported, rejected, or duplicate. Review history excludes raw collector errors and private profile contents. Validation does not run a scan or contact the employer. A new or edited employer must pass validation before it can be enabled. Disabling or retiring an employer keeps profile assignments and collected history, but prevents scans from using it. An employer with profile assignments or collected jobs cannot be permanently deleted.

## Settings

Settings surfaces active runtime paths, the current latest-scan-only report policy, scan defaults, profile paths, and email readiness without displaying secrets. Runtime paths remain read-only, while Email Setup and Scan Schedule have dedicated editing pages.

**Settings > About Junior** includes a Credits section recognizing people who
help improve Junior through beta testing and product feedback.

## Scan scheduling

Open **Settings**, then **Set up scan scheduling**. Choose whether scheduling is on, the local start time, at least one weekday, and whether a completed scheduled scan should email its report. Save the schedule before applying it to the operating system.

On Windows, **Apply schedule to Windows** creates or updates only `\Junior Scheduled Scan`. Junior can inspect, disable, or remove that task from the same page. Junior's window does not need to remain open, and the task can run while the computer is locked. The Windows user must remain signed in, and the computer must be awake and powered on at the scheduled time. The task runs with normal privileges and stores no Windows password.

On Linux, the equivalent controls manage `junior-scan.service` and `junior-scan.timer` in the current user's systemd directory. Junior marks both files, refuses to overwrite unmarked files with the same names, writes updates atomically, and restores the prior files if systemd rejects an update. A dedicated Linux server account can use the same user timer and `junior-scheduled --user-data-root <path>` entry point; it does not have a separate scan implementation. The released `job-radar-scheduled` command remains a compatibility alias.

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

The troubleshooting package exports the selected profile and public company catalog at the moment the user clicks Download. It identifies that profile's newest completed scan by database run ID, includes only a report set whose audit header proves the same run ID, and prioritizes that run's scan and evaluation logs. It never substitutes another profile's newer scan or an older fixed-name report. The package also includes Junior's unified
`junior-application.log` and its separate scan diagnostics. Application events
share a safe operation ID so support can reconstruct company setup, user
actions, database work, email, updates, decisions, and failures without form
values or private content. Company setup includes the public hostname,
discovery stages, final result, elapsed time, and whether Junior actually
created or assigned the company. The application log rotates at 2 MB and keeps
one previous file. Dated scan and evaluation traces follow the configured
retention count and a 100 MB total ceiling.

Common situations:

- **Junior says it is already running:** use the existing window. If no window
  is visible, wait briefly and launch Junior once more; do not start multiple
  copies against the same database.
- **The window does not open:** close any stale Junior process through Task
  Manager, then try once more. If Windows reports a web-rendering component
  problem, repair or install Microsoft Edge WebView2 Runtime.
- **A company source fails:** open **Companies > Company Source Health** and
  compare the latest scan result with the separate connection test. Test that
  source again or run a targeted scan. Other healthy companies can still
  complete.
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
