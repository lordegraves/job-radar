"""Verify the editable job-fit preference board and save workflow."""

import json
from pathlib import Path
from io import BytesIO

from job_radar.profile_models import ManagedProfile, ProfilePreferences
from job_radar.profile_scoring import resolve_effective_scoring_config
from job_radar.profile_storage import create_profile, get_profile, set_active_profile
from job_radar.web_app import create_app


def _write_settings(root: Path) -> Path:
    settings_path = root / "config" / "settings.yaml"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(
        """
database_path: data/job_radar.sqlite3
reports_path: reports
logs_path: logs
""".lstrip(),
        encoding="utf-8",
    )
    return settings_path


def _create_profile(root: Path) -> tuple[Path, ManagedProfile]:
    database_path = root / "data" / "job_radar.sqlite3"
    profile = ManagedProfile(
        profile_id="profile_aaaaaaaa",
        display_name="Infrastructure Search",
        preferences=ProfilePreferences(
            core_strengths=("Linux",),
            credible_adjacent=("Kubernetes",),
            exclusions=("Sales",),
        ),
        scoring_config={
            "positive_keywords": {
                "linux": 10,
                "kubernetes": 8,
            },
            "negative_keywords": {
                "sales": -15,
            },
            "location_preferences": {
                "allowed": {},
                "conditional": {},
                "skipped": {},
            },
            "top_matches": {
                "min_score": 120,
                "excluded_title_keywords": [
                    "sales",
                ],
                "strong_signals": [
                    "title:kubernetes",
                ],
            },
            "review_needed": {
                "min_score": 100,
                "excluded_location_statuses": [],
                "strong_signals": [
                    "body:kubernetes",
                ],
            },
        },
    )
    create_profile(database_path, profile)
    set_active_profile(database_path, profile.profile_id)
    return database_path, profile


def test_fit_board_shows_inferred_user_friendly_buckets(tmp_path: Path) -> None:
    settings_path = _write_settings(tmp_path)
    _, profile = _create_profile(tmp_path)
    app = create_app(
        settings_path=str(settings_path),
        base_directory=str(tmp_path),
    )

    response = app.test_client().get(f"/profile/{profile.profile_id}/fit")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Job fit preferences" in html
    assert "Strong Match" in html
    assert "Needs Review" in html
    assert "Avoid" in html
    assert "Ignored" in html
    assert "Kubernetes" in html
    assert 'data-category="review"' in html
    assert "Save job-fit preferences" in html
    assert 'draggable="true"' in html


def test_fit_board_save_persists_board_and_updates_scan_scoring(
    tmp_path: Path,
) -> None:
    settings_path = _write_settings(tmp_path)
    scoring_path = tmp_path / "config" / "scoring.yaml"
    database_path, profile = _create_profile(tmp_path)
    app = create_app(
        settings_path=str(settings_path),
        base_directory=str(tmp_path),
    )

    saved_signals = [
        {
            "term": "Linux",
            "category": "strong",
            "explanation": "Core production experience.",
        },
        {
            "term": "Kubernetes",
            "category": "review",
            "explanation": "Lab experience; production ownership is unclear.",
        },
        {
            "term": "Sales",
            "category": "avoid",
            "explanation": "Not target work.",
        },
        {
            "term": "Terraform",
            "category": "ignored",
            "explanation": "Do not use this when judging fit.",
        },
    ]

    response = app.test_client().post(
        f"/profile/{profile.profile_id}/fit",
        data={"fit_signals_json": json.dumps(saved_signals)},
    )

    assert response.status_code == 302
    assert "fit_preferences_saved" in response.headers["Location"]

    stored = get_profile(database_path, profile.profile_id)
    assert stored is not None
    assert [signal.term for signal in stored.fit_signals] == [
        "Linux",
        "Kubernetes",
        "Sales",
        "Terraform",
    ]
    assert [signal.category for signal in stored.fit_signals] == [
        "strong",
        "review",
        "avoid",
        "ignored",
    ]
    assert all(signal.user_overridden for signal in stored.fit_signals)
    assert all(signal.evidence_source == "user" for signal in stored.fit_signals)

    scoring = resolve_effective_scoring_config(
        database_path,
        scoring_path,
    )

    assert scoring["positive_keywords"]["linux"] == 10
    assert "kubernetes" not in scoring["positive_keywords"]
    assert "kubernetes" not in scoring["negative_keywords"]
    assert scoring["negative_keywords"]["sales"] == -15
    assert scoring["top_matches"]["strong_signals"] == ["body:linux"]
    assert scoring["review_needed"]["strong_signals"] == ["body:kubernetes"]
    assert "sales" in scoring["top_matches"]["excluded_title_keywords"]
    assert "terraform" not in scoring["positive_keywords"]
    assert "terraform" not in scoring["negative_keywords"]


