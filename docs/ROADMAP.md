# Product Roadmap

This document is a high-level public summary of product direction. It does not replace the protected session execution plan or authorize changes to established priority numbers, task wording, sequencing, or status values.

## Product goal

Job Radar should become a configurable local-first job-search operations application that a non-developer can install, launch, configure, and use without editing source files or YAML by hand.

The product is not intended to become:

- a hosted job board
- an automatic application bot
- an automatic recruiter-outreach system
- a LinkedIn scraper
- a broad web crawler

The projected full-product target remains September 30, 2026. Milestone quality and dependency order take precedence over the date.

## Completed baseline

### MVP — completed July 14, 2026

The single-user local MVP established:

- configured-company scanning
- scoring and recommendation output
- local HTML reports and email previews
- Active Applications and Application History
- follow-up workflow
- dashboard attention queues
- resume upload and profile visibility
- read-only Companies and Settings pages
- guarded email behavior
- a local Flask GUI

### Productization foundations — in progress

Completed foundation work includes:

- database migration integrity and backups
- atomic tracker/history moves
- shared scan lifecycle and durable progress
- structured scoring evidence and report snapshots
- route and reporting modularization
- user-owned runtime paths and safe packaged bootstrap defaults
- optional non-destructive migration of existing settings, profiles, and databases
- bootstrap rejection of literal credential values
- collector HTTP consolidation
- clean wheel, source-distribution, installed-bootstrap, and installed-rendering tests
- retirement of Markdown scan output
- retirement of the spreadsheet import bridge

## Remaining productization areas

### Documentation and release discipline

- replace the monolithic README with focused documentation
- maintain a changelog
- add repeatable release checks
- document user, developer, architecture, security, recovery, and operations workflows
- audit all current instructions against actual CLI behavior

### Artifact taxonomy and retention

- define user-facing reports versus diagnostics and support artifacts
- make HTML and structured data the primary report path
- define retention and rotation rules
- expose retention choices through Settings
- keep old or developer-only files out of normal report navigation

### Backup, export, and recovery

- user-facing backup of SQLite and configuration
- restore validation
- export of tracker/history data
- safe upgrade and migration recovery
- clear separation of application files and personal data

### Editable configuration

- profile creation and switching
- preferences and scoring setup
- target-company add/edit/disable workflows
- source validation and targeted source testing
- GUI-managed email configuration
- no normal-use dependency on hand-edited YAML

### Scheduling and email

- scheduled scans using the shared scan service
- Windows Task Scheduler integration
- Linux systemd user timer support
- safe schedule validation and failure reporting
- explicit GUI send action
- native credential storage for desktop installations
- environment-variable fallback for service and automation modes

### First-run experience

- guided setup
- build on the completed safe user-data initialization foundation
- profile and resume setup
- company and preference setup
- email readiness
- first scan
- clear recovery from incomplete setup

### Packaging and launch

- friendly local launcher
- normal browser opening behavior
- Windows executable
- Windows installer
- Linux tarball distribution
- container/server deployment
- unattended service operation
- upgrade and uninstall behavior
- signed/reproducible release process where practical

Installer work begins only after the application satisfies distribution-readiness exit criteria.

### Final polish and acceptance

- full functional browser validation
- full visual review
- accessibility and terminology review
- privacy and artifact audit
- clean-install acceptance
- upgrade-from-previous-release acceptance
- backup and restore acceptance
- end-to-end first-run acceptance

## Later product growth

After the product is installable and stable:

- richer company knowledge and contacts
- multiple profiles for different users or job searches
- profile-specific resumes, companies, and scoring
- targeted company rescans
- interview preparation and research workflows
- optional mobile companion application

LLM-assisted analysis may be considered later, but it must not replace transparent rules, user control, or local data protections.
