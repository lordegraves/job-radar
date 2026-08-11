# junior

junior is a local-first job discovery, triage, reporting, and application-tracking tool.

It scans configured company career sites, normalizes and scores job postings, stores results in SQLite, and provides a local Flask interface for reviewing results, tracking active applications, and preserving application history.

junior does **not** apply to jobs automatically, contact employers, scrape LinkedIn, bypass authentication, or broadly crawl the internet.

## Status

- Current version: `0.2.0`
- Current field-test build: `RC6 Build 1.19`
- MVP completed and acceptance-tested: July 14, 2026
- Current development branch: `feature/productization-foundation`
- Python requirement: 3.11 or newer

RC6 Build 1.19 is a field-test build. It improves company setup by accepting
any official company page, discovering linked recruiting platforms through a
bounded layered process, validating actual jobs at normal result depth, and
eliminating dependence on an external company-name search. It also carries the
active profile's Strong fit capabilities into résumé comparison, while still
requiring matching evidence in the résumé and posting. Broad shared words or
tools do not make different professions equivalent, and Junior keeps sparse
postings at review level unless their title specifically matches configured
target work.

The Companies page now shows the complete shared catalog. Each row has a
sliding scan toggle for the active profile; turning it off keeps the company
visible so it can be turned back on later. A separate checkbox at the left of
each row selects sources for connection testing. During scans, hard eligibility
failures are discarded before résumé comparison, and the packaged local server
uses a separate process for the CPU-heavy scan and scoring pipeline, so
navigation, progress requests, and other pages remain responsive throughout
scoring. That worker runs below the desktop's operating-system priority and
reports bounded job-by-job progress during large evaluation sets. In an
isolated copy of an 11,140-job profile, this reduced scoring
from roughly 7 minutes 22 seconds to 1 minute 23 seconds without changing the
ten jobs surfaced for review.
Company health can be filtered to Healthy, Needs attention, or Not tested.
The table's selection checkbox applies only to visible rows, so a user can hide
working sources, select the remaining visible sources, and test that group.
Changing a source returns it to Not tested until verification succeeds. A newer
successful connection test clears an older scan warning from the current health
display without removing that historical warning from the scan audit. Valid
empty Greenhouse and iCIMS boards are reported as connected with no openings.
Because Walmart tests use the active profile's target roles and locations, a
reachable Walmart source with no matching jobs is reported as healthy with no
profile matches rather than as a broken or empty recruiting source.
Junior does not start a source-test batch while a scan is running, and an
unexpected background-test failure is identified as a Junior test problem
rather than being mislabeled as a failed employer source. When a background
test finishes, the Companies workspace reloads its saved health evidence so a
successful retest cannot remain visibly stale until Junior is reopened.

Each company detail page groups profile status, recruiting platform, connection
health, last check, returned-job count, and the public request URL into one Job
source workspace. Source-test results appear once. Public reference links stay
collapsed until needed, and an unlocked administrator can move directly from a
company to its global source editor to correct, validate, and retest the
collector without changing profile assignments or collected history.
When an employer moves to another recruiting platform, the administrator can
explicitly migrate the existing employer instead of deleting and recreating
it. Junior preserves the employer identity, profile assignments, collected
jobs, and application history, but disables that source until its replacement
configuration validates and passes a live connection test. The audit records
the platform change without copying source settings into diagnostic output.

The current development build is a functional local application with up to five independent managed profiles. Python wheel, source-package, reproducible Windows executable, unsigned per-user Windows installer, Linux archive, container, and Kubernetes baselines are implemented and validated. A genuinely empty installation now opens a guided first-run path through profile creation, résumé upload, profile-owned work exclusions, company selection, and a final review. The setup checkpoint is stored safely in SQLite, so closing junior during setup returns the user to the last completed step instead of starting over. The review shows the profile, résumé, preferences, locations, companies, user-data location, and scan behavior. Finish setup remains unavailable until Junior verifies minimum usable profile rules and confirms at least one selected company collector can connect. This validation imports, scores, recommends, reports, and emails no jobs, and it explains corrections in plain language. Publicly signed release downloads, remaining editable configuration, and broader release-candidate work are still in progress.

See [CHANGELOG.md](CHANGELOG.md) for released and unreleased changes.

### Product lifecycle

Junior is completing and stabilizing the current shared Python, Flask, and
pywebview product through version 1.0. That application will remain supported
as Junior 1.x while a future native desktop 2.0 is evaluated and built in
parallel. The native work is planned, not current functionality.

The 2.0 project will preserve Junior's shared scanning, scoring, profile,
company, tracker, history, report, diagnostics, scheduling, backup, and storage
services rather than creating different rules for a new interface. It will not
replace 1.x until workflow parity, safe data migration and rollback,
cross-platform behavior, performance, privacy, packaging, and field testing
are verified. See [the authoritative roadmap](docs/ROADMAP.md) and
[architecture documentation](docs/ARCHITECTURE.md) for the complete gates.

## Current capabilities

junior currently provides:

- configured-company scanning across multiple ATS and career-site formats
- first-class Google Careers collection with complete public descriptions,
  stable job identifiers, location data, and bounded parallel pagination
- profile-aware Walmart Careers collection that exhausts the public jobs
  matching the active profile's target roles and preferred locations, carries
  Walmart's server-side scope across pagination, and retrieves complete job
  descriptions without ingesting its roughly 45,000 unrelated openings
- GUI-managed USAJOBS API access: Settings stores the registered contact email
  as non-secret configuration and keeps the authorization key only in the
  operating-system credential manager; environment variables remain an
  advanced CLI/server fallback
- bounded multi-page TalentBrew collection so large career sites such as Ford
  do not stop after the first results page
- marker-based pagination for older generic HTML definitions backed by
  TalentBrew or SAP SuccessFactors, plus a 2,000-listing Workday ceiling
- bounded numbered-page collection for employer-owned public career sites,
  with company setup accepted only after Junior parses an actual public job
- complete Workday detail retrieval when an employer uses `jobs` as its
  Workday site name, including Red Hat's public recruiting source
- reliable Microsoft/Eightfold second-chance description retrieval using the
  platform's internal job identity while preserving stable incremental IDs
- Oracle Recruiting detail completion that preserves qualification-section
  meaning, recognizes compensation advertised `per annum`, and refreshes
  stale details after collector-parser improvements. When a complete posting
  states no required qualifications, Junior reports that gaps cannot be
  verified instead of claiming there are none or treating preferred items as
  mandatory.
- Profile-owned active applications and application history stored safely in SQLite
- profile-owned scoring, occupation-neutral recommendation policy, compensation checks, and resume/profile matching
- structured scan snapshots and HTML reports
- plain-text and HTML email previews with guarded SMTP delivery
- a local Flask GUI with a task-ordered Home, Profile / Resume, Companies,
  Scan, Review Jobs, Applications, Reports & Audit, Help, and Settings flow
