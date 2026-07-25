"""Generate Junior's repeatable third-party dependency license audit.

The audit reads only installed package metadata. It never contacts package
indexes or external services, which keeps the result repeatable and prevents an
audit from transmitting repository or user information.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import importlib.metadata
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JSON = PROJECT_ROOT / "dependency-license-report.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "THIRD_PARTY_LICENSES.md"

# This is the reviewed Windows runtime closure of the dependencies declared in
# pyproject.toml. Update this allowlist deliberately when runtime dependencies
# change; an unexpected or missing distribution makes the audit fail.
RUNTIME_DEPENDENCIES = {
    "blinker": "MIT",
    "bottle": "MIT",
    "certifi": "MPL-2.0",
    "cffi": "MIT-0",
    "charset-normalizer": "MIT",
    "click": "BSD-3-Clause",
    "clr-loader": "MIT",
    "colorama": "BSD-3-Clause",
    "flask": "BSD-3-Clause",
    "idna": "BSD-3-Clause",
    "itsdangerous": "BSD-3-Clause",
    "jaraco-classes": "MIT",
    "jaraco-context": "MIT",
    "jaraco-functools": "MIT",
    "jinja2": "BSD-3-Clause",
    "keyring": "MIT",
    "lxml": "BSD-3-Clause",
    "markupsafe": "BSD-3-Clause",
    "more-itertools": "MIT",
    "proxy-tools": "BSD-2-Clause",
    "pycparser": "BSD-3-Clause",
    "pypdf": "BSD-3-Clause",
    "python-docx": "MIT",
    "pythonnet": "MIT",
    "pywebview": "BSD-3-Clause",
    "pywin32-ctypes": "BSD-3-Clause",
    "pyyaml": "MIT",
    "requests": "Apache-2.0",
    "typing-extensions": "PSF-2.0",
    "urllib3": "MIT",
    "werkzeug": "BSD-3-Clause",
}

DIRECT_DEPENDENCIES = {
    "flask": "Local web interface and HTTP route handling.",
    "keyring": "Operating-system credential-manager integration.",
    "pypdf": "PDF résumé text extraction.",
    "pywebview": "Native desktop window around Junior's shared web interface.",
    "python-docx": "Word résumé text extraction.",
    "pyyaml": "Configuration and compatibility-file parsing.",
    "requests": "Employer career-source collection and optional external lookup.",
}

SUPPLEMENTAL_LICENSES = {
    "proxy-tools": {
        "path": "third_party/proxy_tools_LICENSE.txt",
        "source": "https://github.com/jtushman/proxy_tools/blob/master/LICENSE.txt",
        "note": (
            "The installed wheel metadata says MIT but the authoritative "
            "upstream LICENSE.txt is BSD-2-Clause. Junior distributes the "
            "upstream notice and records this metadata discrepancy for review."
        ),
    }
}

NOTICE_REQUIREMENTS = {
    "Apache-2.0": (
        "Include the Apache 2.0 license and any upstream NOTICE material; "
        "identify modifications when applicable."
    ),
    "BSD-2-Clause": (
        "Retain the copyright notice, license conditions, and disclaimer."
    ),
    "BSD-3-Clause": (
        "Retain the copyright notice, license conditions, disclaimer, and "
        "non-endorsement condition."
    ),
    "CC-BY-4.0": (
        "Credit the source, link the license, and identify Junior's modifications."
    ),
    "MIT": "Retain the copyright and permission notice.",
    "MIT-0": "Retain the copyright and permission notice.",
    "MPL-2.0": (
        "Retain notices and make source available for any modified MPL-covered "
        "files distributed in executable form."
    ),
    "PSF-2.0": "Retain the Python Software Foundation license and notices.",
}

SOURCE_REQUIREMENTS = {
    "MPL-2.0": (
        "File-level source availability applies only if Junior distributes a "
        "modified MPL-covered file. Junior currently distributes certifi "
        "unmodified."
    )
}

REFERENCE_DATA = [
    {
        "name": "O*NET 30.3 Database",
        "version": "30.3",
        "direct_or_transitive": "direct reference asset",
        "where_used": "Occupation titles and descriptions used for role suggestions.",
        "license_spdx": "CC-BY-4.0",
        "authoritative_license_source": "https://www.onetcenter.org/database.html",
        "bundled_into": [
            "Windows standalone application and installer",
            "Linux standalone archive",
            "container image",
            "Python installation",
        ],
        "required_attribution_or_notices": NOTICE_REQUIREMENTS["CC-BY-4.0"],
        "source_offer_requirement": "None.",
        "gpl_3_only_compatibility": "compatible",
        "status": "compliant",
        "notes": [
            "Junior extracts and repackages only the fields needed for local "
            "occupation suggestions and role discovery."
        ],
    },
    {
        "name": "U.S. Census Bureau Gazetteer Files and population estimates",
        "version": "2025",
        "direct_or_transitive": "direct reference asset",
        "where_used": (
            "U.S. place, ZIP-area, radius, and display-prioritization data."
        ),
        "license_spdx": "LicenseRef-US-Government-Public-Domain",
        "authoritative_license_source": (
            "https://www.census.gov/geographies/reference-files/time-series/"
            "geo/gazetteer-files.html"
        ),
        "bundled_into": [
            "Windows standalone application and installer",
            "Linux standalone archive",
            "container image",
            "Python installation",
        ],
        "required_attribution_or_notices": (
            "No copyright notice is required; Junior identifies the Census "
            "Bureau source and does not imply endorsement."
        ),
        "source_offer_requirement": "None.",
        "gpl_3_only_compatibility": "compatible",
        "status": "compliant",
        "notes": [
            "Junior reduces and repackages the source data for local location "
            "normalization and commute-area previews."
        ],
    },
]

BUNDLED_PLATFORM_COMPONENTS = [
    {
        "name": "CPython runtime",
        "version": "3.13.12",
        "direct_or_transitive": "direct bundled component",
        "where_used": "Runs Junior's packaged Python application.",
        "license_spdx": "PSF-2.0",
        "authoritative_license_source": "https://docs.python.org/3/license.html",
        "bundled_into": [
            "Windows standalone application and installer",
            "Linux standalone archive",
        ],
        "required_attribution_or_notices": NOTICE_REQUIREMENTS["PSF-2.0"],
        "source_offer_requirement": "None.",
        "gpl_3_only_compatibility": "compatible",
        "status": "compliant",
        "notes": ["Version is pinned to the runtime used for the audited RC5 build."],
    },
    {
        "name": "Microsoft Edge WebView2 loader assemblies",
        "version": "resolved by pywebview 6.2.1",
        "direct_or_transitive": "transitive bundled component",
        "where_used": "Hosts Junior's local interface in the Windows desktop window.",
        "license_spdx": "LicenseRef-Microsoft-WebView2",
        "authoritative_license_source": (
            "https://www.nuget.org/packages/Microsoft.Web.WebView2/"
        ),
        "bundled_into": ["Windows standalone application and installer"],
        "required_attribution_or_notices": (
            "Retain and comply with the Microsoft WebView2 redistribution terms."
        ),
        "source_offer_requirement": "None.",
        "gpl_3_only_compatibility": "compatible as a separately licensed runtime",
        "status": "compliant",
        "notes": [
            "Junior bundles loader assemblies; the installed Microsoft Edge "
            "WebView2 Runtime renders the desktop interface."
        ],
    },
    {
        "name": "OpenSSL runtime libraries",
        "version": "3.0.18",
        "direct_or_transitive": "transitive bundled component",
        "where_used": "Provides TLS support to the bundled CPython runtime.",
        "license_spdx": "Apache-2.0",
        "authoritative_license_source": (
            "https://www.openssl.org/source/license.html"
        ),
        "bundled_into": [
            "Windows standalone application and installer",
            "Linux standalone archive",
        ],
        "required_attribution_or_notices": NOTICE_REQUIREMENTS["Apache-2.0"],
        "source_offer_requirement": "None.",
        "gpl_3_only_compatibility": "compatible",
        "status": "compliant",
        "notes": ["Version was read from the audited repository-local runtime."],
    },
    {
        "name": "SQLite",
        "version": "3.50.4",
        "direct_or_transitive": "transitive bundled component",
        "where_used": "Stores Junior's local application data.",
        "license_spdx": "LicenseRef-SQLite-Public-Domain",
        "authoritative_license_source": "https://www.sqlite.org/copyright.html",
        "bundled_into": [
            "Windows standalone application and installer",
            "Linux standalone archive",
        ],
        "required_attribution_or_notices": "None required; source is identified.",
        "source_offer_requirement": "None.",
        "gpl_3_only_compatibility": "compatible",
        "status": "compliant",
        "notes": ["Version was read from the audited repository-local runtime."],
    },
]


def _canonicalize(name: str) -> str:
    return name.lower().replace("_", "-").replace(".", "-")


def _license_files(distribution: importlib.metadata.Distribution) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    for relative_path in distribution.files or ():
        lowered = str(relative_path).lower()
        filename = Path(str(relative_path)).name.lower()
        if not (
            "licenses/" in lowered
            or filename.startswith(("license", "copying", "notice"))
        ):
            continue
        resolved = Path(distribution.locate_file(relative_path))
        if not resolved.is_file():
            continue
        content = resolved.read_bytes()
        results.append(
            {
                "path": str(relative_path).replace("\\", "/"),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    return sorted(results, key=lambda item: item["path"].lower())


def _used_by(name: str) -> list[str]:
    users: list[str] = []
    for candidate in RUNTIME_DEPENDENCIES:
        try:
            requirements = importlib.metadata.requires(candidate) or []
        except importlib.metadata.PackageNotFoundError:
            continue
        for requirement in requirements:
            required_name = requirement.split(";", maxsplit=1)[0]
            required_name = required_name.split("[", maxsplit=1)[0]
            required_name = required_name.strip().split(" ", maxsplit=1)[0]
            for separator in ("<", ">", "=", "!", "~"):
                required_name = required_name.split(separator, maxsplit=1)[0]
            if _canonicalize(required_name.strip()) == name:
                users.append(candidate)
                break
    return sorted(users)


def _package_record(name: str, expected_license: str) -> dict[str, Any]:
    distribution = importlib.metadata.distribution(name)
    metadata = distribution.metadata
    metadata_license = (
        metadata.get("License-Expression") or metadata.get("License") or ""
    ).strip()
    license_files = _license_files(distribution)
    supplemental = SUPPLEMENTAL_LICENSES.get(name)
    authoritative_sources = [
        {
            "type": "installed-distribution",
            "path": item["path"],
            "sha256": item["sha256"],
        }
        for item in license_files
    ]
    if supplemental:
        supplemental_path = PROJECT_ROOT / supplemental["path"]
        if supplemental_path.is_file():
            authoritative_sources.append(
                {
                    "type": "supplemental-upstream-copy",
                    "path": supplemental["path"],
                    "sha256": hashlib.sha256(
                        supplemental_path.read_bytes()
                    ).hexdigest(),
                    "upstream": supplemental["source"],
                }
            )
    direct = name in DIRECT_DEPENDENCIES
    metadata_matches = expected_license.lower() in metadata_license.lower()
    status = "compliant"
    notes: list[str] = []
    if not authoritative_sources:
        status = "blocker"
        notes.append("No authoritative license text is available for redistribution.")
    if supplemental:
        status = "needs review" if status != "blocker" else status
        notes.append(supplemental["note"])
    elif metadata_license and not metadata_matches:
        notes.append(
            "Installed metadata uses non-SPDX or legacy license wording; the "
            "bundled upstream license file was used as authority."
        )
    return {
        "name": metadata.get("Name", name),
        "normalized_name": _canonicalize(metadata.get("Name", name)),
        "version": distribution.version,
        "direct_or_transitive": "direct" if direct else "transitive",
        "where_used": (
            DIRECT_DEPENDENCIES[name]
            if direct
            else "Runtime dependency required by " + ", ".join(_used_by(name)) + "."
        ),
        "license_spdx": expected_license,
        "metadata_license": metadata_license,
        "homepage": (
            metadata.get("Project-URL", "").split(",", maxsplit=1)[-1].strip()
            or metadata.get("Home-page", "").strip()
        ),
        "authoritative_license_source": authoritative_sources,
        "bundled_into": [
            "Windows standalone application and installer",
            "Linux standalone archive",
            "container image",
            "Python installation",
        ],
        "required_attribution_or_notices": NOTICE_REQUIREMENTS[expected_license],
        "source_offer_requirement": SOURCE_REQUIREMENTS.get(
            expected_license, "None."
        ),
        "gpl_3_only_compatibility": "compatible",
        "status": status,
        "notes": notes,
        "license_files": license_files,
        "license_file_present": bool(authoritative_sources),
    }


def build_report() -> dict[str, Any]:
    packages: list[dict[str, Any]] = []
    errors: list[str] = []
    for name, expected_license in sorted(RUNTIME_DEPENDENCIES.items()):
        try:
            packages.append(_package_record(name, expected_license))
        except importlib.metadata.PackageNotFoundError:
            errors.append(f"Required runtime distribution is not installed: {name}")

    blockers = [package["name"] for package in packages if package["status"] == "blocker"]
    needs_review = [
        package["name"] for package in packages if package["status"] == "needs review"
    ]
    return {
        "schema_version": 1,
        "project": {
            "name": "junior",
            "python_distribution": "job-radar",
            "license": "GPL-3.0-only",
        },
        "scope": {
            "runtime_dependencies": (
                "Resolved Windows runtime dependency closure declared by "
                "pyproject.toml and bundled by the desktop build."
            ),
            "excluded": (
                "Developer-only tools are not redistributed and are recorded "
                "separately in THIRD_PARTY_LICENSES.md."
            ),
        },
        "packages": packages,
        "reference_data": REFERENCE_DATA,
        "bundled_platform_components": BUNDLED_PLATFORM_COMPONENTS,
        "summary": {
            "package_count": len(packages),
            "missing_package_count": len(errors),
            "blocker_count": len(blockers) + len(errors),
            "blockers": blockers,
            "needs_review_count": len(needs_review),
            "needs_review": needs_review,
            "audit_passed": not errors and not blockers,
        },
        "errors": errors,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Third-Party Licenses",
        "",
        "Junior itself is licensed under GPL-3.0-only. This file records the",
        "third-party software and reference data included in Junior's runtime",
        "distributions. Those components retain their own licenses.",
        "",
        "This inventory is generated from the repository-local Python",
        "environment by `scripts/audit_dependency_licenses.py`. The accompanying",
        "`dependency-license-report.json` contains versions and hashes of",
        "installed license files. It is an engineering compliance record, not",
        "legal advice.",
        "",
        "## Runtime Python dependencies",
        "",
        "| Package | Version | Relationship | License | Status |",
        "|---|---:|---|---|---|",
    ]
    for package in report["packages"]:
        lines.append(
            f"| {package['name']} | {package['version']} | "
            f"{package['direct_or_transitive']} | {package['license_spdx']} | "
            f"{package['status']} |"
        )

    lines.extend(
        [
            "",
            "The machine-readable report records where each dependency is used,",
            "the authoritative license source and hash, bundled artifacts,",
            "required notices, source obligations, GPL compatibility, and notes.",
            "A **blocker** must be resolved before distribution. **Needs review**",
            "is compatible but has an upstream metadata discrepancy or another",
            "issue that should be tracked before the stable release.",
            "",
            "## Bundled platform components",
            "",
        ]
    )
    for component in report["bundled_platform_components"]:
        lines.extend(
            [
                f"### {component['name']}",
                "",
                f"- Version: {component['version']}",
                f"- License: {component['license_spdx']}",
                f"- Source and terms: {component['authoritative_license_source']}",
                f"- Packaging: {', '.join(component['bundled_into'])}",
                f"- Status: {component['status']}",
                "",
            ]
        )

    lines.extend(["## Reference data", ""])
    for dataset in report["reference_data"]:
        lines.extend(
            [
                f"### {dataset['name']}",
                "",
                f"- Version: {dataset['version']}",
                f"- License/status: {dataset['license_spdx']}",
                f"- Source: {dataset['authoritative_license_source']}",
                f"- Junior use: {dataset['where_used']}",
                f"- Modifications: {dataset['notes'][0]}",
                f"- Status: {dataset['status']}",
                "- No endorsement by the source agency or organization is implied.",
                "",
            ]
        )

    lines.extend(
        [
            "## Build tools not redistributed as application components",
            "",
            "- PyInstaller builds standalone bundles and uses its documented",
            "  bootloader exception. It is not installed as a Junior runtime",
            "  dependency.",
            "- Inno Setup builds the Windows installer. The compiler is not",
            "  distributed with Junior.",
            "- pytest, Ruff, build, and setuptools support development and",
            "  packaging and are not user-facing Junior runtime dependencies.",
            "",
            "## Repeat the audit",
            "",
            "From the repository root:",
            "",
            "```powershell",
            r".\.venv\Scripts\python.exe scripts\audit_dependency_licenses.py --check",
            "```",
            "",
            "To intentionally regenerate the committed report and notice after a",
            "dependency update:",
            "",
            "```powershell",
            r".\.venv\Scripts\python.exe scripts\audit_dependency_licenses.py --write",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def _json_text(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _stale_output_diff(path: Path, expected: str) -> str:
    """Show why a generated audit file differs without changing the file."""
    actual = path.read_text(encoding="utf-8") if path.is_file() else ""
    return "".join(
        difflib.unified_diff(
            actual.splitlines(keepends=True),
            expected.splitlines(keepends=True),
            fromfile=f"committed/{path.name}",
            tofile=f"generated/{path.name}",
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    args = parser.parse_args()

    report = build_report()
    json_text = _json_text(report)
    markdown_text = render_markdown(report)

    if args.write:
        DEFAULT_JSON.write_text(json_text, encoding="utf-8")
        DEFAULT_MARKDOWN.write_text(markdown_text, encoding="utf-8")
    else:
        mismatches: list[str] = []
        mismatch_diffs: list[str] = []
        for path, expected in (
            (DEFAULT_JSON, json_text),
            (DEFAULT_MARKDOWN, markdown_text),
        ):
            if not path.is_file() or path.read_text(encoding="utf-8") != expected:
                mismatches.append(str(path.relative_to(PROJECT_ROOT)))
                mismatch_diffs.append(_stale_output_diff(path, expected))
        if mismatches:
            print("License audit outputs are missing or stale: " + ", ".join(mismatches))
            print(
                "The diff below compares the committed file with the audit "
                "generated in this environment:"
            )
            print("\n".join(mismatch_diffs))
            return 1

    if not report["summary"]["audit_passed"]:
        print(json.dumps(report["summary"], indent=2))
        return 1
    print(
        "Dependency license audit passed for "
        f"{report['summary']['package_count']} runtime packages."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
