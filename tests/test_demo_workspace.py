"""Verify fictional demo data stays isolated, repeatable, and safe to render."""

from pathlib import Path

import pytest

from job_radar.demo_workspace import (
    DEMO_PROFILE_ID,
    DemoWorkspaceError,
    create_demo_workspace,
)
from job_radar.employer_storage import list_employer_sources
from job_radar.profile_storage import get_active_profile
from job_radar.runtime_paths import RuntimePaths
from job_radar.tracker.tracker_storage import list_applications
from job_radar.web_app import create_app


def test_create_demo_workspace_builds_complete_fictional_data(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "junior-demo"

    paths = create_demo_workspace(destination)
    runtime_paths = RuntimePaths.from_settings(
        paths.config / "settings.yaml",
        base_directory=paths.root,
    )
    profile = get_active_profile(runtime_paths.database_path)

    assert paths.root == destination.resolve()
    assert profile is not None
    assert profile.profile_id == DEMO_PROFILE_ID
    assert profile.display_name == "Jordan Rivera"
    assert set(profile.company_ids) == {
        "northstar_foods",
        "harborview_university",
        "meadow_market",
    }
    assert len(list_employer_sources(runtime_paths.database_path)) == 3
    assert len(
        list_applications(
            runtime_paths.database_path,
            profile_id=DEMO_PROFILE_ID,
        )
    ) == 3
    assert (paths.resumes / DEMO_PROFILE_ID / "resume.md").is_file()
    assert (paths.resumes / DEMO_PROFILE_ID / "resume.normalized.txt").is_file()


def test_create_demo_workspace_refuses_to_touch_existing_destination(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "existing"
    destination.mkdir()
    sentinel = destination / "keep-me.txt"
    sentinel.write_text("real user data", encoding="utf-8")

    with pytest.raises(DemoWorkspaceError, match="already exists"):
        create_demo_workspace(destination)

    assert sentinel.read_text(encoding="utf-8") == "real user data"
    assert list(destination.iterdir()) == [sentinel]


@pytest.mark.parametrize(
    ("path", "expected_text"),
    (
        ("/", "Home"),
        ("/profile", "Jordan Rivera"),
        ("/companies", "Northstar Foods"),
        ("/tracker", "Production Baker"),
        ("/history", "Lakeview Hotel"),
    ),
)
def test_demo_workspace_renders_key_pages(
    tmp_path: Path,
    path: str,
    expected_text: str,
) -> None:
    destination_name = path.strip("/") or "home"
    paths = create_demo_workspace(tmp_path / f"demo-{destination_name}")
    app = create_app(
        settings_path=paths.config / "settings.yaml",
        base_directory=paths.root,
    )
    app.config.update(TESTING=True)

    response = app.test_client().get(path)

    assert response.status_code == 200
    assert expected_text in response.get_data(as_text=True)