- installed version, release-channel, schema, license, and manual verified
  update controls together at the top of Help & About
- GUI-managed profile creation, editing, selection, guarded deletion, and app-owned resume storage
- profile-owned related-role discovery with evidence explanations and explicit user approval
- unified Profile / Resume workflow for profile creation, résumé management, profile-owned role, location, workplace, schedule, compensation, and travel selections, and occupation-neutral scoring ownership for newly created managed profiles
- an on-demand Profile Configuration Report that users can preview and download
  before choosing whether to share a privacy-safe record of their active job
  preferences, skills, companies, and scoring settings for support
- profile configuration export/import that creates a separate inactive profile
  on the receiving installation and deliberately excludes every résumé file and
  résumé text, plus company-catalog export/import that only appends missing
  public collector definitions without overwriting the receiving catalog or
  changing any profile's company list
- tracker workflow states, follow-up dates, quick actions, bulk terminal updates,
  direct links back to available job postings, archive/restore workflows, and
  guarded deletion
- an unobtrusive Home dashboard option to share a Junior story or make an
  entirely voluntary Venmo donation that does not affect application behavior
- scan lifecycle records, progress state, cross-process locking, stage-specific failures, and bounded pagination
- non-blocking GUI scans with app-wide progress and completion notifications
- an installation-wide employer/source catalog with independent profile assignments and per-profile enable/disable control
- a 50-employer starter catalog on new and upgraded installations; it adds no
  profile assignments, never replaces user-managed definitions, and is applied
  only once so a company the user removes stays removed
- a global Collector Catalog shipped on every installation, automatic setup
  for supported ATS platforms including ADP, Recruitee, Workday, Oracle,
  Phenom, Eightfold, UKG Pro Recruiting/UltiPro, Google Careers, and a
  validated public-page fallback
- clickable Diagnostics details with safe latest-scan warnings, read-only
  company-source health, background connection testing, and selected-company
  scans that preserve the latest full-scan report
- user-owned runtime paths and non-destructive configuration/database bootstrap
- versioned SQLite migrations, foreign-key enforcement, atomic tracker/history moves, and backup-before-migration protection
- clean wheel installation and installed-package rendering tests

Application History is a permanent app-native feature. It is stored in SQLite and remains available for review, filtering, scan-time matching, prior-decision context, reporting, and tracker/history restoration workflows.

Managed profiles have separate Active Applications and Application History records. Switching profiles changes which records the GUI, scans, reports, and CLI use. Existing tracker and history records are assigned to the active managed profile during the protected database migration. A profile that owns tracker or history records cannot be deleted, preventing accidental loss of job-search data.

The completed RC5 work adds **Save for later**, **Pass / don't show again**, and
**I applied — track application** to every structured scan-result
classification. Saved and
passed jobs live in a separate profile-owned workspace; they do not become
applications or application-history records. Passing or saving hides that exact
source job from future reports for that profile and can be reversed later.
Individual review cards accept human-only notes of up to 300 characters and a
listed pass reason before Save or Pass. The Saved Jobs workspace keeps those
details editable, and multi-select actions remain all-or-nothing. Notes never
alter scoring. Eligibility retains
explicit work location, temporary or contract duration, employment type,
schedule, compensation, and work-authorization details when the posting
provides them. A concrete city, named office, or city/state suffix in a title is
treated as location-bound when the posting does not explicitly state that the
job is remote. Those jobs are compared with the profile's selected locations
instead of flooding Review Needed as unknown. Review cards show workplace
arrangement and location separately at a glance. Unresolved practical facts
remain in Review Needed rather than being guessed.

Company discovery combines known ATS patterns, redirects, page metadata and
links, structured data, custom domains, and compatible collector probes. A
company name searches the installation's existing catalog only. To add a new
company, the user may paste any official company URL: a homepage, careers page,
department page, search page, or public job posting. Junior follows a bounded
set of relevant public links, derives the recruiting-platform configuration,
uses the collector's normal pagination, and saves nothing until it validates
actual public jobs. If the official page blocks Junior from reading its links,
Junior also makes a bounded check for a matching public Ashby, Greenhouse, or
Lever board derived from the official company domain. A board is accepted only
when its normal collector returns actual jobs. An unsupported result saves no
partial company and does not
ask the user to hunt for a technical ATS URL.

USAJOBS is the exception because its public search API requires credentials
issued to the user. Request free API access from the USAJOBS Developer site,
then open **Settings → USAJOBS API access** and save the registered contact
email and authorization key. Use **Test USAJOBS access** before configuring a
federal organization. Junior keeps the key only in the operating-system
credential manager and stores only the non-secret email and credential
reference in settings. Normal desktop users do not need environment variables;
the existing environment-variable path remains available for advanced CLI and
server deployments.

Junior owns application identifiers. The internal Junior ID is hidden from
normal forms and reports. A scan-linked application reuses the identifier
assigned during collection, while an application entered manually from
LinkedIn or another outside source receives a new Junior-managed ID when the
user selects Save. Normal users never invent or maintain it.

RC5 now separates bookmarked jobs from applications. **Save for later** keeps a
profile-owned job for later review without claiming the user applied. **Pass**
moves a job into the profile's Reviewed Jobs view and prevents that exact
posting from returning in future reports. **I applied — track application**
opens the application workflow with Junior's scan-owned ID and source details.
The Applications workspace keeps separate Active applications and Application
history views for jobs the user actually applied for. Junior's recommendation
label **Needs your review** is
not the same as the user's saved state.
Home shows the active profile's combined Saved and Reviewed count, breaks it
down into saved and reviewed totals, and links directly to that workspace.
Scan completion now opens **Review Jobs**, an inbox containing only jobs from
the latest scan that still need the user's decision. Saving, applying, or
passing removes the job from this inbox, and later scans do not reset that
durable profile-owned action. Interactive Top Matches, Potential Top Matches,
Review Needed, and New Jobs groups remain organized by the scan's
classification. Top Matches retain confirmed practical eligibility. Potential Top
Matches already satisfy the profile's existing top-match score and strong-signal
rules but list the practical facts still awaiting confirmation; no threshold is
lowered and no internal score is shown. Each group loads at most 20 full job
cards per page. Review Needed also offers a compact view with at most 50
collapsed job summaries per page, page-only Select all, matching navigation at
the top and bottom, and a Back to top link that never changes pages or clears
selections. Numbered page links allow direct movement between distant pages.
Jobs on each page are grouped into collapsible company sections; a company
that spans pages shows both the number on the current page and its total in the
result group. Each company header clearly shows **Expand** or **Collapse**, and
the page also provides expand-all and collapse-all controls. Changing a company
section does not reload the page or clear selected jobs. Every compact summary
can expand to the same Save, Pass,
Apply, Notes, and evidence controls. Explicit workplace,
employment-type, and annual-pay wording in a description can fill a missing ATS
field. An omitted schedule does not imply a conflict, while an explicit night,
evening, weekend, or on-call requirement is still enforced.
Creating an application from Review Jobs returns to the same review group and
marks that scan job as applied. Home and Review Jobs counts show undecided work
remaining, rather than repeating jobs already saved, applied, or passed.
**Reports & Audit** is a separate page for the latest generated HTML report, email
preview, privacy-safe evaluation audit, compressed raw-scan download, and
retained report history. Full scans and selected-company scans keep separate
evaluation audits, so a targeted scan cannot replace the latest full-scan
audit. Downloaded audit filenames include the scan date and time. New
installations retain the latest 10 successful report runs by default. Existing
installations keep their current retention setting until the user changes it.

