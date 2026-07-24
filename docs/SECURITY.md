# Security and Privacy

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

The current supported mechanism is an environment-variable reference such as `smtp_password_env`.

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
