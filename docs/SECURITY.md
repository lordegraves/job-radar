# Security and Privacy

The user-facing description of Junior's implemented data and network behavior
is the repository-root [PRIVACY.md](../PRIVACY.md). Private vulnerability
reporting and release-authenticity guidance is in
[SECURITY.md](../SECURITY.md).

Repository pushes and pull requests involving `main` or
`feature/productization-foundation` receive an additional automated
reachable-history scan through
`.github/workflows/secret-scanning.yml`. The workflow uses a pinned,
checksum-verified Gitleaks release, redacts findings, retains no report
artifact, and has read-only repository access. GitHub's built-in secret
scanning and push protection remain enabled as a separate defense.

Automated detection reduces risk but does not make a detected credential safe.
If a real secret is ever committed, revoke or rotate it first; deleting a file
or making a later commit does not remove the secret from Git history.

## Local-first model

junior is designed to run under the user's control. It is not a hosted SaaS service.

Private data may include:

- profile and resume content
- target-company configuration
- application and review history
- tracker notes and follow-up dates
- recruiter or contact details
- reports and email previews
- logs containing job-search details
- email configuration and credential references

Private data must remain in user-owned runtime storage and out of source control.

## Credentials

SMTP password values must never be stored in:

- YAML configuration
- SQLite
- reports or email previews
- logs or diagnostics
- bootstrap files
- source code or source control
- wheel, installer, container, or release artifacts
- support bundles

Normal desktop setup stores the password through the operating-system
credential manager. Environment-variable references such as
`smtp_password_env` remain supported for automation, containers, servers, and
compatibility configurations.

A missing credential must not prevent unrelated application startup or local work. Email readiness should report disabled, unavailable, or ready states separately.

## Approved desktop direction

Future desktop setup should use native operating-system credential storage by default:

- Windows Credential Manager
- macOS Keychain
- a Secret Service-compatible Linux keyring where available

Environment variables remain supported for containers, servers, automation, CI, existing configurations, and compatibility use.

Container mode has no built-in network authentication. The supported Compose
example binds only to localhost. A deployment on another interface requires a
separately secured private network or authenticated reverse proxy; the Junior
port must not be exposed directly to the public internet.

Kubernetes uses the same boundary. The supplied Service is private
`ClusterIP`, and Junior still has no built-in web authentication. Any ingress
must provide authentication and a trusted network boundary. The committed
Secret manifest contains no credential value; operators must create Secret
data outside source control. Pin deployed images to an immutable release tag
or digest, and do not place credentials in manifests, images, logs, or the
persistent volume.

junior configuration should store only a credential reference, never the credential value.

Upgrades must preserve references and must not expose, migrate, overwrite, or delete stored credentials automatically.

A lost credential may be replaced, but junior must not display or recover it.

## Protection limits

Operating-system credential storage protects against ordinary file access and accidental inclusion in junior data. It is not absolute protection.

It does not protect against:

- malware running as the user
- administrators or root
- a compromised operating system
- inspection of process memory during credential use
- compromise of the mail provider or account
- deliberate disclosure by the user

These limits must be communicated wherever credentials are saved or managed.

## User-data bootstrap

Bootstrap operations are non-destructive:

- normal setup uses safe packaged starter settings, an empty company list, and starter scoring rules
- profiles, résumés, databases, and live company configuration are not copied automatically
- existing destination files are preserved
- an existing destination database is preserved
- SQLite database copies use SQLite-safe backup behavior
- existing data is imported only when the user supplies an optional source argument
- imported settings containing literal passwords, tokens, API keys, or other secret values are rejected
- credential references such as `smtp_password_env` remain allowed
- private user data is not moved into the repository or included in release packages

## Database safety

Database changes must preserve user data.

Required protections:

- schema migration versions
- foreign-key enforcement
- backup before migration
- transactional tracker/history moves
- profile ownership for Tracker and History records
- atomic failure instead of guessed ownership when legacy application data has no eligible active profile
- safe failure without partial cross-table state

## Network and source behavior

junior scans only configured sources.

Company setup requests only the public company URL supplied by the user and a
bounded set of relevant public links advertised by that site. Name-only input
never invokes an external search provider; it searches the local catalog.
Candidate sources remain transient until Junior independently validates actual
public jobs through a supported collector.

The manual update check sends Junior's installed version to GitHub's public
releases API. It does not download or install software. Junior contains no
application analytics, advertising tracker, central learning service, or
automatic crash-report uploader.

It must not:

- scrape LinkedIn
- bypass login, authentication, anti-bot, or access controls
- broadly crawl the internet
- submit applications
- contact employers automatically

Collectors should use bounded pagination and reasonable request behavior.

## Logs, diagnostics, and reports

Never include secrets in logs, reports, previews, diagnostics, test fixtures, screenshots, or support output.

Before release, inspect artifacts for:

- passwords
- tokens
- API keys
- personal resumes or profiles
- private company lists
- recruiter/contact data
- real SQLite databases
- reports, logs, or email previews
- local settings files

See [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md).