The Windows setup wizard uses Junior's dark visual design and logo. It labels
the workflow as an installation when Junior is absent, an update when another
build is installed, or a repair when the same build is run again. Updates and
repairs replace application files while preserving user settings and data.
A manually launched repair or update uses Windows' normal application-closing
support to ask Junior to exit before replacing locked files. It does not
force-close Junior; protected scan, database, and report work must finish
safely. Junior's built-in updater retains its separate bounded shutdown and
verified installer handoff.

### Version 1.0 accuracy release gates

Junior is considered accuracy-ready for Version 1.0 only when all approved
regression jobs produce their human-reviewed outcome, there is no confirmed
false Top Match, no confirmed eligible relevant job is silently omitted, and a
fresh risk-weighted sample reaches at least 95 percent agreement. The validation
corpus must have 100 percent correct location and remote-region handling, a
credible audit reason for every omission, visible identification of every
plausible incomplete posting, and complete normalized data or an explicit
source limitation from every collector. These are release gates, not aspirational
metrics; a failed gate blocks the release until the defect is understood and
repaired or the expected result is deliberately re-reviewed.

#### Current observed accuracy result

The latest non-LLM validation reached **100 percent agreement in a 50-job
risk-weighted review**. In plain language, every decision Junior made for the
50 jobs that were manually checked agreed with the expected decision. This is
an observed validation rate, not a claim that every job on the internet—or
even every job in that scan—was reviewed by a person. The Version 1.0 release
gate remains at least 95 percent agreement on a fresh sample so later changes
must continue to prove that they have not reintroduced an old problem.

The result came from installed RC6 Build 1.11 scan run 80 on August 4, 2026.
Junior evaluated 19,863 postings in 5 minutes and 52 seconds. The scan produced
six Potential Top Matches, three Needs Review jobs, no incomplete plausible
postings, and no collector errors. The 50-job review covered:

- all nine jobs Junior displayed, checking the recommendation, location and
  remote rules, major résumé gaps, and stated eligibility concerns;
- the 15 highest-scoring omitted jobs, because these are the hidden jobs most
  likely to expose a false rejection;
- 25 randomly selected omitted jobs, to check ordinary decisions across a
  wider mix of employers and occupations; and
- the Ford India-remote regression job as a named test case, confirming that
  `India; Remote` remains India-restricted after normalization and is omitted
  for a United States profile.

A reviewed decision counted as correct only when the final bucket was
defensible from the posting, profile, résumé, and tracked-job history, and an
omission had a credible audit reason. The review also checked that plausible
jobs were not hidden merely because their descriptions were unavailable.
Separately, the complete automated test suite passed **1,304 tests**, source
and test linting passed, and whitespace validation passed. These automated
checks protect known rules and collector behavior; the 50-job human-style
review measures whether those rules produced sensible real-world results.

### AI résumé tailoring

AI résumé tailoring is under development and is not currently available to
users. Settings provides no enablement, credential, provider, or connection-test
controls, and job reports provide no tailoring action. The retained experimental
OpenAI and local-model code has no role in scans, scoring, filtering,
recommendations, gaps, or omissions. Junior continues to collect, evaluate, and
sort every job using its tested deterministic rules.

Local résumé-tailoring is parked. It is not current product functionality,
is not offered for installation, and has no role in scans, scoring, filtering,
recommendations, gaps, or omissions. Developers can use
`scripts/benchmark_local_resume_tailoring.py` with an explicitly supplied
`llama.cpp` server executable, GGUF model, private benchmark-case file, and
output path. The benchmark starts a loopback-only local server, measures
startup and response time, checks that cited evidence appears in the supplied
résumé, and writes no result into Junior's database or reports.

The August 2026 feasibility run compared the official Q4 releases of Microsoft
Phi-3 Mini (2.39 GB, MIT) and Qwen3 4B (2.50 GB, Apache-2.0) on three synthetic
truthfulness cases. Both produced usable local response times, but Phi promoted
unsupported qualifications in two of three cases and Qwen promoted unsupported
qualifications in all three. Local AI is therefore **parked and not approved
for product integration**. The benchmark and its tests are retained so a later
reconsideration starts from measured evidence. A later trial must demonstrate
truthful advice and justify its additional download, memory, CPU, maintenance,
and licensing costs before this decision changes.

Temporary employer-source failures do not turn incomplete cache entries into
verified descriptions. Junior retries non-Eightfold sources once; Eightfold
retains its source-specific retry budget. If refresh still fails, Junior runs
recent cache entries through the same conservative detail planner, attempts a
strictly bounded recovery for plausible summaries, safely pre-screens clearly
unrelated titles, and visibly withholds anything that remains incomplete. One
source warning reports the complete and withheld counts. Decision accuracy and
source completeness therefore remain separate release measurements.

### RC6 collection and evaluation

RC6 Build 1.4 makes collection and job evaluation more complete and more
trustworthy:

- Every successful scan writes a downloadable plain-text evaluation audit
  explaining why each collected job was surfaced or omitted. It contains
  public job identity and bounded evaluation outcomes, but excludes job
  descriptions, profile contents, résumé contents, credentials, and raw
  exceptions. Junior verifies that every scored job is represented before it
  publishes a successful result; an incomplete audit fails safely instead of
  becoming a misleading diagnostic record.
- The Scan page paints its starting state immediately after the scan button is
  pressed. Its completion message reports the exact elapsed time and number of
  companies scanned.
- Workday collection no longer stops after 40 jobs when a later page
  incorrectly reports a total of zero. Pagination continues until Junior
  reaches the real end of the listing, while repeated-page detection prevents
  endless collection. The same protection applies to Eightfold.
