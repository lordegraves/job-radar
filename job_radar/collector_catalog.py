"""Describe the job-platform collectors built into every Junior installation."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CollectorCapability:
    """Present one shipped collector without creating an employer record."""

    source_type: str
    name: str
    setup: str
    description: str


COLLECTOR_CAPABILITIES = (
    CollectorCapability(
        "greenhouse",
        "Greenhouse",
        "Automatic from careers URL",
        "Scans public Greenhouse job boards.",
    ),
    CollectorCapability(
        "lever",
        "Lever",
        "Automatic from careers URL",
        "Scans public Lever job boards.",
    ),
    CollectorCapability(
        "ashby",
        "Ashby",
        "Automatic from careers URL",
        "Scans public Ashby job boards.",
    ),
    CollectorCapability(
        "adp",
        "ADP Workforce Now",
        "Automatic from complete ADP URL",
        "Scans public ADP Workforce Now recruiting portals.",
    ),
    CollectorCapability(
        "recruitee",
        "Recruitee",
        "Automatic from careers URL",
        "Scans public Recruitee career sites through their official public API.",
    ),
    CollectorCapability(
        "workday",
        "Workday",
        "Additional setup may be required",
        "Scans configured public Workday career sites.",
    ),
    CollectorCapability(
        "icims",
        "iCIMS",
        "Additional setup may be required",
        "Scans configured public iCIMS career sites.",
    ),
    CollectorCapability(
        "oracle_hcm",
        "Oracle Cloud HCM",
        "Additional setup may be required",
        "Scans configured Oracle Cloud recruiting sites.",
    ),
    CollectorCapability(
        "smartrecruiters",
        "SmartRecruiters",
        "Additional setup may be required",
        "Scans configured public SmartRecruiters job sites.",
    ),
    CollectorCapability(
        "selectminds",
        "SelectMinds",
        "Additional setup may be required",
        "Scans configured SelectMinds career sites.",
    ),
    CollectorCapability(
        "phenom",
        "Phenom",
        "Additional setup may be required",
        "Scans configured Phenom-powered career sites.",
    ),
    CollectorCapability(
        "dayforce",
        "Dayforce",
        "Additional setup may be required",
        "Scans configured Dayforce career sites.",
    ),
    CollectorCapability(
        "rippling",
        "Rippling",
        "Additional setup may be required",
        "Scans configured Rippling job boards.",
    ),
    CollectorCapability(
        "schoolspring",
        "SchoolSpring",
        "Additional setup may be required",
        "Scans configured SchoolSpring education listings.",
    ),
    CollectorCapability(
        "jibe",
        "Jibe",
        "Additional setup may be required",
        "Scans configured Jibe-powered career sites.",
    ),
    CollectorCapability(
        "jobsyn",
        "JobSync",
        "Additional setup may be required",
        "Scans configured JobSync-powered listings.",
    ),
    CollectorCapability(
        "activate",
        "Activate",
        "Additional setup may be required",
        "Scans configured Activate-powered career sites.",
    ),
    CollectorCapability(
        "weka",
        "WEKA",
        "Additional setup may be required",
        "Scans configured WEKA career listings.",
    ),
    CollectorCapability(
        "usajobs",
        "USAJOBS",
        "Additional setup may be required",
        "Scans configured public USAJOBS searches.",
    ),
    CollectorCapability(
        "html",
        "Standard public careers page",
        "Additional setup may be required",
        "Scans supported public career pages that do not use a known platform.",
    ),
)


def list_collector_capabilities() -> tuple[CollectorCapability, ...]:
    """Return the immutable application-owned collector list."""

    return COLLECTOR_CAPABILITIES
