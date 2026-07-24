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

Use this checklist for every tagged junior release.

## Release scope

- [ ] Version and release scope are documented.
- [ ] `CHANGELOG.md` has an accurate release entry.
- [ ] No unfinished feature is described as complete.
- [ ] README and linked documentation match the actual CLI and GUI.

## Automated validation

```powershell
python -m ruff check job_radar tests
python -m pytest -q tests
git diff --check
```

- [ ] Ruff passes.
- [ ] Focused tests for changed areas pass.
- [ ] Full tests pass.
- [ ] Packaging tests pass.
- [ ] No whitespace errors remain.

## Packaging

```powershell
python -m pytest -q tests\test_packaging.py
```

- [ ] Wheel builds from a clean temporary source copy.
- [ ] Wheel contains all required packages, templates, and safe bootstrap starter files.
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
- [ ] Tag is pushed explicitly.
- [ ] Release artifacts correspond to the tagged commit.
- [ ] Post-release smoke test passes.