- Workday and SelectMinds collection now open each posting's detail source
  before evaluation. This provides the full responsibilities, required
  qualifications, workplace wording, location, employment type, and travel
  requirements instead of relying on a short search-result teaser.
- A posting with no usable job description is explicitly treated as an
  incomplete, weak match. Junior no longer displays **Possible gaps: None**
  when it did not have enough information to perform the comparison.
- Qualification extraction recognizes common employer-specific headings such
  as **You may be a good fit if**, **Who you are**, and **What we're looking
  for**, including nested JSON-LD job descriptions.
- Junior evaluates required qualifications and the work described in the job
  posting, not merely a loose collection of matching words. It distinguishes
  required qualifications from preferred or bonus qualifications.
- The active profile's target roles now participate directly in role-family
  alignment. Clearly unrelated work and central missing disciplines become
  critical gaps and are omitted instead of being sent to Review Jobs.
- Generic words such as `system` and `systems`, and a profile strength by
  itself, cannot establish that a job belongs to the user's target profession.
  Unrelated aerospace, finance, retail, and other cross-discipline work is
  omitted before missing practical details can send it to Review Jobs.
- Linux operations evidence does not qualify a kernel-development position by
  itself, and multiword profile gaps must appear as one real concept in the
  role description rather than as unrelated words scattered across the page.
- A Top Match requires strong or very strong résumé evidence, confirmed
  practical eligibility, and no more than one non-critical gap. Strong jobs
  with unresolved practical facts remain Potential Top Matches.
- Safe scan diagnostics record per-company collection and evaluation totals,
  including broad omission categories, without recording job descriptions,
  profile contents, résumé contents, or credentials.
- Supported collectors preserve a bounded failure-stage label in scan
  diagnostics. For example, an Eightfold warning can distinguish the initial
  job-search request from a later results-page request or response-reading
  failure without retaining raw responses, private URLs, or exception text.
- Eightfold connection tests exercise the same job-detail request used by a
  full scan. Temporary throttling and server failures are retried, and a
  remaining failure identifies the safe collection stage where it occurred.
- Fresh Microsoft/Eightfold scans retrieve every plausible job description
  needed for evaluation without depending on an older cache. The title-level
  sift still avoids deep downloads for clearly unrelated work and records that
  decision in the evaluation audit.
- Existing Mistral AI entries that still use its retired Lever source migrate
  transactionally to the verified Ashby board. Junior backs up the database,
  resets the old connection result, and records the source change in its safe
  employer-catalog audit.
- Practical eligibility recognizes explicit citizenship and work-authorization
  requirements, employer wording that offers hybrid or remote arrangements,
  and multiple salary ranges for different job levels. A confirmed outside-area
  job is no longer described as though its location were uncertain.
- If a tracked posting lacks a complete description, Junior says that résumé
  strengths and qualification gaps could not be verified instead of displaying
  misleading `None` values.

These rules are occupation-neutral. They use each profile's own target roles,
résumé evidence, gaps, and exclusions rather than globally hard-coded
technology preferences.

### Distribution and support improvements

RC6 is planned to improve distribution and tester support without weakening
Junior's local-first or user-controlled behavior:

- The manual **Check for updates** action is build-aware. In the installed
  Windows desktop app, a separate **Download and install update** action
  downloads only the exact installer and checksum published on Junior's
  official GitHub release, verifies the SHA-256 checksum, closes Junior, runs
  the installer, waits for its result, and explicitly reopens the app. Junior
  then keeps a plain-language success or failure notice visible until the user
  dismisses it. A sanitized **Update activity** log records the handoff,
  installer result, and restart stage without storing paths, download
  addresses, or raw errors. Checking alone never downloads or installs
  anything. Browser,
  server, and development modes provide the verified release link instead of
  self-updating. Profiles, résumés, companies, applications, and history remain
  in the separate user-data directory.
- Diagnostics provides a selected-profile **Download troubleshooting package**
  action. Junior creates a bounded ZIP containing the importable profile
  configuration, public company catalog, matching latest scan artifacts when
  available, health summary, and allowlisted sanitized logs. It excludes every
  résumé, the SQLite database, credentials, applications, history, personal
  notes, backups, raw scan archives, and arbitrary files. Junior never sends
  the package. A later Contact support action may open the user's email client,
  but it will not attach or send anything automatically.
- Junior will add and validate an MSIX package for Microsoft Store
  distribution. The Store version is intended to remain free to users and use
  Microsoft-managed package signing and updates. The existing open-source
  repository and direct GitHub release channel will remain available.
- The project will apply to the SignPath Foundation open-source program for
  free signing of GitHub-distributed releases. This requires a verifiable
  GitHub Actions build, explicit signing approvals, documented project roles,
  and public privacy and code-signing policies. If Junior is not accepted,
  Microsoft Artifact Signing will be reassessed before purchasing a commercial
  certificate.

MSIX readiness requires more than converting the installer format. Store
acceptance work must verify first installation, launch, icons, external links,
notifications, clean shutdown, user-data paths, SQLite and credentials,
scheduled scans, upgrades, rollback and recovery, and uninstall behavior.
Existing user-owned data must remain outside the application package and must
not be removed by an update, repair, or uninstall.

The Contact support email handoff, MSIX, and signing items above remain planned
RC6 capabilities and are not implemented in RC6 Build 1.19. Users choose the
profile and download the troubleshooting ZIP themselves. Interactive
company-source discovery writes correlated events to the bounded
`junior-application.log`. Each attempt records its submission type, public
hostname, stages, collector families, safe outcomes, counts, elapsed time, and
whether a company was actually created or assigned.

### Planned RC7 language assistance

RC7 is governed by one product rule:

> **Junior explains. Junior does not decide.**

The first and only planned language-model capability is **Explain this job**.
It may translate a posting and Junior's existing structured evidence into a
plain-language explanation for the user. It will not learn preferences, change
scoring, modify a profile, approve or reject a job, pass or save a job, expand
a search, or make an application decision.

Local processing is preferred. Any online provider must remain disabled by
default and require clear, informed user setup before selected information
leaves the computer. Junior's normal scanning, scoring, review, and application
workflows must remain fully usable when language assistance is disabled or
unavailable. This is planned behavior, not part of the current RC5 build.

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
junior-web --settings config\settings.yaml
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

GitHub Actions automatically runs two repository checks for pushes and pull
requests involving `main` or `feature/productization-foundation`:

- **Python validation** uses Windows and Python 3.13 to run Ruff and the complete
  Python test suite.
- **Secret scanning** uses the checksum-verified Gitleaks 8.30.1 release to scan
  all reachable Git history. Findings are redacted, and the temporary report is
  removed before the job ends.

Both workflows use read-only repository permissions, do not persist checkout
credentials, and can also be started manually from GitHub's Actions page. These
remote checks supplement rather than replace the local validation required
before a commit or release.

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

