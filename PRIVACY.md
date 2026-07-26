# Junior Privacy Notice

Junior is designed to keep job-search data on the computer or server where the
user runs it. Junior does not operate a central user-account service and does
not include product analytics, advertising trackers, crash-reporting services,
or application telemetry.

This notice describes the current implementation. It does not promise planned
features that do not yet exist.

## Data stored locally

Junior stores profiles, résumés, employer settings, collected jobs, review
decisions, applications, reports, settings, schedules, logs, backups, and
runtime files in its configured user-data location. Report storage can include
a compressed raw-scan ZIP containing public job descriptions collected from
configured employers. On a normal Windows
installation, that location is `%LOCALAPPDATA%\JobRadar`.

Email passwords are not stored in Junior's SQLite database or ordinary settings
files. Junior reads them from the operating-system credential manager or from
the environment variable the user configured. The settings file may retain the
non-secret name of that credential reference.

## Employer and recruiting-platform connections

During a scan, Junior connects to the public career sites and recruiting
platforms configured for the user's selected employers. These requests contain
the public source address and the public identifiers, filters, or pagination
values required by that source. The destination can observe the user's IP
address and normal connection details.

Junior does not send the user's résumé, profile, application history, or email
credentials to employer career sites as part of scanning.

## Optional external company lookup

External company lookup is disabled by default and is not required for normal
scans. If the user enables it, Junior may query Bing only after its direct
company-source checks fail.

The exact Bing request contains:

- the submitted public company name;
- the hostname from the submitted public careers address;
- the words `official careers jobs`; and
- `format=rss`.

Bing can also observe the user's IP address and ordinary connection metadata.
Junior does not include profile or résumé information, desired roles,
locations, application history, contact details, database contents, or the path
and query string from the submitted careers address.

External results are suggestions, not authority. Junior independently tests a
candidate with its normal collectors before saving a working company source.
Failed probes, candidate sources, intermediate search results, and external
responses are transient and are not retained as durable application data.

## Email

Email is disabled until the user configures it. Testing a connection sends the
configured SMTP username and password to the selected email provider for
authentication, but it does not send a message.

When the user enables report delivery, Junior sends the configured sender,
recipients, subject, report content, and any selected report attachment through
that SMTP provider. The provider processes that message under its own terms and
privacy policy.

## Update checks

Junior does not download or install updates automatically. When the user clicks
**Check for updates**, Junior requests the latest stable release record from
GitHub's public API. The request identifies the installed Junior version in its
User-Agent. GitHub can observe the user's IP address and normal connection
metadata. No profile, résumé, job, or application data is sent.

## Logs and diagnostics

Junior keeps diagnostic information locally. Scan and collector failures use
sanitized categories and plain-language summaries instead of raw network or
exception text. Startup diagnostics may include Junior's version, the settings
file path, the Python error type, and source-code stack locations. They
deliberately omit exception messages and local variables.

Job-review actions write a bounded local `junior-actions.log`. Its allowlisted
fields record when an action occurred, whether it succeeded, the Junior-managed
job identifier, the screen where it occurred, the prior and requested state,
and a bounded reason code. It does not record job titles, public URLs, user
notes, job descriptions, profile or résumé contents, credentials, raw
exceptions, or environment contents. If the log cannot be written, Junior does
not undo or misreport an otherwise successful user decision.

Junior does not automatically upload logs or diagnostics. A user decides
whether to copy or share a troubleshooting summary. Do not share passwords,
tokens, résumés, profiles, databases, or other private data with a support
request.

## Telemetry

Junior contains no application analytics, usage tracking, advertising tracker,
central learning service, or automatic crash-report uploader.

The Windows desktop build uses the separately installed Microsoft Edge WebView2
Runtime to render Junior's local interface. Junior does not add WebView
telemetry. Microsoft and the operating system control that runtime's servicing
and platform behavior.

## Deletion, backups, and uninstall

User-requested permanent deletion is guarded and creates a safety backup where
the documented workflow requires one. A Junior backup can contain the local
database, profiles, résumés, settings, employer configuration, reports, and
sanitized logs. Credentials are excluded.

Backups remain local unless the user copies them elsewhere. Anyone who obtains a
backup may be able to read sensitive job-search information, so backups should
be stored like private documents.

Uninstalling Junior removes the installed application but intentionally leaves
the user-data directory, schedules, and operating-system credential entries in
place so an update or reinstall does not destroy data. Users who want complete
removal must first make any wanted backup, remove Junior-owned schedules through
Junior, uninstall the application, and then deliberately remove the remaining
user data and credential entry.

## Browser, server, and container operation

The desktop application serves its interface only on the local loopback address.
If a user deliberately runs Junior in browser, server, container, or Kubernetes
mode and exposes it to a network, that operator is responsible for access
controls, transport security, persistent storage, backups, and network logging.

## Questions

Privacy questions may be sent to:

Clayton Graves

claytonmgraves@outlook.com

Do not include passwords, access tokens, résumés, databases, or other private
data in email.
