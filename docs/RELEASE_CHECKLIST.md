# Release Checklist

Use this checklist for every tagged Job Radar release.

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
- [ ] Wheel contains all required packages and templates.
- [ ] Package installs outside the repository.
- [ ] Installed CLI starts.
- [ ] Installed web application renders using temporary user-owned data.
- [ ] Release artifact does not depend on the source tree.

## Database and upgrade safety

- [ ] Existing `v0.1.0`-era database migration is tested when schema changed.
- [ ] Foreign keys remain enabled.
- [ ] Backup-before-migration works.
- [ ] Failed migrations do not leave a partially upgraded database.
- [ ] Tracker/history moves remain atomic.
- [ ] User data remains intact after upgrade.

## Functional browser checks

- [ ] Home dashboard loads and links correctly.
- [ ] Scan page starts and reports progress.
- [ ] Latest HTML report opens.
- [ ] Reports page distinguishes primary outputs from additional files.
- [ ] Active Applications list, detail, add, edit, quick actions, and filters work.
- [ ] Tracker-to-History movement works.
- [ ] Application History list, detail, edit, filters, and restore work.
- [ ] Profile / Resume page loads and resume replacement works.
- [ ] Companies and Settings pages load accurately.
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
- [ ] No real resumes, profiles, or personal settings.
- [ ] No real SQLite databases.
- [ ] No private reports, logs, or email previews.
- [ ] No recruiter/contact details or personal application notes.
- [ ] No local cache, build, or inspection artifacts.
- [ ] SMTP password values are absent from all artifacts.
- [ ] Credential limitations are documented accurately.

## Documentation and support

- [ ] User Guide matches current workflows.
- [ ] Development Guide matches commands and validation.
- [ ] Architecture reflects actual module boundaries.
- [ ] Security document reflects current behavior and future policy.
- [ ] Roadmap separates completed, current, and future work.
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
