# Changelog

All notable changes to junior are documented here.

This project follows the spirit of [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Version numbers are currently managed in `pyproject.toml`.

## Unreleased

- Added a first-class Google Careers collector. Junior now recognizes Google’s
  public careers URL, reads every reported results page with bounded
  concurrency, and preserves Google’s complete public descriptions,
  qualifications, locations, compensation text, and stable job identifiers.
  Company setup validates Google directly instead of incorrectly reporting
  that Bing could not verify the valid public job source.

- Rebuilt RC6 Build 1.17 with a Windows desktop-shell recovery path. If the
  packaged Python.NET/WinForms backend cannot initialize, Junior now records
  privacy-safe runtime evidence and opens its already-running local interface
  in the default browser instead of becoming unusable. Startup logs now include
  the exact Junior build, failure stage and category, operating-system and
  architecture facts, and safe integrity details for required packaged runtime
  files without exposing raw errors, credentials, profile data, or rÃ©sumÃ©s.

- Made company-source status use the newest available evidence, so a source
  edit remains untested until verified and a successful later test clears stale
  red scan state while preserving the earlier warning in its audit trail.
- Treat valid empty Greenhouse and iCIMS job boards as connected with no public
  openings, and keep source-health totals, filters, and live test results in
  agreement.

- Treat an iCIMS board that explicitly reports no current job openings as a
  healthy connected source with zero openings. This prevents employers such as
  DDN from appearing under Needs attention when their public board is working
  normally but temporarily empty.

- Integrated the session-scoped Administration workspace into Settings &
  Diagnostics. Unlocking now reveals consistent collapsible administrative
  sections on the same page. Normal navigation while Administration mode is
  active asks the user to exit that mode before continuing, preventing elevated
  access from being carried casually through the rest of the application.
- Added a forward-only database migration for the employer source-change test
  flag. Existing installations that had already completed the earlier source
  health migration now receive the field safely, preventing source-test write
  failures and Employer Catalog page crashes after an upgrade.

- Corrected company-source batch testing so a running scan cannot make several
  unrelated employers appear broken through database contention. Unexpected
  worker failures now produce a clear inconclusive result and a privacy-safe
  diagnostic event. Company health can be filtered to healthy, needs-attention,
  or untested sources, and the table checkbox selects only the visible rows.

- Added a guarded recruiting-platform migration workflow to the Employer
  Catalog. An administrator can move an existing employer to a different
  supported collector while preserving its stable identity, profile
  assignments, collected jobs, and application history. The form explains
  the installation-wide effect and requires explicit confirmation. A migrated
  employer is disabled, its obsolete source-health result is cleared, and it
  must pass configuration validation and a live connection test before it can
  be enabled again. The sanitized audit records the change as a source
  migration without storing collector configuration.

- Consolidated each company detail page into one Job source workspace with the
  public request URL, profile state, platform, connection health, last test,
  returned-job count, and aligned actions. Source-test outcomes no longer
  appear twice, reference links are collapsed, and unlocked administrators can
  open the existing global source editor directly to correct, validate, and
  retest a collector without changing profile assignments or job history.

- Reorganized Review Jobs into one consistent workspace. Summary cards for Top
  Matches, Potential Matches, Needs Review, New This Scan, and Saved & Passed
  keep every queue one click away while the selected queue's controls and
  collapsed company groups appear below. New This Scan is identified as a
  cross-category shortcut, redundant dashboard/report links were removed, and
  scan files remain under Scan and Reports & Audit instead of being repeated
  in the review inbox.

- Distinguished the Companies page controls: persistent left-hand checkboxes
  select sources for testing, while sliding switches control whether the active
  profile scans each company.

- Reworked Companies into a persistent global catalog with a per-profile scan
  toggle. Turning a company off no longer hides or removes it, and source-test
  selection appears only while the user is choosing sources to test.
- Removed thousands of unnecessary résumé comparisons for jobs already blocked
  by citizenship, clearance, work authorization, or unrelated eligibility
  rules. A copied 11,140-job cross-profile scan reduced scoring from about 442
  seconds to about 83 seconds while preserving the same 10 surfaced jobs.
- Made the packaged local server accept navigation and progress requests while
  its background scan worker is scoring, and made company scan toggles save
  without navigating away from the current page position.
- Improved required-qualification interpretation for legal sponsorship notices,
  optional “preferred” and “a plus” clauses, generic ATS impact/complexity
  sections, dated marketing experience, budgets, teamwork, and communication
  across organizational levels. Oracle summary-only listings now request their
  full detail before evaluation, and plausible “analyst” and “insights” titles
  receive description review instead of being rejected from the title alone.
- Added bounded TalentBrew result pagination with duplicate and repeated-page
  protection. Ford and other large TalentBrew sites no longer stop after the
  first 15 listings; collected jobs still use the existing normalization and
  evaluation rules.
- Older generic HTML definitions now recognize TalentBrew and SAP
  SuccessFactors markers and follow their platform-specific result pages.
  Workday collection now allows up to 2,000 listings rather than silently
  stopping at 1,000 for large employers such as HPE.

- Moved installed-version details and manual verified update controls from
  Diagnostics to the top of Help & About, keeping troubleshooting pages
  focused on operational health and support evidence.

- Add a one-click, selected-profile troubleshooting package to Diagnostics.
  The bounded ZIP combines importable profile configuration, the public
  company catalog, matching latest scan artifacts, health information, and
  allowlisted sanitized logs. It is never sent automatically and deliberately
  excludes résumés, SQLite data, credentials, application activity, personal
  notes, backups, raw scan archives, and arbitrary local files.
- Prepare `RC6 Build 1.15` for controlled cross-profile accuracy testing. A
  required qualification that wraps a concrete named capability in ordinary
  hiring language can now use direct résumé evidence for that capability,
  and an explicit experience-year range can use dated employment evidence for
  its named alternative capabilities. Managed-profile Strong fit entries now
  reach the shared résumé matcher without becoming evidence by themselves.
  Role alignment no longer treats a shared broad word or familiar tools as
  proof that two different professions are equivalent, and sparse postings
  remain review-level unless a specific configured target title is present.
  Existing eligibility, location, compensation, and omission boundaries remain
  unchanged.
- Prepare `RC6 Build 1.14` for field testing with safe profile and global
  company-catalog transfer, append-only duplicate handling, inactive profile
  imports, résumé exclusion, and Junior-styled file selectors.
- Make Companies and source health a collapsible card. Its closed state shows
  a green all-working summary or yellow review guidance, while expansion keeps
  the existing tests, progress, individual health details, and profile actions.
- Add separate profile and company-catalog transfer workflows. Profile / Resume
  exports a profile chosen by its visible name and imports it as a new inactive
  profile with a new internal identity. Résumé files and text, applications,
  history, saved decisions, notes, scan data, reports, logs, credentials, and
  local paths are never transferred. Companies exports only the global public
  collector catalog; import appends missing definitions, skips duplicates, and
  cannot overwrite existing companies or alter any profile's company list.
- Add purpose-specific, timestamped troubleshooting logs for scan execution,
  per-job evaluation decisions, database writes and slow operations, user
  actions, and safe application errors. Diagnostics explains what each log is
  for and displays its descriptive filename. Correlation IDs and scan-run IDs
  let support trace related events without recording résumé text, full job
  descriptions, submitted form values, SQL values, credentials, or raw
  exception messages. Existing log-retention choices apply independently to
  each troubleshooting purpose.
- Add a Profile Configuration Report under Profile / Resume, with a
  Diagnostics shortcut, an inspectable preview, and a user-directed HTML
  download. Junior never emails or uploads the report, and its explicit safe
  field list excludes identity, résumé content, work history, applications,
  notes, local paths and identifiers, private source URLs, credentials, and
  raw errors.
- Rename the combined workspace to **Settings & Diagnostics**, remove the
  redundant Help submenu entry, and use **Diagnostics** consistently for
  health checks, runtime information, and logs.
- Keep the Diagnostics log picker anchored at the log viewer, add a dedicated
  privacy-safe email activity log, expose connection and delivery tests beside
  email status, and add a diagnostic test message that contains no addresses,
  credentials, profile data, or raw server responses.
- Send the readable scan summary as the email body and retain the full HTML
  report as an attachment instead of rendering the report's large cards inside
  the message body.
- Keep the selected-company scan receipt independent from ordinary full scans,
  label when it was completed, explain what updates it, and refresh its figures
  immediately when a new selected-company scan finishes.
- Preserve explicit at-scale experience requirements during résumé comparison
  across Junior's shared technology and infrastructure vocabulary, while leaving
  ordinary skill requirements and broader scoring thresholds unchanged.
- Distinguish an undated skill mention from a supported number of years by using
  explicit duration statements or dated employment blocks, without crediting
  unrelated tenure or double-counting overlapping roles.
- Make Help topic, Previous, and Next links open the requested section, close
  the other Help cards, scroll the selected card into view, and preserve its
  bookmark fragment.
- Rename the Home attention shortcut from **Open tracker** to **Open
  Applications** so it matches the consolidated Applications workspace.
- Add a prominent Settings and Diagnostics navigation strip to those related
  pages while keeping Help as its own primary destination.
- Reorder the normal-user navigation around Junior's actual workflow, combine
  Active Applications and Application History beneath one Applications
  destination, identify read-only exports as Reports & Audit, and keep
  Diagnostics reachable from Help and Settings instead of treating troubleshooting
  as an everyday primary task.
- Let a manually launched Windows repair or update ask Windows to close a
  running Junior cleanly before replacing locked application files. Setup never
  force-closes Junior, preserving the existing protection for scans and durable
  database/report writes.
- Keep all Help topics on one desktop row with shorter labels and responsive
  four- and two-column layouts for narrower windows.
- Add a navigable Help & About page to RC6 Build 1.13. The
  page presents curated normal-user guidance as collapsible cards while the
  repository README retains developer, packaging, and operations material.

- Prepare the fully audited, accuracy-validated product as `RC6 Build 1.13`,
  including canonical Junior commands, the renamed GitHub release location,
  disabled under-development AI controls, and expanded large-data GUI checks.

- Make `junior`, `junior-desktop`, `junior-web`, `junior-scheduled`, and
  `junior-backup` the canonical installed commands while retaining released
  `job-radar*` aliases for existing automation and upgrades. Update official
  repository, release, update-check, license, and security links to the renamed
  `lordegraves/junior` GitHub repository.
- Park all AI résumé tailoring while the feature remains under development.
  Settings provides no enablement or connection controls, job reports provide
  no tailoring action, and direct legacy requests cannot activate the feature.
  Retained experimental OpenAI and local-model code has no role in scans.
- Retain the experimental OpenAI advisory implementation with bounded retry,
  refusal handling, evidence-grounded prompts, and secure credential boundaries
  for future development; it is not currently exposed to users.
- Record a 100 percent observed agreement rate in the latest 50-job
  risk-weighted, non-LLM validation: all nine surfaced jobs, the 15
  highest-scoring omissions, 25 random omissions, and the Ford India-remote
  regression case agreed with the expected outcome. The underlying installed
  scan evaluated 19,863 postings with no incomplete plausible postings or
  collector errors, and the automated suite passed 1,304 tests. This is a
  measured validation sample, not a claim that every collected job was
  manually reviewed.
- Brand the Windows setup wizard with Junior's logo and distinguish a new
  installation from an update or same-build repair in the wizard title,
  instructions, action button, and completion message.
- Make transient source fallback deterministic: retry non-Eightfold sources
  once, re-evaluate cached summaries through the normal detail planner, recover
  plausible descriptions within a strict circuit breaker, distinguish complete
  cache from visibly withheld incomplete cache, and emit one consolidated
  warning without changing scoring behavior.
- Recover complete plausible descriptions from fresh Microsoft/Eightfold,
  Workday, Oracle, and public HTML sources without requiring a pre-populated
  cache, while continuing to skip clearly unrelated detail downloads safely.
- Automatically migrate Junior's obsolete Mistral Lever source to its verified
  Ashby board, with a transactional backup and employer-catalog audit entry.
- Preserve multiple level-specific salary ranges, recognize explicit hybrid-or-
  remote and citizenship requirements, describe confirmed location mismatches
  with certainty, and stop incomplete tracked jobs from claiming no strengths
  or gaps.
- Build an experimental OpenAI advisory foundation with explicit
  résumé-transmission consent, operating-system credential storage, structured
  responses, and safe deterministic fallback. The experiment is now parked;
  no AI controls or tailoring actions are exposed and scans do not call OpenAI.
- Retrieve complete Oracle HCM and ADP requisition details through their
  structured public endpoints, retry transient Workday detail failures once,
  and distinguish plausible incomplete jobs from safely skipped unrelated
  listing teasers.
- Separate worker-queue time from actual per-company collection time and refine
  advanced network failure-model gaps without claiming a candidate lacks basic
  networking experience.

- Give immediate visual acknowledgement when full scans, selected-company
  scans, and connection tests are submitted, and prevent duplicate clicks
  while Junior starts the requested work.
- Enforce explicit hybrid and on-site wording from complete descriptions before
  looser ATS remote hints, then check those jobs against profile locations.
- Keep already-tracked applications out of Potential Top Matches and location
  outliers, while keeping accepted on-call obligations visible on job cards.
- Preserve Workday employment type during detail normalization and refresh old
  Workday cache entries once after the parser upgrade.
- Replace the scan-profile tile wall with a formatted list and label the
  exceptional-location option as Enabled or Disabled.
- Replace the completed-scan dashboard tiles with a compact five-line receipt,
  and render the recorded duration before JavaScript runs.
- Make each company group clearly show its individual Expand or Collapse action.
- Omit unsupported kernel-development roles from infrastructure searches, and
  stop inventing multiword profile gaps from unrelated words scattered across
  a posting.
- Expand the latest completed-scan card with duration, companies, collected
  jobs, recommendation outcomes, new/seen/changed totals, and source warnings.
- Prevent Eightfold detail services from holding a scan for hours: reuse
  verified descriptions, cap optional detail enrichment at five minutes per
  employer, stop after three consecutive detail failures, retain all valid
  listings, and evaluate insufficient listings conservatively.
- Show a continuously updating `HH:MM:SS` scan clock plus the current company,
  recruiting platform, listing page, and description-retrieval operation.
- Persist only bounded public scan-progress labels, and report a plain-language
  warning when Eightfold listings were collected without complete descriptions.
- Add an atomic all-source posting cache so follow-up Workday and Eightfold
  scans reuse fresh unchanged descriptions, while new, changed, stale, and
  previously incomplete jobs still retrieve and evaluate complete details.
- Bound Workday detail retrieval to four workers, make Eightfold honor
  `Retry-After` and bounded exponential backoff, and make its connection test
  exercise a later results page.
- Show live and final elapsed scan time, record separate company, evaluation,
  and report-generation timings, and report how many details were reused.
- Treat profile work exclusions as central-role rules: match titles and
  explicitly stated primary responsibilities, but do not reject strong jobs
  for an incidental phrase elsewhere in a long description.
- Keep full-scan and selected-company evaluation audits separate, timestamp
  audit downloads, and reject incomplete audits that do not account for every
  scored job.
- Show immediate scan-start feedback and include exact elapsed time and
  company totals when scans finish.
- Make Eightfold connection tests exercise the full job-detail path, retry
  temporary throttling or server failures, and report the failed collection
  stage safely.
- Add a downloadable privacy-safe evaluation audit explaining why every
  collected job was surfaced or omitted.
- Require successful scans to verify that their evaluation audit was durably
  created, and warn on Reports when a current report set is missing it.
- Retain each evaluation audit with its verified archived report set.
- Collect complete Workday and SelectMinds job-detail records before
  evaluation so travel, regional restrictions, telework language,
  responsibilities, and required qualifications are not lost in listing
  teasers.
- Treat a missing job description as an incomplete weak match instead of
  reporting that no résumé gaps were found.
- Recognize additional employer-specific qualification headings and nested
  JSON-LD job postings when comparing required work with résumé evidence.
- Label the application, executable metadata, and installer consistently as
  `RC6 Build 1.11`.
- Add direct **View posting** links to Active Applications and Application
  History when the original public job address is available.
- Identify the safe collection step behind Eightfold scan warnings, including
  whether Microsoft failed on the initial job-search request, response reading,
  or a later results page, while keeping raw responses and private details out
  of diagnostics.
- Add a GUI **Send latest scan summary** action that uses saved email
  settings, sends the latest generated summary, attaches the full HTML report,
  and reports a safe end-to-end delivery result without starting another scan.
- Stop generic words such as `system`, `systems`, and a profile strength by
  itself from establishing role alignment. Clearly unrelated aerospace,
  finance, retail, and other cross-discipline jobs are now omitted before
  missing practical details can send them to Review Jobs.
- Begin RC6 with complete Workday and Eightfold pagination that ignores false
  zero totals, detects repeated pages, and stops only at a verified boundary.
- Evaluate required qualifications, central job disciplines, described
  responsibilities, profile target roles, configured gaps, and explicitly
  avoided work before surfacing a job. Preferred and bonus qualifications do
  not become required gaps.
- Omit clearly unrelated or critically mismatched jobs instead of sending them
  to Review Jobs, while preserving uncertain and plausibly adjacent work for
  human review.
- Require Strong or Very Strong résumé evidence for Top Match, in addition to
  confirmed practical eligibility and the existing gap limit.
- Add privacy-safe per-company scan diagnostics for collected, actionable,
  omitted, and broad omission-reason totals without storing job, profile, or
  résumé contents.
- Group Review Jobs by company within each bounded result page, show
  page-specific and overall company counts, preserve selections when groups
  are collapsed, and add numbered navigation for direct page changes.
- Start Review Jobs company groups collapsed while preserving individual,
  Expand all, and Collapse all controls.
- Replace separate troubleshooting-log cards and simplified prose exports with
  one developer-oriented structured-log viewer and timestamped `.log`
  downloads. Each line identifies its timestamp, severity, subsystem, event,
  and detailed safe fields while retaining the existing privacy allowlist.
- Wait for every packaged Junior process to release the installed executable,
  then run the verified Windows update, record a sanitized
  handoff/installer/restart log, and reopen Junior only after the durable
  result is ready.
- Align troubleshooting-log card content and actions while exposing update
  activity alongside scan, operational, and user-action diagnostics.
- Label the corrected final RC5 field-test package and every application page
  as `SP5 Build 1.14`.
- Keep the Scan page focused by showing a compact success message when all
  company sources work and expanding specific company-source problems only
  when attention is required.
- Prevent company-source test forms from opening raw JSON when page scripting
  is unavailable, and restore page-specific scripts needed for live progress.
- Simplify company-row controls to side-by-side Pause and Remove actions while
  preserving the guarded profile-removal confirmation.
- Guarantee that an approved desktop update releases protected writes and the
  single-instance lock before terminating wrapper threads that could otherwise
  prevent Windows Setup from starting.
- Stop updater handoffs after a bounded shutdown wait, preserve the existing
  installation, reopen Junior, and show a durable failure result instead of
  waiting indefinitely while claiming an update is installing.
- Merge profile company management and bounded connection testing into one
  Companies table with live progress, collector details, source health, and
  quieter profile-only removal controls.
- Move actual selected-company scanning to a collapsible Scan-page workflow
  that uses the normal live scan progress, imports new deduplicated jobs into
  Review Jobs, preserves prior decisions, and writes a separate targeted
  report without replacing the latest full-scan report.
- Replace selected-company scan cards with a scalable selection table and
  replace developer-oriented Scan-page details with a collapsible
  plain-language results and company-warning summary.
- Treat a successful real scan as the newest source-health evidence so a
  working source no longer remains red because an older connection test failed.
- Give source-health rows consistent green, yellow, red, and neutral state
  indicators with readable status text and descriptions.
- Present sanitized diagnostic events as readable, timestamped steps and
  download them with dated support-friendly filenames.
- Wait for the verified Windows installer to finish, reopen Junior explicitly,
  and keep a plain-language success or failure result visible until dismissed.
- Put Company Source Health directly in the Companies workflow with clear
  working, warning, and untested counts.
- Keep background source-test progress refreshing after a temporary page
  refresh failure instead of requiring the user to leave and reopen the page.
- Replace Settings dashboard cards and separate setup pages with four collapsed
  expandable sections whose controls stay on the main Settings page.
- Explain when USAJobs sources cannot run because local USAJobs API access is
  not configured, rather than showing a generic source-setup warning.
- Relaunch Junior after an automatic Windows update completes while preserving
  the optional launch choice for normal interactive installation.
- Prevent the Windows updater from invoking Restart Manager after Junior has
  already completed its clean update handoff.
- Keep Diagnostics information cards within their grid rows and give the
  troubleshooting-log table readable column widths.
- Prevent the Windows update installer from racing Junior's still-running
  desktop process. A detached handoff now waits for Junior to close cleanly
  before starting the already verified installer and reopening the app.
- Promote Diagnostics to a top-level health and troubleshooting workspace.
  Settings now contains only editable user controls, while Diagnostics owns
  installed-build details, runtime paths, scan defaults, health summaries,
  and sanitized troubleshooting logs.
- Add live company-source test progress with the current company, current
  step, percentage complete, safe per-source results, and an automatically
  refreshed readable results table.
- Bound Eightfold connection tests to a small source sample so health checks
  do not trigger thousands of detail requests or create avoidable rate-limit
  failures. Normal Eightfold scans retain full collection behavior.
- Clarified Diagnostics as Junior's overall health and troubleshooting
  workspace while Company Source Health owns per-company connection tests and
  targeted rescans. Source results now show their safe explanations directly
  instead of hiding them in hover text.
- Added human-readable names and descriptions for sanitized logs, enabled
  normal attachment downloads in the desktop shell, and labeled each log view
  by its actual purpose.
- Added safe company identifiers and bounded failure explanations to scan
  diagnostics. Common HTTP outcomes now distinguish access denial, missing
  source addresses, request limiting, and temporary recruiting-service
  failures without recording raw exceptions or responses.
- Added an explicit, checksum-verified Windows desktop update workflow. Checking
  remains read-only; a separate confirmation downloads the exact official
  installer and checksum, rejects mismatches, closes Junior cleanly, installs
  the update, and reopens without moving or replacing user-owned data.
- Label field-test packages and every application page as `SP5 Build 1.5`.
- Added reusable TalentBrew discovery so branded career sites such as Ford can
  lead Junior to their verified public job-search page without a company-only
  exception.
- Added a bounded, sanitized company-discovery log that records which collector
  family and public hostname Junior tested, whether jobs were verified, and
  whether optional external lookup was used. URLs, profile data, résumés,
  credentials, and raw exceptions are excluded.
- Kept company-source testing visibly active with an elapsed-time indicator,
  and aligned the company confirmation field and action.
- Moved installed build, schema, and manual update information onto the main
  Settings page. Removed the redundant Exit card while preserving the desktop
  shell's protected clean-shutdown mechanism.
- Added clickable latest-scan and company-source Diagnostics details. Normal
  users can review sanitized per-company collector warnings, open the global
  read-only Collector Catalog, test selected or all untested sources in the
  background, and run a targeted scan for selected companies without replacing
  the latest full-scan report.
- Made the manual update check field-test-build aware. It compares the installed
  SP5 build with installer assets on Junior's verified RC5 GitHub release.
- Added an off-by-default profile option for exceptional matches outside the
  user's selected locations. Eligible roles must already satisfy Junior's
  strong-match rules and have location as their only blocker; they appear in a
  separate review group and never become Top Matches automatically.
- Added bounded, privacy-safe scan diagnostics. The downloadable
  `junior-last-scan.log` explains the latest scan's stages, collector types,
  counts, safe failure categories, and elapsed time without storing employer
  names, job listings, URLs, profile settings, or résumé contents. A bounded
  general diagnostic history is retained separately.
- Fixed Eightfold collection when the server returns smaller pages than Junior
  requests, and preserved an employer's explicit Flex workplace field.
- Label field-test packages and every application page as `SP5 Build 1.3`, and
  include the same build identity in diagnostics and generated reports.
- Add an explicit Flex workplace arrangement to profile creation and editing.
  Junior recognizes explicit flex-workplace wording without treating flexible
  hours or schedules as workplace-location evidence.
- Let users download recognized, sanitized Junior logs directly from
  Settings → Diagnostics without exposing unrelated files.

- Added direct downloads for current and retained reports, including a
  compressed raw-scan ZIP containing every public posting collected in a run.
  Normal HTML and email reports remain summarized instead of rendering
  thousands of unrelated or omitted jobs. New installations retain 10
  successful report runs by default; existing saved retention choices remain
  unchanged.
- Fixed passing a previously saved job by placing its notes, reason, and Pass
  action in one explicit form. The decision now either moves the job to
  Reviewed / passed or shows a useful error, and a bounded privacy-safe action
  log records success or failure without job text, notes, résumé content, URLs,
  or raw exceptions.
- Clarified that a missing job type means full-time, part-time, contract,
  temporary, seasonal, or internship—not remote, hybrid, or on-site—and made
  résumé-supported strengths and possible gaps prominent on review cards.
- Added an occupational-relevance gate before practical eligibility review.
  An allowed location, missing compensation, or other unresolved logistics can
  no longer place unrelated work in Review Jobs without profile-owned title,
  responsibility, or résumé evidence.
- Separated Review Jobs from Reports. Review Jobs now acts as an undecided
  inbox: saved, applied, and passed jobs leave every review group immediately
  and remain resolved after later scans. Reports now contains the current
  read-only HTML and email outputs plus optional retained history.
- Clarified review-card explanations by separating the evidence that caused
  Junior to surface a job from practical facts that still need user review.
- Documented that the latest successful scan is replaceable raw input while
  profile-owned decisions and application records persist independently.
- Fixed systemic location triage so concrete cities, named offices, and
  city/state suffixes in job titles are compared with the profile's allowed
  locations even when the ATS omits a remote, hybrid, or on-site label. Review
  cards now show workplace arrangement and location separately at a glance.
- Fixed the Review Jobs application workflow so saving an application returns
  to its originating review group, removes it from unresolved review results,
  and records today's date as the default last activity.
- Fixed compensation extraction when an ATS double-encodes its job-description
  HTML, including salary ranges separated by an encoded dash.
- Standardized native dropdown styling across the application and expanded the
  profile occupation search field to use the available card width.
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
  handles after commit or rollback. The gate now repeatedly renders the real
  Active Applications and Application History pages, and an extended test
  passed with 500 companies, 500,000 jobs, 50,000 history records, 10,000
  active applications, and five profiles.
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

[Unreleased]: https://github.com/lordegraves/junior/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/lordegraves/junior/releases/tag/v0.2.0
[0.1.0]: https://github.com/lordegraves/junior/releases/tag/v0.1.0
