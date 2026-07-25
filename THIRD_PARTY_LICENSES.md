# Third-Party Licenses

Junior itself is licensed under GPL-3.0-only. This file records the
third-party software and reference data included in Junior's runtime
distributions. Those components retain their own licenses.

This inventory is generated from the repository-local Python
environment by `scripts/audit_dependency_licenses.py`. The accompanying
`dependency-license-report.json` contains versions and hashes of
installed license files. It is an engineering compliance record, not
legal advice.

## Runtime Python dependencies

| Package | Version | Relationship | License | Status |
|---|---:|---|---|---|
| blinker | 1.9.0 | transitive | MIT | compliant |
| bottle | 0.13.4 | transitive | MIT | compliant |
| certifi | 2026.6.17 | transitive | MPL-2.0 | compliant |
| cffi | 2.1.0 | transitive | MIT-0 | compliant |
| charset-normalizer | 3.4.7 | transitive | MIT | compliant |
| click | 8.4.2 | transitive | BSD-3-Clause | compliant |
| clr_loader | 0.3.1 | transitive | MIT | compliant |
| colorama | 0.4.6 | transitive | BSD-3-Clause | compliant |
| Flask | 3.1.3 | direct | BSD-3-Clause | compliant |
| idna | 3.18 | transitive | BSD-3-Clause | compliant |
| itsdangerous | 2.2.0 | transitive | BSD-3-Clause | compliant |
| jaraco.classes | 3.4.0 | transitive | MIT | compliant |
| jaraco.context | 6.1.2 | transitive | MIT | compliant |
| jaraco.functools | 4.6.0 | transitive | MIT | compliant |
| Jinja2 | 3.1.6 | transitive | BSD-3-Clause | compliant |
| keyring | 25.7.0 | direct | MIT | compliant |
| lxml | 6.1.1 | transitive | BSD-3-Clause | compliant |
| MarkupSafe | 3.0.3 | transitive | BSD-3-Clause | compliant |
| more-itertools | 11.1.0 | transitive | MIT | compliant |
| proxy_tools | 0.1.0 | transitive | BSD-2-Clause | needs review |
| pycparser | 3.0 | transitive | BSD-3-Clause | compliant |
| pypdf | 6.14.2 | direct | BSD-3-Clause | compliant |
| python-docx | 1.2.0 | direct | MIT | compliant |
| pythonnet | 3.1.0 | transitive | MIT | compliant |
| pywebview | 6.2.1 | direct | BSD-3-Clause | compliant |
| pywin32-ctypes | 0.2.3 | transitive | BSD-3-Clause | compliant |
| PyYAML | 6.0.3 | direct | MIT | compliant |
| requests | 2.34.2 | direct | Apache-2.0 | compliant |
| typing_extensions | 4.16.0 | transitive | PSF-2.0 | compliant |
| urllib3 | 2.7.0 | transitive | MIT | compliant |
| Werkzeug | 3.1.8 | transitive | BSD-3-Clause | compliant |

The machine-readable report records where each dependency is used,
the authoritative license source and hash, bundled artifacts,
required notices, source obligations, GPL compatibility, and notes.
A **blocker** must be resolved before distribution. **Needs review**
is compatible but has an upstream metadata discrepancy or another
issue that should be tracked before the stable release.

## Bundled platform components

### CPython runtime

- Version: 3.13.12
- License: PSF-2.0
- Source and terms: https://docs.python.org/3/license.html
- Packaging: Windows standalone application and installer, Linux standalone archive
- Status: compliant

### Microsoft Edge WebView2 loader assemblies

- Version: resolved by pywebview 6.2.1
- License: LicenseRef-Microsoft-WebView2
- Source and terms: https://www.nuget.org/packages/Microsoft.Web.WebView2/
- Packaging: Windows standalone application and installer
- Status: compliant

### OpenSSL runtime libraries

- Version: 3.0.18
- License: Apache-2.0
- Source and terms: https://www.openssl.org/source/license.html
- Packaging: Windows standalone application and installer, Linux standalone archive
- Status: compliant

### SQLite

- Version: 3.50.4
- License: LicenseRef-SQLite-Public-Domain
- Source and terms: https://www.sqlite.org/copyright.html
- Packaging: Windows standalone application and installer, Linux standalone archive
- Status: compliant

## Reference data

### O*NET 30.3 Database

- Version: 30.3
- License/status: CC-BY-4.0
- Source: https://www.onetcenter.org/database.html
- Junior use: Occupation titles and descriptions used for role suggestions.
- Modifications: Junior extracts and repackages only the fields needed for local occupation suggestions and role discovery.
- Status: compliant
- No endorsement by the source agency or organization is implied.

### U.S. Census Bureau Gazetteer Files and population estimates

- Version: 2025
- License/status: LicenseRef-US-Government-Public-Domain
- Source: https://www.census.gov/geographies/reference-files/time-series/geo/gazetteer-files.html
- Junior use: U.S. place, ZIP-area, radius, and display-prioritization data.
- Modifications: Junior reduces and repackages the source data for local location normalization and commute-area previews.
- Status: compliant
- No endorsement by the source agency or organization is implied.

## Build tools not redistributed as application components

- PyInstaller builds standalone bundles and uses its documented
  bootloader exception. It is not installed as a Junior runtime
  dependency.
- Inno Setup builds the Windows installer. The compiler is not
  distributed with Junior.
- pytest, Ruff, build, and setuptools support development and
  packaging and are not user-facing Junior runtime dependencies.

## Repeat the audit

From the repository root:

```powershell
.\.venv\Scripts\python.exe scripts\audit_dependency_licenses.py --check
```

To intentionally regenerate the committed report and notice after a
dependency update:

```powershell
.\.venv\Scripts\python.exe scripts\audit_dependency_licenses.py --write
```