Validate long-term responsiveness with a disposable fictional workspace:

```powershell
.\.venv\Scripts\python.exe scripts\validate_performance_scale.py
```

The default gate creates 100 fictional companies, 100,000 jobs, 10,000
historical applications, 2,500 active applications, and five profiles. It
checks indexed database access and repeatedly renders the real Active
Applications and Application History pages. The August 2026 extended run used
500 companies, 500,000 jobs, 50,000 history records, 10,000 active applications,
and five profiles. Its slowest repeated page responses were 0.100 seconds for
Active Applications and 0.225 seconds for Application History. Every run uses
an isolated fictional workspace and removes it afterward.

Before publishing a release candidate, complete the normal-user walkthrough in
[`docs/RELEASE_CHECKLIST.md`](docs/RELEASE_CHECKLIST.md). It covers the exact
installer artifact from checksum verification through guided setup, first
report, application tracking, restart, update checking, backup, restore,
repair/update, uninstall, and byte-for-byte preservation of isolated user data.

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

The resulting `artifacts\installer\Junior-Setup-0.2.0-RC6-build-1.19.exe` installs under the
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
Kustomize only after replacing `junior:0.2.0` with the exact immutable image
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

Closing the desktop window requests a clean local-server shutdown. If a GUI scan is active, Junior keeps the process and instance lock alive until the scan worker finishes its protected database and report writes. The internal shutdown endpoint remains available to the desktop shell, but Settings does not show a redundant Exit card.

The desktop launcher now uses pywebview to place the same local Flask interface inside a normal native window. It does not create a second UI. A first launch opens at the reviewed 1440 by 900 pixel size, with a 960 by 640 minimum. When the user closes the native window, Junior stores only its size and screen position in the user-owned runtime directory and restores that geometry on the next launch. Missing or invalid state returns safely to the reviewed default. Windows, Linux, and macOS must share the same pages, controls, layouts, validation, typography, and workflows; only genuinely native window chrome, dialogs, notifications, and keyboard conventions may differ. Use `junior-desktop --browser` when deliberate browser-based local use is preferred, or `--no-browser` for an externally managed local server. The released `job-radar-desktop` name remains a compatibility alias. PySide6/QWebEngineView remains the documented fallback if cross-platform testing proves system webview rendering cannot satisfy that shared-interface requirement.

If Windows cannot initialize the native pywebview/Python.NET shell, Junior now
keeps its already-running local service available and opens the same interface
in the user's default browser. It records the build, failure stage, safe runtime
category, Windows and processor details, and the presence, size, and SHA-256
hash of required packaged desktop files. It does not record raw exception
messages, environment contents, credentials, profile data, or rÃ©sumÃ© content.
This recovery path preserves normal access to Diagnostics instead of making a
desktop-shell problem prevent Junior from running.

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

The Profile / Resume page is a read-only home for selecting profiles and reviewing the active profile, résumé insights, and a plain-English summary of what junior is intended to find during targeted company scans. A compact profile selector supports switching, editing, creating, and guarded permanent deletion. junior supports up to five profiles; deleting one also removes its Junior-managed résumé and requires the same typed `DELETE` confirmation used for application deletion. Dedicated create and edit pages keep data entry separate from the summary; Cancel and Back return without saving, and only an explicit Create profile, Save changes, or Save résumé action writes the corresponding change. When no profile exists, the summary page directs the user to create the first one. This workflow does not run a search and is not a broad job-board filter. It stores normalized occupation identities, structured U.S. locations and commute radii, job levels, employment types, schedule, on-call availability, security-clearance handling, workplace arrangements, minimum compensation, travel percentage, and optional work exclusions in SQLite. Workplace choices include Remote, Hybrid, On-site, and Flex. Flex applies only when an employer explicitly describes a flexible workplace arrangement or work model; flexible hours remain a separate schedule preference. A clear requirement for an existing active clearance follows the profile's choice; ambiguous clearance wording is placed in Needs Review instead of being guessed. Exclusions describe roles or responsibilities the user does not want; duplicate lines are normalized and the existing profile evidence boundary evaluates them without assuming that similar-sounding titles mean the same work. Selected locations use approximate straight-line distance to define acceptable hybrid, on-site, and flex commutes. Truly remote jobs ignore commuting distance, while an employer's remote residency restriction must match a location where the user lives or genuinely plans to move. Newly created managed profiles own an occupation-neutral scoring configuration instead of inheriting another user's role, skill, location, or exclusion assumptions. Saved practical preferences feed the shared eligibility, scoring, and recommendation services used by GUI, CLI, and scheduled scans. The former `/preferences` address redirects to Profile / Resume for compatibility. Occupation suggestions use the O*NET 30.3 Database under CC BY 4.0; location suggestions and radius coverage use the U.S. Census Bureau 2025 Gazetteer Files, with display prioritization from the Census Bureau Vintage 2025 Population Estimates. junior includes only the reference fields needed by this workflow and has modified their packaging and presentation.

Profile / Resume also provides an on-demand **Profile Configuration Report**.
The user previews the exact support snapshot before downloading it as a readable
HTML file; Junior neither emails nor uploads it. The report includes the active
profile's job preferences, normalized skill and fit labels, selected companies
and collector types, and effective scoring/recommendation settings. It uses an
explicit safe-field list and excludes the profile name, résumé content and
file, work-history detail, applications, saved and passed jobs, personal notes,
local paths and identifiers, private source URLs, credentials, and raw errors.
Diagnostics links to the same preview for troubleshooting, while the report
itself remains owned by Profile / Resume.

Profile / Resume also provides a separate configuration transfer workflow. The
export control lists saved profiles by display name and downloads the selected
profile's job preferences, structured occupations and locations, fit-board
choices, scoring/report settings, and company selections. It never includes a
résumé record, résumé file, résumé text, application or job-decision history,
notes, scan results, reports, logs, credentials, local paths, or the source
installation's internal profile ID. Import validates a bounded versioned JSON
file, assigns a new internal profile ID, resolves only companies already present
in the receiving global catalog, and creates a separate profile that is not
active. The user must explicitly select it, upload a résumé normally, and then
start a scan. Import never overwrites an existing profile; a duplicate display
name receives a clear Imported suffix. The normal five-profile limit still
applies.

The active managed profile also has a Related Roles workspace. Junior can suggest adjacent titles from packaged O*NET occupation descriptions when the profile's résumé contains supporting work evidence, or from job descriptions previously observed during that profile's own scans. Similar wording alone is not enough. Suggestions tied to an observed employer retain that company context because one title can describe different disciplines at different companies. Every suggestion shows a plain-language explanation and the matched evidence terms. The user must choose **Relevant**, **Not relevant**, or **Different discipline**; only Relevant mappings join the existing target-role boundaries used by company recommendations. No internal score is shown, no suggestion is approved automatically, and the feature does not alter the established job-scoring formula. Junior stores the suggestion, short displayed evidence terms, and feedback in the profile-owned database; it does not store another raw copy of the résumé.

