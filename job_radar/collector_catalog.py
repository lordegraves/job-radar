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
        "eightfold",
        "Eightfold",
        "Automatic from supported careers URLs",
        "Scans public Eightfold PCS career sites.",
    ),
    CollectorCapability(
        "workday",
        "Workday",
        "Automatic when Junior finds the Workday site",
        "Scans configured public Workday career sites.",
    ),
    CollectorCapability(
        "icims",
        "iCIMS",
        "Automatic when Junior finds the iCIMS site",
        "Scans configured public iCIMS career sites.",
    ),
    CollectorCapability(
        "ukg",
        "UKG Pro Recruiting",
        "Automatic from complete UKG or UltiPro URL",
        "Scans public UKG Pro Recruiting job boards.",
    ),
    CollectorCapability(
        "oracle_hcm",
        "Oracle Cloud HCM",
        "Automatic when Junior finds Oracle site metadata",
        "Scans configured Oracle Cloud recruiting sites.",
    ),
    CollectorCapability(
        "smartrecruiters",
        "SmartRecruiters",
        "Automatic when Junior finds the SmartRecruiters site",
        "Scans configured public SmartRecruiters job sites.",
    ),
    CollectorCapability(
        "selectminds",
        "SelectMinds",
        "Automatic when Junior finds the SelectMinds site",
        "Scans configured SelectMinds career sites.",
    ),
    CollectorCapability(
        "phenom",
        "Phenom",
        "Collector available; automatic setup not yet verified",
        "Scans configured Phenom-powered career sites.",
    ),
    CollectorCapability(
        "dayforce",
        "Dayforce",
        "Automatic when Junior finds the Dayforce site",
        "Scans configured Dayforce career sites.",
    ),
    CollectorCapability(
        "rippling",
        "Rippling",
        "Automatic when Junior finds the Rippling site",
        "Scans configured Rippling job boards.",
    ),
    CollectorCapability(
        "schoolspring",
        "SchoolSpring",
        "Collector available; automatic setup not yet verified",
        "Scans configured SchoolSpring education listings.",
    ),
    CollectorCapability(
        "jibe",
        "Jibe",
        "Collector available; automatic setup not yet verified",
        "Scans configured Jibe-powered career sites.",
    ),
    CollectorCapability(
        "jobsyn",
        "JobSync",
        "Collector available; automatic setup not yet verified",
        "Scans configured JobSync-powered listings.",
    ),
    CollectorCapability(
        "activate",
        "Activate",
        "Collector available; automatic setup not yet verified",
        "Scans configured Activate-powered career sites.",
    ),
    CollectorCapability(
        "weka",
        "WEKA",
        "Collector available; automatic setup not yet verified",
        "Scans configured WEKA career listings.",
    ),
    CollectorCapability(
        "usajobs",
        "USAJOBS",
        "API access and organization setup required",
        "Scans configured public USAJOBS searches after the registered email and authorization key are saved securely in Settings.",
    ),
    CollectorCapability(
        "html",
        "Standard public careers page",
        "Automatic only after real-job validation",
        "Scans supported public career pages, including HRMDirect/ClearCompany boards, that do not use a dedicated collector.",
    ),
    CollectorCapability(
        "talentbrew",
        "TalentBrew",
        "Automatic from a TalentBrew-powered careers URL",
        "Recognizes TalentBrew career sites and scans their public job listings.",
    ),
    CollectorCapability(
        "google_careers",
        "Google Careers",
        "Automatic from Google Careers URL",
        "Scans Google's public careers search and complete job records.",
    ),
    CollectorCapability(
        "walmart",
        "Walmart Careers",
        "Automatic and scoped to the active profile",
        "Scans every Walmart-family job matching the profile's target roles and locations.",
    ),
)


def list_collector_capabilities() -> tuple[CollectorCapability, ...]:
    """Return the immutable application-owned collector list."""

    return COLLECTOR_CAPABILITIES
