"""Verify the session-scoped Administration shell and navigation boundary."""

from pathlib import Path

from job_radar.web_app import create_app


def write_settings_file(path: Path, database_path: Path) -> None:
    path.write_text(
        (
            f"database_path: {database_path}\n"
            f"reports_path: {path.parent / 'reports'}\n"
            f"logs_path: {path.parent / 'logs'}\n"
        ),
        encoding="utf-8",
    )


def build_test_app(tmp_path: Path):
    settings_path = tmp_path / "config" / "settings.yaml"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    write_settings_file(
        settings_path,
        tmp_path / "data" / "junior.sqlite3",
    )
    return create_app(
        settings_path=settings_path,
        base_directory=tmp_path,
    )


def test_administration_unlock_lock_and_session_isolation(
    tmp_path: Path,
) -> None:
    app = build_test_app(tmp_path)
    client = app.test_client()

    locked_response = client.get("/administration")
    unlock_page = client.get("/administration/unlock")
    incorrect_response = client.post(
        "/administration/unlock",
        data={"confirmation": "admin"},
        follow_redirects=True,
    )

    assert locked_response.status_code == 302
    assert "/administration/unlock" in locked_response.headers["Location"]
    assert unlock_page.status_code == 200
    assert "Type ADMIN to continue" in unlock_page.get_data(as_text=True)
    assert "Administration remains locked" in incorrect_response.get_data(
        as_text=True
    )
    assert client.get("/administration").status_code == 302

    unlocked_response = client.post(
        "/administration/unlock",
        data={"confirmation": "ADMIN"},
        follow_redirects=True,
    )
    unlocked_settings = client.get("/settings").get_data(as_text=True)

    assert unlocked_response.status_code == 200
    assert "<h1 class=\"page-title\">Administration</h1>" in (
        unlocked_response.get_data(as_text=True)
    )
    assert ">Administration</a>" in unlocked_settings
    assert "Administration mode" in unlocked_settings
    assert "Exit" in unlocked_settings

    separate_client = app.test_client()
    assert separate_client.get("/administration").status_code == 302

    lock_response = client.post(
        "/administration/lock",
        data={"next": "/settings"},
    )
    assert lock_response.status_code == 302
    assert lock_response.headers["Location"] == "/settings"
    assert client.get("/administration").status_code == 302


def test_administration_redirects_accept_only_safe_local_paths(
    tmp_path: Path,
) -> None:
    app = build_test_app(tmp_path)
    client = app.test_client()

    safe_response = client.post(
        "/administration/unlock",
        data={
            "confirmation": "ADMIN",
            "next": "/settings?section=email",
        },
    )
    assert safe_response.headers["Location"] == "/settings?section=email"

    client.post("/administration/lock")
    unsafe_response = client.post(
        "/administration/unlock",
        data={
            "confirmation": "ADMIN",
            "next": "https://example.invalid/steal",
        },
    )
    assert unsafe_response.headers["Location"] == "/administration"


def test_settings_stays_available_and_locked_navigation_stays_normal(
    tmp_path: Path,
) -> None:
    app = build_test_app(tmp_path)
    client = app.test_client()

    settings_response = client.get("/settings")
    html = settings_response.get_data(as_text=True)

    assert settings_response.status_code == 200
    assert "<h1 class=\"page-title\">Settings</h1>" in html
    assert "Unlock Administration" in html
    assert ">Administration</a>" not in html
    assert "Administration mode" not in html


def test_new_app_process_invalidates_prior_administration_marker(
    tmp_path: Path,
) -> None:
    first_app = build_test_app(tmp_path)
    first_client = first_app.test_client()
    first_client.post(
        "/administration/unlock",
        data={"confirmation": "ADMIN"},
    )
    prior_session_cookie = first_client.get_cookie("session")
    second_app = build_test_app(tmp_path)
    second_client = second_app.test_client()

    assert prior_session_cookie is not None
    second_client.set_cookie("session", prior_session_cookie.value)

    assert first_app.config["SECRET_KEY"] == second_app.config["SECRET_KEY"]
    assert (
        first_app.config["JOB_RADAR_ADMIN_SESSION_MARKER"]
        != second_app.config["JOB_RADAR_ADMIN_SESSION_MARKER"]
    )
    assert first_app.config["SECRET_KEY"] not in {
        b"development",
        b"secret",
        b"changeme",
    }
    assert second_client.get("/administration").status_code == 302