Each profile owns its own company search list. The Companies workspace shows only the active profile's employers and labels each one Scanning or Paused according to that profile's assignment. Existing upgrades complete their pending one-time YAML company import during application startup, before Profile, Companies, or Recommendations can show an empty profile-owned workspace. A company name searches only the existing local catalog. To discover and add a new employer, the user pastes any official company URL: a homepage, careers page, department page, search page, or public job posting. Junior first checks exact catalog names, aliases, normalized careers URLs, and known source identifiers. Exact existing matches require the user to choose the employer. For a confidently recognizable public career site, Junior shows the detected provider and company identity and requires explicit confirmation before creating or assigning anything. Confirmation rechecks the submitted address on the server and runs a bounded real collector test; Junior saves the source only when that test returns a credible public job. Branded pages are inspected for supported recruiting-platform links and metadata before the generic public-page fallback is attempted. Candidate URLs and failed probes remain in memory for that request and are discarded; only the verified working source and its current health are stored. The Add Company page shows an animated checking state during this work. Individual public requests remain bounded, and unfamiliar-source discovery stops after two minutes. A timeout saves no employer or profile assignment and gives the user a safe retry message. Ambiguous catalog names require the user to choose an exact match, while unsuccessful URL setup attempts can be retried or safely removed. The company detail page shows the safe source status, recruiting platform, last check, and returned-job count, and allows a normal user to rerun the non-destructive source test without exposing collector settings or raw failures. It can also keep optional shared Website, Careers, LinkedIn, and Glassdoor shortcuts. Junior opens those public links in the normal browser; it does not log in to, query, monitor, or scrape those services, and changing a shortcut does not change the validated job collector. The new profile assignment starts as Scanning. Employers that are already assigned, unavailable, or missing required setup cannot be added. A user can pause, resume, or remove an assigned company without changing the shared employer definition or another profile's choice. **Remove from this profile** requires typing `REMOVE`, stops future scans only for the active profile, and preserves collected jobs, applications, history, reports, and other historical records. Global employer deletion remains guarded in Administration. The Profile / Resume summary shows the same company count and links to the workspace. When no managed profile is active, the Companies page directs the user to create or select one and does not display legacy YAML configuration. Released CLI/server YAML scan compatibility remains available.

The Companies page can download a versioned JSON copy of the global public
collector catalog and import one from another Junior installation. The transfer
contains only the stable company identity, display name, supported collector
type, availability state, and public structured collector fields. Company
notes, profile assignments, scanning selections, health history, collected
jobs, diagnostics, credentials, and private operational metadata are excluded.
Import validates the complete file before writing, appends only missing company
IDs/names, and uses insert-only storage so a receiving definition cannot be
replaced. It does not add companies to or remove companies from any profile.
For a full tester handoff, import the company catalog first and then import the
profile so its matching company selections can be retained.

Junior does not present its local Employer Catalog as a comprehensive recommendation system. Users choose the employers they want to monitor. A name selects only an employer already in that catalog. A new employer requires any official company URL; Junior then identifies and validates the supported career platform before asking for confirmation. Junior does not invent employer names, silently add companies, broadly crawl the public web, or claim to know the full market for a profession or region. Existing recommendation metadata and Administration services remain available for compatibility and technical maintenance, but they are not part of the normal-user company workflow.

An optional profile setting can surface exceptional matches outside the user's
selected locations. It is off by default. A role must already satisfy Junior's
strong-match rules and have location as its only blocker. These roles appear in
a separate review group and never become Top Matches automatically.

## Settings and Administration boundary

Settings remains the normal-user home for safe personal and product preferences. Report retention, email delivery, and scan scheduling appear as expandable sections on one page. Every section starts collapsed; expanding it reveals the actual controls without opening a separate setup page. Saving or testing returns to the same expanded section, and older Settings bookmarks redirect to the matching section. Installed-version details, runtime paths, health checks, and logs remain in Diagnostics. A manual update check reads Junior's official GitHub release information and reports the result without downloading anything. When a newer supported Windows desktop build is available, the user may separately approve downloading its official installer, verifying its SHA-256 checksum, closing Junior, installing the update, and reopening the app. Browser, server, and development modes do not install updates. Email setup stores credentials through the operating system rather than ordinary settings or SQLite. Scan schedule setup stores an enabled state, local start time, selected weekdays, and email-delivery choice; it shows the calculated next run and safe status from the most recent scheduled scan. On Windows, the same page manages Junior's single `\Junior Scheduled Scan` Task Scheduler entry with normal user permissions and no stored Windows password. Junior's window may be closed and the computer may be locked, but the Windows user must remain signed in and the computer must be awake and powered on at the scheduled time. On Linux, it atomically manages only the marked `junior-scan.service` and `junior-scan.timer` files in the current user's systemd directory and refuses to overwrite similarly named files it does not own. Both platforms start the same `job-radar-scheduled` entry point and shared scan service. The Linux user timer can also run under a dedicated server service account with that account's explicit Junior data root; full logged-out service installation guidance remains part of the later Linux operations milestone. Administration remains a separate, session-scoped safety boundary, but its controls appear as additional collapsible sections inside Settings & Diagnostics rather than opening a separate Administration dashboard. Unlocking requires typing `ADMIN` on the Settings page; this is an explicit confirmation, not a password or protection from someone who already controls the local computer. If the user selects a normal application destination while Administration mode is active, Junior asks whether to exit, closes the elevated session after confirmation, and then continues to that destination. Administration unlock state is limited to the current browser session and Junior process, and restarting Junior invalidates it. The Flask session signing key is generated locally under the user-owned database runtime directory. It is never committed or stored in YAML or SQLite; deleting it invalidates existing browser sessions.

The Scan page keeps full-scan and selected-company receipts separate. A full scan updates the full-scan receipt only. A selected-company scan updates its own receipt immediately when it completes; that card shows when it ran and explicitly explains that another selected-company scan is what replaces it.

Every unlocked Administration subpage includes an explicit **Back to Settings & Diagnostics** link. Junior also uses consistent page spacing and themed scrollbars across the browser and desktop interfaces. Developer-oriented scan commands and resolved paths remain available on the Scan page under a collapsed technical-details section so they do not interrupt the normal scan workflow.

