# Release Checklist

Run the automated Windows release gate from the repository root:

```powershell
.\scripts\validate_release.ps1
```

It runs the full test suite, Ruff, whitespace validation, a fresh installer
build, and disposable silent install, repair/upgrade, and uninstall
preservation checks. It never uses the active Junior workspace. A previously
built or separately supplied installer may be checked with
`-SkipInstallerBuild` and optional `-InstallerPath`.

Then validate the packaged Windows and Linux applications without repository
Python, a virtual environment, existing settings, or developer tools:

```powershell
.\scripts\validate_clean_packages.ps1
```

The Windows check launches only the temporary installed `Junior.exe` with an
empty isolated workspace. The Linux check runs only the release archive in a
Python-free Debian container. Both uninstall and verify synthetic user-data
sentinels remain intact. The command builds both packages first; use
`-SkipPackageBuild` only when deliberately validating already-built artifacts.

Finally, perform the release-candidate walkthrough below against the exact
installer intended for publication. This is a normal-user acceptance test, not
a substitute for the automated gates.

Use this checklist for every tagged junior release.

## Release-candidate new-user walkthrough

Use a new temporary `JOB_RADAR_DATA_DIR`. Never point this test at a real
Junior workspace, profile, résumé, database, report directory, or credential
store.

Record the installer filename, SHA-256 checksum, source download page or local
release-artifact location, Junior version, Windows version, and test date.

- [ ] Download or copy the exact release-candidate installer from its intended
  distribution location and verify its published SHA-256 checksum.
- [ ] Install Junior for the current user and launch it from the installed
  shortcut or application executable, without repository Python.
- [ ] Confirm a new empty workspace opens the guided setup welcome page.
- [ ] Create a fictional profile, choose at least one target role, job level,
  employment type, and workplace arrangement, and upload a fictional résumé.
- [ ] Add at least one supported public company source and confirm setup
  validation connects without importing jobs. A broken second source may be
  retained only to verify that Junior explains the warning and still accepts a
  different working source.
- [ ] Review the final setup summary and finish setup.
- [ ] Run the first manual scan and confirm the app-wide completion notice
  reports the job count and any source warnings in plain language.
- [ ] Open the latest HTML report and plain-text email preview from Reports.
- [ ] Add a fictional application to Active Applications, reopen it, and
  verify its company, role, URL, status, outcome, and notes.
- [ ] Use About to run the manual stable-release check. Confirm Junior reports
  the installed version as current or links only to a newer verified release;
  it must not download or install anything automatically.
- [ ] Create a restorable backup from Administration.
- [ ] Change the fictional application after the backup, restore the backup,
  and confirm Junior creates a separate pre-restore safety backup.
- [ ] Exit Junior through Settings, relaunch the installed executable, and
  confirm the profile, résumé, companies, report, and original application
  data survived. The post-backup change must be absent after restore.
- [ ] Run the release installer again as a repair/update and confirm all
  fictional user data remains byte-for-byte intact.
- [ ] Exit Junior cleanly, uninstall it, confirm application files are removed,
  and confirm the isolated user-data directory remains byte-for-byte intact.
- [ ] Remove the verified temporary acceptance workspace after recording the
  result. Never delete a normal Junior user-data directory as cleanup.

Record each step as Pass, Fail, or Not Run. A Fail is a release blocker until
Priority 68 resolves it and this complete walkthrough passes again.

## Release scope

- [ ] Version and release scope are documented.
- [ ] `CHANGELOG.md` has an accurate release entry.
- [ ] No unfinished feature is described as complete.
- [ ] README and linked documentation match the actual CLI and GUI.

## Automated validation

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest -q tests
git diff --check
```

- [ ] Ruff passes.
- [ ] Focused tests for changed areas pass.
- [ ] Full tests pass.
- [ ] Packaging tests pass.
- [ ] `scripts\validate_performance_scale.py` passes at its default long-term
  data volumes.
- [ ] No whitespace errors remain.

## Packaging

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_packaging.py
```

