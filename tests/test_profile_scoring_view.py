"""Verify the Profile page shows the scoring owned by the active profile."""

from pathlib import Path

from job_radar.profile_models import ManagedProfile
from job_radar.profile_storage import create_profile, set_active_profile
from job_radar.web_app import create_app


def test_profile_page_shows_active_profile_scoring_instead_of_global_yaml(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "config" / "settings.yaml"
    scoring_path = tmp_path / "config" / "scoring.yaml"
    database_path = tmp_path / "data" / "job_radar.sqlite3"

    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(
        """
database_path: data/job_radar.sqlite3
reports_path: reports
logs_path: logs
""".lstrip(),
        encoding="utf-8",
    )
    scoring_path.write_text(
        """
positive_keywords:
  linux: 10
negative_keywords: {}
location_preferences:
  allowed: {}
  conditional: {}
  skipped: {}
top_matches:
  min_score: 120
  excluded_title_keywords: []
  strong_signals:
    - title:linux
review_needed:
  min_score: 100
  excluded_location_statuses: []
  strong_signals:
    - body:linux
""".lstrip(),
        encoding="utf-8",
    )

    profile_scoring = {
        "positive_keywords": {
            "baker": 15,
        },
        "negative_keywords": {},
        "location_preferences": {
            "allowed": {},
            "conditional": {},
            "skipped": {},
        },
        "top_matches": {
            "min_score": 45,
            "excluded_title_keywords": [],
            "strong_signals": [
                "title:baker",
            ],
        },
        "review_needed": {
            "min_score": 20,
            "excluded_location_statuses": [],
            "strong_signals": [
                "body:pastry",
            ],
        },
    }
    profile = ManagedProfile(
        profile_id="profile_aaaaaaaa",
        display_name="Bakery Search",
        scoring_config=profile_scoring,
    )
    create_profile(database_path, profile)
    set_active_profile(database_path, profile.profile_id)

    app = create_app(
        settings_path=str(settings_path),
        base_directory=str(tmp_path),
    )
    response = app.test_client().get("/profile")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Job fit" in html
    assert "Baker" in html
    assert "Pastry" in html
    assert "Linux" not in html
    assert "Top Match threshold" not in html
    assert "Review Needed threshold" not in html
    assert ">45<" not in html
    assert ">20<" not in html