| Classification | Controls |
|---|---|
| Normal Settings | Email setup, report retention, scan preferences, ordinary interface preferences, scheduling preferences, and safe user-facing defaults |
| Administration | Employer Catalog and collector configuration, runtime paths, database operations, backup and restore, legacy import and migration, raw diagnostics, support bundles, and installation-wide defaults affecting every profile |
| Undecided / future | The final placement of support links, bounded diagnostic summaries, and recovery guidance will be decided when those workflows become editable |

The **Settings & Diagnostics** workspace provides normal-user controls for email, scheduling, and retention in collapsed expandable sections. Its separate **Diagnostics** view summarizes application configuration, the latest scan, company sources, and email delivery with green, yellow, red, or neutral status cards. Help remains its own primary page rather than appearing again inside the Settings submenu. Email setup distinguishes a connection test that sends nothing, a privacy-safe diagnostic test email, and delivery of the latest scan summary. The diagnostic message confirms configuration, secure connection, authentication, and server handoff without including addresses, credentials, profile data, résumé contents, or raw server responses. The readable summary is the email body; the full HTML report remains attached. Email test and delivery outcomes appear in a dedicated sanitized Email activity log. Problems are categorized as configuration, collector, network, email, or unexpected application failures and include a plain-language next step. A separate developer-log pane shows one recognized Junior-owned log at a time as timestamped structured text and downloads a complete `.log` copy without simplifying or dropping safe fields. Selecting another log returns to the log viewer instead of the top of the page. The on-screen view is limited to the newest 200,000 bytes. It is not a general file browser: nested paths, arbitrary logs, editing, deletion, and unrestricted downloads are rejected. Job descriptions, profile and résumé contents, credentials, tokens, environment contents, request headers, and raw exception text are neither stored in these logs nor displayed. AI résumé tailoring is visibly marked **Under development** and provides no enablement, credential, provider, or connection-test controls. Job reports provide no tailoring action. Retained experimental AI code does not send data, alter Junior's deterministic scoring, or add provider calls, cost, or delay to scans. Administration includes the global Employer Catalog, where an unlocked administrator can create and edit structured employer-source settings, run bounded local validation, test the real collector connection without importing jobs, and enable, disable, or retire an employer. A connection test records the last attempt, last success, last problem, returned-job count, and a safe troubleshooting category. It never stores raw collector or network error text, and editing source settings clears stale connection health. The employer detail page can assign an available, validated employer to any managed profile or remove one profile's assignment without affecting another profile or deleting collected history. Permanent deletion requires typing `DELETE` and is permitted only when no profile assignment or collected job references the employer; otherwise the administrator must disable or retire it. The Employer Review Queue lets unresolved profile submissions be matched to an existing employer, used to prefill a new employer, assigned after availability checks, or closed as unsupported, rejected, or duplicate. Recommendation Administration provides employer/profile diagnostics, global employer recommendation metadata and eligibility, profile-specific feedback inspection and guarded reset, and explicitly bounded rebuilds for one profile, one employer, or every profile. Recommendation maintenance has a sanitized audit and does not silently override profile feedback. Review decisions have a sanitized audit trail. New and edited employers must validate before they can be globally enabled. Disabling or retiring preserves profile assignments and collected history; an unavailable employer is omitted from scans until it is enabled again. Packaged company defaults are empty for new installations. Existing legacy definitions import only once into the active profile, never replace a user-edited database employer with the same stable ID, and remain separate from later user-owned catalog changes. Other Administration categories remain planned.

Developer logs retain allowlisted scan and job-evaluation traces, a unified
application activity history, and startup failures. Scan and evaluation
filenames identify the exact scan run. The application log correlates database
writes and slow operations, user actions, safe failures, decisions, email,
company discovery, and updates while omitting routine fast reads and form
values. Safe failures retain an error type and correlation ID, never raw
exception text. Structured operational events identify their schema,
Junior version and build, subsystem, severity, stage, status, counts, timing,
reason codes, and safe failure category when those facts apply. The viewer
and complete timestamped `.log` downloads use conventional one-line structured
text: timestamp, severity, subsystem, event, and detailed `key=value` fields.
Non-scan activity is consolidated in `junior-application.log`, which rotates at
2 MB and keeps one previous file. Scan and evaluation traces remain separate.
The configured dated-log retention count is applied independently to each scan
log purpose, and a 100 MB aggregate ceiling removes the oldest dated trace when
the configured count would otherwise consume excessive storage.
A developer can follow the same scan run or request across related logs and
inspect every retained safe field without exposing full job descriptions,
profile settings, résumé contents, submitted form values, secrets, environment
contents, request headers, SQL values, or raw exception text.

Companies is the normal working area for both profile membership and company
source health. The source-health card starts collapsed and reports all working
sources in green or identifies sources needing review in yellow. Expanding it
shows whether each company is scanning, which collector it uses, the latest
scan result, and the latest bounded connection-test result.
When a supported recruiting platform explicitly confirms that its board has no
current openings, Junior reports the source as connected with zero openings
rather than treating the empty board as a source failure.
Users can pause or resume a company, test one or more sources without importing
jobs, and remove a company from only the active profile without deleting its
history. Connection-test progress and individual results refresh on that same
page. Diagnostics summarizes overall source health and links directly to this
workspace when action is needed.

Actual selected-company scans belong on the Scan page, separately from
connection tests. A user can expand **Scan selected companies**, choose up to
25 enabled companies from a compact table, and run the same collection,
deduplication, scoring, and Review Jobs import used by a full scan. The
selected scan writes its own targeted report instead of replacing the latest
full-scan report. Stable job identity prevents duplicate records, while
existing Save, Pass, and Apply decisions continue to suppress already-decided
jobs. A separate collapsible results summary shows the newest scan totals and
plain-language company-source warnings. Runtime paths and developer command
details remain in Diagnostics rather than the normal Scan workflow.

Green means working, yellow means incomplete or needs review, red means an
actual source failure, and neutral means not yet tested or not included in the
latest scan. Safe
failure explanations distinguish an unreachable source, denied public request,
missing address, temporary request limit, recruiting-service problem, and a
collector that could not interpret the returned job list.

Every state-changing web form and background action uses a session-bound CSRF token. Junior rejects missing, invalid, or stale tokens before route business logic runs, so the attempted change is not written. Normal forms receive a plain-language recovery page; background requests receive a bounded JSON error. Refreshing the page creates or loads the current token and allows the user to review and resubmit. GET routes remain read-only.