def test_fit_board_rejects_duplicate_terms(tmp_path: Path) -> None:
    settings_path = _write_settings(tmp_path)
    _, profile = _create_profile(tmp_path)
    app = create_app(
        settings_path=str(settings_path),
        base_directory=str(tmp_path),
    )

    response = app.test_client().post(
        f"/profile/{profile.profile_id}/fit",
        data={
            "fit_signals_json": json.dumps(
                [
                    {"term": "Linux", "category": "strong"},
                    {"term": "linux", "category": "review"},
                ]
            )
        },
    )

    assert response.status_code == 302
    assert "fit_error=" in response.headers["Location"]


def test_fit_board_suggests_exact_resume_capabilities_without_activating_them(
    tmp_path: Path,
) -> None:
    settings_path = _write_settings(tmp_path)
    database_path = tmp_path / "data" / "job_radar.sqlite3"
    profile = ManagedProfile(
        profile_id="profile_bbbbbbbb",
        display_name="Services Leadership",
        preferences=ProfilePreferences(
            target_roles=("Solution Architect",),
        ),
        scoring_config={
            "positive_keywords": {},
            "negative_keywords": {},
            "top_matches": {"strong_signals": []},
            "review_needed": {"strong_signals": []},
        },
    )
    create_profile(database_path, profile)
    set_active_profile(database_path, profile.profile_id)
    app = create_app(
        settings_path=str(settings_path),
        base_directory=str(tmp_path),
    )
    client = app.test_client()
    upload = client.post(
        f"/profile/{profile.profile_id}/resume",
        data={
            "resume_file": (
                BytesIO(
                    b"Summary\nSolution Architect\nTechnical Skills\n"
                    b"Professional services scoping\nSOW authoring\n"
                    b"Professional Experience\nUnrelated narrative"
                ),
                "resume.txt",
            )
        },
        content_type="multipart/form-data",
    )
    assert upload.status_code == 302

    html = client.get(f"/profile/{profile.profile_id}/fit").get_data(as_text=True)
    assert "Solution Architect" in html
    assert "Professional services scoping" in html
    assert "SOW authoring" in html
    assert "exact words in your résumé" in html
    assert 'data-category="review"' in html

    stored = get_profile(database_path, profile.profile_id)
    assert stored is not None
    assert stored.fit_signals == ()
    assert stored.scoring_config is not None
    assert stored.scoring_config["positive_keywords"] == {}


def test_fit_board_splits_dense_resume_skills_into_usable_suggestions(
    tmp_path: Path,
) -> None:
    settings_path = _write_settings(tmp_path)
    database_path = tmp_path / "data" / "job_radar.sqlite3"
    profile = ManagedProfile(
        profile_id="profile_cccccccc",
        display_name="Solution Architecture",
        preferences=ProfilePreferences(target_roles=("Solution Architect",)),
        scoring_config={
            "positive_keywords": {},
            "negative_keywords": {},
            "top_matches": {"strong_signals": []},
            "review_needed": {"strong_signals": []},
        },
    )
    create_profile(database_path, profile)
    set_active_profile(database_path, profile.profile_id)
    app = create_app(settings_path=str(settings_path), base_directory=str(tmp_path))
    client = app.test_client()
    client.post(
        f"/profile/{profile.profile_id}/resume",
        data={
            "resume_file": (
                BytesIO(
                    b"Summary\nSolution Architect\nTechnical Skills\n"
                    b"Business Continuity & Disaster Recovery\n"
                    b"Hypervisors & VDI: VMware ESXi / vSphere, Microsoft Hyper-V\n"
                    b"Professional Experience\n"
                ),
                "resume.txt",
            )
        },
        content_type="multipart/form-data",
    )

    html = client.get(f"/profile/{profile.profile_id}/fit").get_data(as_text=True)

    assert "Business Continuity" in html
    assert "Disaster Recovery" in html
    assert "Hypervisors &amp; VDI" in html
    assert "VMware ESXi" in html
    assert "vSphere" in html
    assert "Microsoft Hyper-V" in html
