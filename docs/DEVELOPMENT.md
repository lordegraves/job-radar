# Development Guide

## Environment

The primary development environment is Windows PowerShell with Python 3.13, while the package supports Python 3.11 and newer.

```powershell
cd C:\dev\job-radar
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pip install ruff
```

The `dev` extra installs pytest and the `build` package required by the packaging tests. Ruff is installed separately because it is a repository validation tool rather than an application dependency.

## Core commands

Show CLI help:

```powershell
python -m job_radar --help
```

Validate configuration:

```powershell
python -m job_radar validate --config config\target-companies.yaml --settings config\settings.yaml --scoring config\scoring.yaml
```

Start the web app:

```powershell
python -m job_radar.web_app --settings config\settings.yaml
```

Run a scan:

```powershell
python -m job_radar scan --config config\target-companies.yaml --settings config\settings.yaml --report reports\target-scan.html --email-preview reports\target-email-preview.txt
```

## Required validation sequence

For normal code changes:

1. Run focused tests for the changed area.
2. Run Ruff.
3. Run the full test suite.
4. Perform relevant manual or live validation.
5. Review documentation impact.
6. Run `git diff --check`.
7. Review the complete diff.
8. Stage explicit files only.
9. Commit and push the explicit branch.

Commands:

```powershell
python -m pytest -q tests\test_relevant_area.py
python -m ruff check job_radar tests
python -m pytest -q tests
git diff --check
git diff
```

Do not use automatic Ruff fixes during review-sensitive refactors. Review each edit explicitly.

## Packaging validation

Packaging behavior is tested in `tests/test_packaging.py`.

The tests verify:

- recursive package discovery
- inclusion of templates, subpackages, and safe bootstrap starter files
- wheel construction from a clean temporary source copy
- installation into an isolated environment outside the repository
- CLI startup from the installed package
- first-time user-data setup without relying on the source repository
- Flask home-page rendering from the installed wheel using temporary user-owned data
- exclusion of private runtime data, profiles, databases, credentials, and live configuration

Run:

```powershell
python -m pytest -q tests\test_packaging.py
```

Build the unsigned Windows desktop bundle:

```powershell
.\scripts\build_windows.ps1
```

The script uses `packaging/windows/junior.spec`, the repository-local
interpreter, and ignored `build/` and `artifacts/` directories. The expected
entry point is `artifacts/windows/Junior/Junior.exe`. The bundle includes
packaged templates, static assets, bootstrap defaults, reference data,
pywebview, and keyring backends. It must never include repository configuration,
profiles, resumes, databases, logs, reports, credentials, or another user's
runtime data.

The packaged executable has been smoke-tested outside Python by using a new
temporary `JOB_RADAR_DATA_DIR`, confirming an HTTP 200 response from the local
interface, and confirming safe starter settings were created. Installer
creation uses Inno Setup:

```powershell
.\scripts\build_windows_installer.ps1
```

The script rebuilds the application bundle first, then compiles
`packaging/windows/junior-installer.iss`. It accepts `-CompilerPath` when
`ISCC.exe` is not in the documented local-tool or standard installation paths.
The generated installer is written to
`artifacts/installer/Junior-Setup-0.1.0.exe`.

Installer validation uses disposable install and user-data directories. It
must verify install, packaged launch, HTTP readiness, uninstall, application
file removal, and preservation of an independent user-data sentinel.

Run the repeatable preservation gate:

```powershell
.\scripts\validate_windows_upgrade.ps1
```

This installs and reinstalls the current setup package, uninstalls it, and
compares SHA-256 hashes for representative settings, company configuration,
profile, résumé, database, report, backup, schedule, and credential-reference
files at every stage.

## Runtime data during development

Default runtime resolution prefers bootstrapped user settings when present and otherwise falls back to repository configuration during development.

The normal bootstrap command uses safe files packaged under `job_radar/bootstrap_defaults/`. Repository profiles, databases, and live company configuration are never automatic bootstrap sources.

Use an isolated root for tests or manual experiments:

```powershell
$env:JOB_RADAR_DATA_DIR = "C:\temp\job-radar-test-data"
```

Remove the override afterward:

```powershell
Remove-Item Env:\JOB_RADAR_DATA_DIR -ErrorAction SilentlyContinue
```

Never modify, display, stage, or distribute private local email settings.

## Database changes

Database work must preserve:

- schema migration versioning
- foreign-key enforcement
- backup-before-migration behavior
- transaction boundaries for tracker/history moves
- existing user data
- compatibility with databases created by `v0.1.0`

Migration changes require focused storage tests, full tests, and a real-database or realistic-copy validation when appropriate.

## Collectors

Collectors remain isolated by source type under `job_radar/collectors/`.

Shared behavior belongs in:

- `collector_http.py`
- `pagination.py`
- `registry.py`

A collector should not implement unbounded pagination or duplicate shared HTTP behavior without a source-specific reason.

## Web application

`job_radar/web_app.py` is the application factory and registration point.

Feature routes live under `job_radar/web_routes/`. Business rules must stay in GUI-neutral services rather than templates or route handlers.

Templates should focus on rendering. Avoid moving tracker, history, scan, report, or configuration business logic into Jinja.

## Reports

The GUI consumes structured report snapshots and shared view models.

HTML is the primary user-facing report format. Markdown scan-output generation has been retired. Do not restore compatibility facades or duplicate Markdown and HTML rendering pipelines.

## Git workflow

- Stage explicit files; do not use `git add .`.
- Review `git diff` before staging.
- Do not repeat a staged diff when the full diff was just reviewed and no files changed afterward.
- Use concise lowercase commit messages.
- Push explicitly:

```powershell
git push origin feature/productization-foundation
```

## Release development

See [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) before tagging or publishing a release.

Junior's update check is intentionally a manual, read-only operation on the
About page. It uses GitHub's latest stable release endpoint, accepts only a
semantic-version tag and an HTTPS link under this repository's release path,
and reports connection or validation problems without raw exceptions. It does
not download an installer, replace application files, run migrations, or write
user data.

The Linux x86-64 package is built natively inside Docker with:

```powershell
.\scripts\build_linux_tarball.ps1
```

`.dockerignore` is an allowlist for this build context. Do not broaden it to
include `config`, `data`, `profiles`, `reports`, `logs`, or other user-owned
paths. The build exports only `Junior-linux-x86_64.tar.gz`. Release validation
must extract that archive in a disposable Linux environment, run
`Junior/junior --help`, exercise install and uninstall with a synthetic home
directory, and verify its user-data sentinels remain unchanged.
