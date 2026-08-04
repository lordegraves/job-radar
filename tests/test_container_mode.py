"""Verify container mode uses shared services and persistent external data."""

from pathlib import Path

from job_radar import __version__
from job_radar.web_app import create_app


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_health_endpoint_is_bounded_and_contains_no_user_content(
    tmp_path: Path,
) -> None:
    settings = tmp_path / "config/settings.yaml"
    settings.parent.mkdir(parents=True)
    settings.write_text(
        "database_path: data/junior.sqlite3\n"
        "reports_path: reports\n"
        "logs_path: logs\n",
        encoding="utf-8",
    )
    response = create_app(
        settings_path=settings,
        base_directory=tmp_path,
    ).test_client().get("/health")

    assert response.status_code == 200
    assert response.get_json() == {
        "application": "junior",
        "status": "ready",
        "version": __version__,
    }
    assert str(tmp_path) not in response.get_data(as_text=True)


def test_container_uses_persistent_mount_and_shared_web_app() -> None:
    dockerfile = (
        PROJECT_ROOT / "packaging/container/Dockerfile"
    ).read_text(encoding="utf-8")
    entrypoint = (
        PROJECT_ROOT / "packaging/container/entrypoint.sh"
    ).read_text(encoding="utf-8")

    assert "JOB_RADAR_DATA_DIR=/var/lib/junior" in dockerfile
    assert 'VOLUME ["/var/lib/junior"]' in dockerfile
    assert "USER junior:junior" in dockerfile
    assert "/health" in dockerfile
    assert (
        "COPY pyproject.toml README.md LICENSE PRIVACY.md SECURITY.md "
        "THIRD_PARTY_LICENSES.md "
        "dependency-license-report.json ./"
    ) in dockerfile
    assert "COPY third_party ./third_party" in dockerfile
    assert 'org.opencontainers.image.licenses="GPL-3.0-only"' in dockerfile
    assert "junior bootstrap-user-data" in entrypoint
    assert '"job_radar.web_app:create_app()"' in entrypoint
    assert entrypoint.count("bootstrap-user-data") == 1
    assert 'exec "$@"' in entrypoint


def test_compose_binds_to_localhost_and_uses_named_volume() -> None:
    compose = (
        PROJECT_ROOT / "packaging/container/compose.yaml"
    ).read_text(encoding="utf-8")

    assert '"127.0.0.1:8000:8000"' in compose
    assert "junior-data:/var/lib/junior" in compose
    assert "restart: unless-stopped" in compose
