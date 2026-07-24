"""Verify the Linux tarball recipe is portable and preserves user data."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_linux_spec_uses_shared_desktop_entry_and_resources() -> None:
    text = (PROJECT_ROOT / "packaging/linux/junior.spec").read_text()
    assert '"desktop_launcher.py"' in text
    assert 'collect_data_files("job_radar")' in text
    assert 'collect_all("webview")' in text
    assert 'name="junior"' in text


def test_linux_build_is_native_and_creates_tarball() -> None:
    text = (PROJECT_ROOT / "scripts/build_linux_tarball.sh").read_text()
    assert '"$(uname -s)" != "Linux"' in text
    assert ".venv/bin/python" in text
    assert "packaging/linux/junior.spec" in text
    assert "Junior-linux-x86_64.tar.gz" in text


def test_docker_build_context_excludes_user_data() -> None:
    dockerignore = (PROJECT_ROOT / ".dockerignore").read_text()
    assert dockerignore.startswith("# Linux release builds")
    assert dockerignore.splitlines()[1] == "*"
    assert "!job_radar/**" in dockerignore
    for private_path in ("data", "profiles", "reports", "logs", "config"):
        assert f"!{private_path}" not in dockerignore


def test_windows_host_build_exports_only_linux_artifact() -> None:
    text = (PROJECT_ROOT / "scripts/build_linux_tarball.ps1").read_text()
    assert "packaging\\linux\\Dockerfile" in text
    assert "--target artifact" in text
    assert "type=local" in text
    assert "Junior-linux-x86_64.tar.gz" in text


def test_linux_container_installs_required_binary_inspection_tool() -> None:
    text = (PROJECT_ROOT / "packaging/linux/Dockerfile").read_text()
    assert "binutils" in text
    assert "rm -rf /var/lib/apt/lists/*" in text


def test_linux_uninstall_preserves_user_owned_categories() -> None:
    text = (PROJECT_ROOT / "packaging/linux/uninstall.sh").read_text()
    assert "junior/application" in text
    assert ".config/job-radar" not in text
    assert "Profiles, resumes, settings, databases" in text


def test_linux_launcher_checks_platform_and_webview_dependency() -> None:
    text = (PROJECT_ROOT / "packaging/linux/launch-junior.sh").read_text()
    assert 'uname -s' in text
    assert "libwebkit2gtk" in text
    assert 'exec "$bundle_dir/junior" "$@"' in text
