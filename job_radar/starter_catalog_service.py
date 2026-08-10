"""Install a tested starter employer catalog without overwriting user data."""

import json
from pathlib import Path

from job_radar.database import connect_database
from job_radar.storage import initialize_database


STARTER_CATALOG_VERSION = 1

_GREENHOUSE_EMPLOYERS = (
    ("affirm", "Affirm"), ("airbnb", "Airbnb"),
    ("andurilindustries", "Anduril Industries"), ("asana", "Asana"),
    ("block", "Block"), ("brex", "Brex"), ("canonical", "Canonical"),
    ("carta", "Carta"), ("carvana", "Carvana"), ("chime", "Chime"),
    ("cloudflare", "Cloudflare"), ("coinbase", "Coinbase"),
    ("coursera", "Coursera"), ("datadog", "Datadog"),
    ("discord", "Discord"), ("doordashusa", "DoorDash"),
    ("dropbox", "Dropbox"), ("duolingo", "Duolingo"),
    ("elastic", "Elastic"), ("figma", "Figma"), ("gitlab", "GitLab"),
    ("grafanalabs", "Grafana Labs"), ("gusto", "Gusto"),
    ("hellofresh", "HelloFresh"), ("hubspotjobs", "HubSpot"),
    ("instacart", "Instacart"), ("khanacademy", "Khan Academy"),
    ("lucidmotors", "Lucid Motors"), ("lyft", "Lyft"),
    ("mongodb", "MongoDB"), ("mozilla", "Mozilla"), ("okta", "Okta"),
    ("oscar", "Oscar Health"), ("peloton", "Peloton"),
    ("pinterest", "Pinterest"), ("reddit", "Reddit"),
    ("relativity", "Relativity Space"), ("robinhood", "Robinhood"),
    ("samsara", "Samsara"), ("sofi", "SoFi"), ("stripe", "Stripe"),
    ("sweetgreen", "Sweetgreen"), ("toast", "Toast"),
    ("voxmedia", "Vox Media"), ("waymo", "Waymo"),
    ("wikimedia", "Wikimedia Foundation"),
)


def starter_catalog_entries() -> tuple[dict[str, object], ...]:
    """Return immutable source definitions admitted by live collector tests."""

    greenhouse = tuple(
        {
            "employer_id": f"starter_{slug}",
            "name": name,
            "source_type": "greenhouse",
            "source_identifier": slug,
            "careers_url": f"https://job-boards.greenhouse.io/{slug}",
            "source_config": {
                "source_slug": slug,
                "careers_url": f"https://job-boards.greenhouse.io/{slug}",
            },
        }
        for slug, name in _GREENHOUSE_EMPLOYERS
    )
    return greenhouse + (
        {
            "employer_id": "starter_google",
            "name": "Google",
            "source_type": "google_careers",
            "source_identifier": "google-careers",
            "careers_url": "https://www.google.com/about/careers/applications/jobs/results",
            "source_config": {
                "source_url": "https://www.google.com/about/careers/applications/jobs/results",
                "careers_url": "https://www.google.com/about/careers/applications/jobs/results",
            },
        },
        {
            "employer_id": "starter_microsoft",
            "name": "Microsoft",
            "source_type": "eightfold",
            "source_identifier": "apply.careers.microsoft.com:microsoft.com",
            "careers_url": "https://careers.microsoft.com/v2/global/en/home.html",
            "source_config": {
                "source_url": "https://apply.careers.microsoft.com",
                "domain": "microsoft.com",
                "careers_url": "https://careers.microsoft.com/v2/global/en/home.html",
            },
        },
        {
            "employer_id": "starter_walmart",
            "name": "Walmart",
            "source_type": "walmart",
            "source_identifier": "walmart-careers",
            "careers_url": "https://careers.walmart.com/",
            "source_config": {
                "source_url": "https://careers.walmart.com/api/graphql",
                "careers_url": "https://careers.walmart.com/",
            },
        },
        {
            "employer_id": "starter_ford",
            "name": "Ford Motor Company",
            "source_type": "talentbrew",
            "source_identifier": "www.careers.ford.com/search-jobs",
            "careers_url": "https://www.careers.ford.com/search-jobs",
            "source_config": {
                "source_url": "https://www.careers.ford.com/search-jobs",
                "careers_url": "https://www.careers.ford.com/search-jobs",
                "job_link_patterns": ["/job/"],
            },
        },
    )


def seed_starter_catalog(database_path: str | Path) -> int:
    """Apply this catalog version once, appending IDs that are still absent."""

    db_path = initialize_database(database_path)
    with connect_database(db_path) as connection:
        if connection.execute(
            "SELECT 1 FROM starter_catalog_versions WHERE catalog_version = ?",
            (STARTER_CATALOG_VERSION,),
        ).fetchone():
            return 0
        inserted = 0
        for entry in starter_catalog_entries():
            cursor = connection.execute(
                """
                INSERT INTO employer_sources (
                    employer_id, name, source_type, enabled, source_config_json,
                    normalized_name, normalized_careers_url, source_identifier,
                    resolution_status, creation_source, catalog_origin,
                    validation_state, last_validated_at
                ) VALUES (?, ?, ?, 1, ?, ?, ?, ?, 'existing',
                          'starter_catalog', 'starter', 'valid', CURRENT_TIMESTAMP)
                ON CONFLICT DO NOTHING
                """,
                (
                    entry["employer_id"], entry["name"], entry["source_type"],
                    json.dumps(entry["source_config"], separators=(",", ":"), sort_keys=True),
                    str(entry["name"]).casefold(), entry["careers_url"],
                    entry["source_identifier"],
                ),
            )
            inserted += cursor.rowcount
        connection.execute(
            "INSERT INTO starter_catalog_versions (catalog_version) VALUES (?)",
            (STARTER_CATALOG_VERSION,),
        )
        return inserted