- [ ] Wheel builds from a clean temporary source copy.
- [ ] Wheel contains all required packages, templates, and safe bootstrap starter files.
- [ ] Wheel, source distribution, Windows bundle and installation, Linux archive, and container image include `LICENSE`, `PRIVACY.md`, `SECURITY.md`, `THIRD_PARTY_LICENSES.md`, `dependency-license-report.json`, and required supplemental notices; package metadata and the container label declare `GPL-3.0-only`.
- [ ] `.\.venv\Scripts\python.exe scripts\audit_dependency_licenses.py --check` passes with no blockers.
- [ ] Source distribution builds from a clean temporary source copy.
- [ ] Source distribution includes safe bootstrap starter files.
- [ ] Source distribution excludes private runtime data and local inspection artifacts.
- [ ] Package installs outside the repository.
- [ ] Installed CLI starts.
- [ ] Default bootstrap succeeds from outside the source repository.
- [ ] Default bootstrap creates starter settings, an empty company list, and starter scoring rules.
- [ ] Default bootstrap creates empty profile and data directories without copying a profile, resume, or database.
- [ ] A second bootstrap run preserves existing destination files.
- [ ] Optional migration rejects settings containing literal credentials and allows credential references.
- [ ] Installed web application renders using temporary user-owned data.
- [ ] Installed desktop launcher starts, waits for readiness, opens or reuses the local interface, and reports startup failures safely.
- [ ] `scripts\build_windows.ps1` creates `artifacts\windows\Junior\Junior.exe`.
- [ ] Packaged `Junior.exe` starts without Python, a virtual environment, or a repository checkout.
- [ ] Packaged first run creates only safe starter data under an isolated `JOB_RADAR_DATA_DIR`.
- [ ] Windows bundle contains no profile, resume, database, credential, report, log, or private configuration.
- [ ] `scripts\validate_windows_upgrade.ps1` passes against the release installer.
- [ ] `scripts\build_linux_tarball.ps1` creates `artifacts\linux\Junior-linux-x86_64.tar.gz`.
- [ ] Linux archive starts in a clean Linux environment without Python or the source tree.
- [ ] Linux install/uninstall validation preserves synthetic user data byte for byte.
- [ ] Docker build context excludes configuration, profiles, resumes, databases, reports, logs, and credentials.
- [ ] Container runs as a non-root user and becomes healthy through `/health`.
- [ ] Container recreation or image replacement preserves the mounted synthetic user-data volume.
- [ ] Container stops gracefully and does not expose a development server.
- [ ] Compose binds to localhost unless a separately secured network boundary is documented.
- [ ] Kubernetes manifests render cleanly and use an immutable release image tag or digest.
- [ ] Kubernetes runs one non-root application replica with `Recreate` upgrades and a bound persistent volume.
- [ ] Kubernetes restart validation preserves a synthetic sentinel and `/health` remains ready.
- [ ] Kubernetes scan and backup CronJobs are suspended by default, forbid overlap, and retain bounded job history.
- [ ] A manual Kubernetes backup job creates a verified bundle and scheduled retention never removes manual or pre-change backups.
- [ ] Kubernetes Secret manifests contain no values and the Service remains private unless an authenticated ingress is separately configured.
- [ ] Kubernetes disaster-recovery instructions require backups outside the application persistent volume.
- [ ] Release artifacts do not depend on the source tree.

## Database and upgrade safety

- [ ] Existing `v0.1.0`-era database migration is tested when schema changed.
- [ ] Foreign keys remain enabled.
- [ ] Backup-before-migration works.
- [ ] Failed migrations do not leave a partially upgraded database.
- [ ] Tracker/history moves remain atomic.
- [ ] Tracker and History pages, counts, scans, reports, CLI operations, and direct record URLs remain isolated to the active profile.
- [ ] Existing application records migrate to the active non-archived profile without changing row counts or durable identities.
- [ ] Migration fails atomically when legacy application records exist without an eligible active profile.
- [ ] User data remains intact after upgrade.
- [ ] Installer repair/reinstall preserves every representative user-owned file byte for byte.
- [ ] Uninstall removes application files and preserves every representative user-owned file byte for byte.

## Functional browser checks

- [ ] Home dashboard loads and links correctly.
- [ ] Scan page starts and reports progress.
- [ ] Latest HTML report opens.
- [ ] Reports page shows only the current HTML report and email preview.
- [ ] Active Applications list, detail, add, edit, quick actions, and filters work.
- [ ] Tracker-to-History movement works.
- [ ] Application History list, detail, edit, filters, and restore work.
- [ ] Profile / Resume page loads and resume replacement works.
- [ ] Companies shows the installation-wide catalog and the active profile's selections accurately.
- [ ] Settings loads accurately and remains read-only until its editable workflows are implemented.
- [ ] Desktop-launcher startup and shutdown behavior matches the documented current limitations.
- [ ] Destructive actions require explicit confirmation.
- [ ] Error and empty states are readable.

## Visual and accessibility checks

- [ ] No clipped, overlapping, or off-screen content.
- [ ] Dark-theme contrast is acceptable.
- [ ] Navigation and page widths are consistent.
- [ ] Keyboard focus is visible.
- [ ] Labels and terminology are user-facing and consistent.
- [ ] Responsive behavior is acceptable at common desktop widths.

## Privacy and security audit

Inspect the repository, build context, wheel, release archive, installer, and container context.

- [ ] No passwords, tokens, credentials, or private environment values.
- [ ] No real resumes, profiles, personal settings, or personal scoring/location preferences.
- [ ] No real SQLite databases.
- [ ] No private reports, logs, or email previews.
- [ ] No recruiter/contact details or personal application notes.
- [ ] No local cache, build, or inspection artifacts.
- [ ] SMTP password values and other literal secrets are absent from all artifacts.
- [ ] Packaged company defaults contain no live or private company targets.
- [ ] Credential limitations are documented accurately.
- [ ] The privacy notice matches verified current storage, employer requests,
  optional external lookup, email, logging, telemetry, backup, deletion,
  uninstall, and update-check behavior.
- [ ] Private vulnerability reporting is enabled and its link is usable.

## Documentation and support

- [ ] User Guide matches current workflows.
- [ ] Development Guide matches commands and validation.
- [ ] Architecture reflects actual module boundaries.
- [ ] Security document reflects current behavior and future policy.
- [ ] `docs/ROADMAP.md` remains the authoritative roadmap and separates completed, current, and future work.
- [ ] Recovery and known limitations are documented.

## Git and release

- [ ] Working tree is clean.
- [ ] Intended branch is synchronized with origin.
- [ ] Release commit has been reviewed.
- [ ] Version has been updated where required.
- [ ] Tag points to the intended commit.
- [ ] Published tag is immutable; use a signed annotated tag when the signing
  key and recovery process are available.
- [ ] Tag is pushed explicitly.
- [ ] Release artifacts correspond to the tagged commit.
- [ ] SHA-256 checksums are generated from the exact published artifacts and
  uploaded beside them.
- [ ] Release notes identify the official GitHub release page and do not claim
  Authenticode signing until a protected signing process exists.
- [ ] Post-release smoke test passes.
