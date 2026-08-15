# Security Policy

## Supported versions

Junior is currently field-test software. Security fixes are applied to the
newest published release candidate and, after the stable release, to the newest
stable release. Older release candidates may not receive separate fixes.

## Report a vulnerability privately

Do not open a public issue for a suspected vulnerability.

Use GitHub's private vulnerability reporting form:

https://github.com/lordegraves/junior/security/advisories/new

If that form is unavailable, contact:

Clayton Graves

claytonmgraves@outlook.com

Include the Junior version, operating system, the affected feature, safe
reproduction steps, and the security impact. Do not send a real résumé,
database, password, access token, credential, or other private user data.
Create a minimal synthetic example when evidence is required.

Please allow reasonable time to confirm the report, prepare a fix, and publish
coordinated release guidance before public disclosure.

## Release authenticity

Official downloads are published only from:

https://github.com/lordegraves/junior/releases

Every release must publish a SHA-256 checksum file. Verify the installer against
that checksum before running it. Unsigned field-test installers can trigger a
Windows SmartScreen warning; verify the filename, release page, and checksum
before choosing to continue.

Published release tags and history are not rewritten. Future stable releases
should use signed annotated tags once the maintainer's signing key and recovery
process are established. Windows Authenticode signing is being prepared through
the SignPath Foundation open-source program. It must not be claimed until the
project is accepted and a release artifact completes the protected signing
process. See [`CODE_SIGNING_POLICY.md`](CODE_SIGNING_POLICY.md) for the public
policy and current status.

## Security boundaries

Junior is local-first, but it is not a security boundary against another person
who controls the same operating-system account. Administration confirmation is
an accident-prevention control, not a password.

Browser, server, container, and Kubernetes operators are responsible for
network access controls, TLS termination, host security, storage permissions,
and independent backups.
