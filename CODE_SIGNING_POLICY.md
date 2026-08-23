# Code Signing Policy

## Current status

Junior is applying to the SignPath Foundation open-source code-signing program.
RC6 Build 1.26 is not Authenticode-signed unless its GitHub release explicitly
identifies a signed artifact and publishes the corresponding verification
details. Until then, users should download Junior only from the official GitHub
release page and verify the published SHA-256 checksum.

Free code signing provided by [SignPath.io](https://signpath.io/), certificate
by [SignPath Foundation](https://signpath.org/).

## Official project and downloads

- Source: <https://github.com/lordegraves/junior>
- Releases: <https://github.com/lordegraves/junior/releases>
- License: GPL-3.0-only
- Privacy notice: [`PRIVACY.md`](PRIVACY.md)
- Security reporting: [`SECURITY.md`](SECURITY.md)

## What Junior signs

The Junior project signs only release executables and installers built from
Junior-owned source in this public repository. A release may bundle reviewed
third-party runtime components under their own licenses; Junior does not claim
authorship of those components and does not sign unrelated upstream binaries
as separate products.

The signed artifact must be produced on a GitHub-hosted runner from the public
release commit. The workflow uploads the unsigned installer as a GitHub Actions
artifact and submits that exact artifact to SignPath. SignPath's protected
policy and manual approval determine whether a signed artifact is returned.
Local developer builds are never submitted as release artifacts.

## Roles and approval

- Committer and reviewer: Clayton Graves (`@lordegraves`)
- Signing request approver: Clayton Graves (`@lordegraves`)

The maintainer uses multi-factor authentication for privileged accounts and
reviews the source commit, successful validation runs, artifact identity,
version metadata, and release notes before approving a signing request. A
failed or unexpected build is not approved by repeatedly rerunning it.

## Release identity and traceability

Signed release metadata must identify Junior, its public repository, the exact
version and RC build, and the originating Git commit. Published tags are
immutable. Every release continues to include a SHA-256 checksum; the checksum
is an integrity aid and not a substitute for Authenticode signing.

If a key, credential, workflow, dependency, or artifact is suspected of being
compromised, signing stops until the incident is investigated. The maintainer
will revoke or replace affected credentials or certificates through SignPath,
publish corrected artifacts when appropriate, and disclose material impact in
the security advisory and release notes.

## Privacy and network behavior

Junior has no product telemetry or automatic crash uploader. Its documented
network connections are public employer and recruiting-platform requests,
user-configured SMTP and USAJOBS connections, optional user-configured OpenAI
explanations, and a user-initiated GitHub update check or installer download.
Junior does not automatically upload profiles, resumes, databases, logs, or
diagnostic packages. The complete current disclosure is in
[`PRIVACY.md`](PRIVACY.md).