A successful scan writes fixed-name outputs in the user-owned `reports` directory. The latest HTML report, structured snapshot, email preview, and compressed raw-scan ZIP keep stable filenames. The HTML and email outputs summarize relevant results so thousands of unrelated or omitted postings do not make the normal report unreadable. The raw-scan ZIP contains a normal text file with every public posting collected in that run, including its public description, for download and offline review; Junior does not render that large file in the GUI. A failed or interrupted scan does not replace the last valid result. Profile-owned actions taken from scan data persist separately: saved jobs, passed jobs, tracked applications, and application history remain after reports are replaced and continue to suppress already-decided jobs from Review Jobs. New installations retain the latest 10 successful report runs by default. Existing installations keep their saved policy and may choose latest only, latest plus previous, or a total from 1 through 50. Before replacement, Junior copies and verifies the prior complete set in its marked `reports/archive` directory. The Reports page provides direct downloads for current and retained exports. Because raw ZIPs can grow with employer and job volume, Settings shows the retention control and lets the user reduce the number kept. The same Settings page limits recognized dated Junior logs while preserving active logs and unrelated files. Reduced limits are enforced on the next successful scan.

Scans started from the GUI run in the background. The rest of junior remains available while a scan is running, and every page monitors the same durable scan status. An app-wide notification reports completion, completion with source warnings, or failure and links to the appropriate results or details.

SMTP passwords must not be stored in YAML, SQLite, logs, reports, previews, bootstrap files, packages, or source control. Junior can store desktop credentials in the operating system's credential manager through the packaged `keyring` adapter; settings retain only the non-secret `smtp_credential_key` reference. The established `smtp_password_env` environment-variable reference remains supported for existing installations, servers, containers, and automated deployments. If the operating system has no usable secure credential backend, Junior reports that credential storage is unavailable and does not fall back to a plain-text file.

Settings includes an expandable Email section with Gmail, Outlook, and Custom SMTP choices, username and password entry, sender and recipient delivery details, and a clear credential-storage status. Gmail and Outlook use their standard SMTP server, port, and transport-security defaults; provider policy may require an app password or separately enabled SMTP access. Saving validates a complete replacement settings file before atomically activating it, preserves unrelated and newer settings keys, and writes a newly entered password only to the operating-system credential manager. **Test Connection** connects, negotiates TLS when configured, and authenticates without sending a message, launching a scan, or producing a normal report. A session-scoped status card shows the tested provider, result, time, credential-storage method, and a short reason. Ordinary results are limited to Connected, Not configured, Authentication failed, Server unreachable, or TLS negotiation failed; the browser session contains no password or raw SMTP failure.

The same expandable Email section provides **Send latest scan summary** as an explicit end-to-end delivery check. It uses only saved email settings, sends the already-generated plain-language summary, attaches the full latest HTML report, and does not run a scan or change stored job data. Junior reports a clear success or safe failure result on the page. A complete successful scan must exist before this action can send anything.

The downloadable `junior-last-scan.log` records the newest scan's stages,
collector types, counts, safe failure categories, and elapsed time.
`junior-application.log` correlates company setup, user actions, database work,
email, updates, job decisions, and safe application failures. Company setup
records whether the input was a name or URL, public hostnames, discovery and
validation stages, final status, elapsed time, and whether Junior actually
created or assigned the company. It is included automatically in every
troubleshooting package. Scan run and evaluation traces remain separate.
Application logging is limited to the current 2 MB file plus one previous file;
dated scan/evaluation history also has a 100 MB aggregate ceiling. None of the logs
contains job listings, employer names, submitted URLs, profile settings, or
résumé contents.

## Database upgrade recovery

Before changing an existing database structure, junior creates a backup in the `backups` directory beside the active database. The established default Windows location remains `%LOCALAPPDATA%\JobRadar\data\backups`. Backup filenames identify the database and migration range, for example `job_radar.sqlite3.pre-migration-v1-v3-<timestamp>.bak`.

If junior reports an upgrade failure, close junior and do not delete, rename, replace, or repeatedly reopen the active database or its backups. Preserve the complete `data` directory and contact Clayton Graves at `claytonmgraves@outlook.com`. Include the displayed technical details and diagnostic-log location, but do not send the database, résumé, profile, passwords, access tokens, or other credentials unless an approved secure support process is provided.

Unlocked Administration provides a **Backup and recovery** screen. Its backup action creates a verified `.jrbackup` bundle and downloads a portable copy through the application. The bundle contains a consistent SQLite copy plus Junior-owned settings, company/scoring configuration, managed profile and résumé files, reports, and sanitized logs. Junior validates the manifest, file paths, sizes, checksums, and database before restoring into the same or a separate installed workspace. It creates a separate pre-restore safety backup first and tells the user to restart after success. The source workspace remains unchanged. Credentials remain in Windows Credential Manager or their configured environment variable and are never included. The same screen can download a readable JSON database export; that export is for review and portability and cannot be used as a restore bundle.

Junior also creates safety backups automatically immediately before an eligible permanent profile or company deletion. Profile deletion preserves the complete workspace because the profile and managed résumé span SQLite and files; company deletion preserves a verified SQLite copy because the employer catalog is database-owned. Invalid confirmations and in-use records are rejected before a backup or deletion occurs. Existing schema upgrades continue to create their established pre-migration backups.

## Acknowledgements

### Early Field Testing

Special thanks to Dawn Peacock for extensive early usability testing and
workflow feedback that directly shaped the RC5 review workflow, job management
model, and company discovery improvements.

Special thanks to Jerry Reddick for field testing Junior's company discovery
and job-source workflows and providing direct usability feedback.

## Documentation

- [User Guide](docs/USER_GUIDE.md)
- [Development Guide](docs/DEVELOPMENT.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Security and Privacy](docs/SECURITY.md)
- [Roadmap](docs/ROADMAP.md)
- [Release Checklist](docs/RELEASE_CHECKLIST.md)
- [Changelog](CHANGELOG.md)

## License

Junior is free software licensed under the GNU General Public License,
version 3.0 only (`GPL-3.0-only`).

See [LICENSE](LICENSE) for the complete license terms. Third-party components
and reference data retain their own licenses and attribution requirements,
which are inventoried in
[THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md). The repeatable,
machine-readable audit is stored in
[dependency-license-report.json](dependency-license-report.json).
Both audit files are included in the Windows installer, Linux standalone
archive, container image, Python wheel, and source distribution.

Junior's implemented data and network behavior is documented in
[PRIVACY.md](PRIVACY.md). Report security issues privately by following
[SECURITY.md](SECURITY.md), not through a public issue. Official downloads are
published only on the
[Junior GitHub releases page](https://github.com/lordegraves/junior/releases);
verify each installer with its published SHA-256 checksum.

## Product boundaries

junior is designed to remain:

- local-first and user-controlled
- based on configured companies rather than broad crawling
- transparent in scoring and recommendations
- safe for manual review
- independent of automatic applications or recruiter outreach
- usable through one shared service layer across CLI, browser, packaged, and service modes

The long-term target is a configurable cross-platform application that a non-developer can install, launch, configure, and operate without editing source files by hand.
