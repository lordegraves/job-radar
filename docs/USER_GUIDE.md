# junior User Guide

This guide describes the current local application. It does not assume that installer or all first-run onboarding work is complete.

## First-time setup

Create a user-owned junior workspace:

```powershell
python -m job_radar bootstrap-user-data
```

This creates:

- safe starter settings
- an empty company list
- starter scoring rules
- empty data, profile, report, and log directories

It does not copy a personal profile, résumé, database, credentials, or live company list.

Existing junior data can be brought over deliberately with the optional `--source-settings`, `--source-companies`, `--source-scoring`, `--source-profiles`, and `--source-database` arguments. Existing destination files are always preserved.

After launch, a genuinely empty installation opens the guided setup welcome page. The current guided path creates a profile, accepts optional roles or responsibilities to avoid, accepts or skips a résumé, opens profile-owned company selection, and shows a final review. Junior records the completed step in its SQLite database. If the application closes before setup is finished, reopening it returns to that step without deleting or recreating the partial profile. The review shows the profile, résumé status, saved job preferences, locations, exclusions, companies, local data location, and how targeted scans will behave. Setup is marked complete only when **Finish setup** is selected on the review page.

## Launching the application

The current installed desktop-style entry point is:

```powershell
job-radar-desktop
```

It creates the user-owned workspace when needed, starts junior locally, waits for the interface to become ready, and opens the default browser. If junior is already running on the selected local address, the launcher reuses that instance instead of starting another server.

This is a browser-opening launcher, not the final native desktop window or Windows installer. Those remain future productization work.

From an activated development environment:

```powershell
python -m job_radar.web_app --settings config\settings.yaml
```

Open `http://127.0.0.1:5000/`.

When bootstrapped user settings exist, junior can use them by default:

```powershell
python -m job_radar.web_app
```

## Database upgrade recovery

junior creates a backup before changing an existing database structure. The established default Windows workspace remains `%LOCALAPPDATA%\JobRadar`, and migration backups are stored in its `data\backups` directory.

If an upgrade fails:

1. Close junior.
2. Do not delete, rename, replace, or repeatedly reopen the active database or any backup.
3. Preserve the complete junior `data` directory.
4. Contact Clayton Graves at `claytonmgraves@outlook.com` with the displayed technical details and diagnostic-log location.

Do not send your database, résumé, profile, passwords, access tokens, or other credentials unless an approved secure support process is provided. junior does not currently provide a self-service restore screen, so do not manually replace the active database with a backup.

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

## Reports

The Reports page opens the latest successful scan outputs.

Current scan artifacts are:

- HTML scan report — the primary user-facing report
- plain-text email preview — the message that can be reviewed before delivery
- structured JSON snapshot — internal structured data used by the application

Each successful scan replaces the previous fixed-name outputs. The Reports page does not expose arbitrary files from the reports directory. Configurable report history and retention are planned but are not implemented yet.

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

Managed profiles store target roles, locations, work arrangements, employment types, schedules, compensation minimums, travel tolerance, and related job-fit preferences. Current scans use the implemented workplace, location, employment, schedule, on-call, compensation, and practical-eligibility rules. Recommendation actions and risks are occupation-neutral: junior does not globally favor or penalize a particular industry, employer, job title, skill, or region. Profile-owned fit terms, resume evidence and gaps, exclusions, compensation, location eligibility, and that profile's application history supply the relevant context. Some broader scoring configuration still uses the established scoring boundary, so the application continues to explain recommendations in plain language rather than treating every saved field as an independent score boost.

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

Select **View recommendations** to see companies connected to the active profile's desired roles. Being scan-ready is not enough: Junior shows a catalog company only when its role metadata or recent jobs match the profile's target work. Unrelated employers are omitted. Junior explains each suggestion in ordinary language and does not show its internal ranking number. When Junior has recent jobs seen during that profile's own scans, it can explain how many matched the target work, how many had strong title matches, whether remote jobs matched the profile, whether workplace or location conflicts appeared, whether at least two jobs provide a reliable below-minimum pay pattern, and how recently the newest match appeared. It evaluates only a bounded 90-day window and ignores older scans whose profile ownership is unknown. Applications and rejections do not automatically alter company recommendations. **Add to profile** begins scanning that company for the active profile. **Maybe later** hides it for 30 days, **Dismiss** hides it for 90 days, and **Not relevant** hides it persistently. These choices belong only to the active profile. Recommendations do not search the public web.

The recommendations page can also show employers found in recent job data for the active profile but not yet present in Junior's catalog. This section is limited to 50 fresh employers from the last 90 days, requires jobs matching the profile's desired roles, and explains why each one is worth reviewing. A profile without desired roles receives no speculative suggestions. **Review company** checks for an existing catalog match and otherwise sends the employer to the Administration review queue. Junior does not silently create, trust, or scan an outside company, and this workflow does not perform broad web crawling.

To add a company, enter its ordinary name or public careers URL. Junior looks for an exact known company first. If more than one company may match, Junior asks you to choose instead of merging them. Junior can safely configure a limited set of clearly recognizable career sites; other names and sites are sent for administrator review. This check does not visit the submitted website. A company awaiting review is not scanned. Its requesting profile may see Setup pending, Ready to add, or Unsupported; another profile does not see that request.

Technical job-source settings do not appear in the normal Companies workspace. They are managed in the session-guarded Administration area after typing `ADMIN`. This confirmation is a safety boundary, not a password.

Administration's Employer Catalog supports global employer creation and editing through labeled fields, local configuration validation, and global enable, disable, and retire controls. The Employer Review Queue lets an administrator match a submitted company to an existing employer, begin a prefilled new-employer setup, optionally assign an available employer to the requesting profile, or close the request as unsupported, rejected, or duplicate. Review history excludes raw collector errors and private profile contents. Validation does not run a scan or contact the employer. A new or edited employer must pass validation before it can be enabled. Disabling or retiring an employer keeps profile assignments and collected history, but prevents scans from using it. An employer with profile assignments or collected jobs cannot be permanently deleted.

## Settings

The current Settings page is read-only.

It surfaces active runtime paths, the current latest-scan-only report policy, scan defaults, profile paths, and email readiness without displaying secrets.

## Email

Email delivery requires explicit configuration and the CLI `--send-email` option. The GUI Scan page currently creates the email preview but does not send email.

To run a scan and deliberately request configured SMTP delivery:

```powershell
python -m job_radar scan --config config\target-companies.yaml --settings config\settings.yaml --report reports\target-scan.html --email-preview reports\target-email-preview.txt --send-email
```

The application can still launch and perform unrelated work when email is disabled or a credential is unavailable.

SMTP password values must be supplied through a supported credential source. The current implementation supports environment-variable references and must never store the password value in YAML, SQLite, logs, reports, previews, or source control.

## CLI fallbacks

Summarize history:

```powershell
python -m job_radar history summary --settings config\settings.yaml
```

List applications:

```powershell
python -m job_radar tracker list --settings config\settings.yaml
```

List records needing action:

```powershell
python -m job_radar tracker list --needs-action --settings config\settings.yaml
```

The CLI remains useful for validation, testing, automation, and fallback operation. The GUI is the normal daily interface.
