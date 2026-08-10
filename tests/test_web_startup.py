"""Verify safe, understandable failures during web application startup.

The tests cover missing or invalid settings, unexpected exceptions, diagnostic
log redaction, support guidance, and server startup failures without exposing
raw private error messages.
"""

import sys
from pathlib import Path

import pytest

from job_radar import web_app
from job_radar.config import ConfigError


def test_configuration_startup_error_explains_missing_settings(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "config" / "settings.yaml"
    error = ConfigError(f"Config file does not exist: {settings_path}")

    message = web_app._format_configuration_startup_error(
        error,
        settings_path=settings_path,
    )

    assert (
        "junior could not start because its settings file was not found."
        in message
    )
    assert "What to do:" in message
    assert "junior bootstrap-user-data" in message
    assert "Then start junior again." in message
    assert "Technical details:" in message
    assert str(settings_path) in message


def test_configuration_startup_error_explains_invalid_settings(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "config" / "settings.yaml"
    error = ConfigError("settings.yaml reports_path must be a string")

    message = web_app._format_configuration_startup_error(
        error,
        settings_path=settings_path,
    )

    assert "junior could not start because its settings are invalid." in message
    assert "Open the settings file shown below" in message
    assert "settings.yaml reports_path must be a string" in message
    assert "Settings file:" in message
    assert str(settings_path.resolve()) in message


def test_unexpected_startup_error_directs_user_to_support(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "config" / "settings.yaml"
    diagnostic_log_path = tmp_path / "logs" / "startup-errors.log"
    error = RuntimeError("unexpected startup failure")

    message = web_app._format_unexpected_startup_error(
        error,
        settings_path=settings_path,
        diagnostic_log_path=diagnostic_log_path,
    )

    assert "unexpected problem" in message
    assert "probably not something you can fix" in message
    assert "claytonmgraves@outlook.com" in message
    assert "Do not include passwords" in message
    assert str(diagnostic_log_path) in message
    assert "Error type: RuntimeError" in message
    assert "unexpected startup failure" not in message
    assert "exception message was omitted" in message
    assert str(settings_path.resolve()) in message


def test_main_reports_missing_settings_without_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings_path = tmp_path / "missing-settings.yaml"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "junior-web",
            "--settings",
            str(settings_path),
        ],
    )

    with pytest.raises(SystemExit) as exit_error:
        web_app.main()

    captured = capsys.readouterr()

    assert exit_error.value.code == 1
    assert captured.out == ""
    assert "settings file was not found" in captured.err
    assert "junior bootstrap-user-data" in captured.err
    assert f"Config file does not exist: {settings_path.resolve()}" in captured.err
    assert "Traceback" not in captured.err


def test_main_reports_unexpected_failure_and_support_contact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings_path = tmp_path / "config" / "settings.yaml"
    diagnostic_log_path = tmp_path / "logs" / "startup-errors.log"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "junior-web",
            "--settings",
            str(settings_path),
        ],
    )
    monkeypatch.setattr(
        web_app,
        "create_app",
        lambda **_kwargs: (_ for _ in ()).throw(
            RuntimeError("unexpected startup failure")
        ),
    )
    monkeypatch.setattr(
        web_app,
        "_write_startup_diagnostic_log",
        lambda *_args, **_kwargs: diagnostic_log_path,
    )

    with pytest.raises(SystemExit) as exit_error:
        web_app.main()

    captured = capsys.readouterr()

    assert exit_error.value.code == 1
    assert captured.out == ""
    assert "unexpected problem" in captured.err
    assert "claytonmgraves@outlook.com" in captured.err
    assert str(diagnostic_log_path) in captured.err
    assert "Error type: RuntimeError" in captured.err
    assert "unexpected startup failure" not in captured.err
    assert "exception message was omitted" in captured.err
    assert "Traceback" not in captured.err


def test_unexpected_startup_failure_writes_diagnostic_log(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "config" / "settings.yaml"

    try:
        raise RuntimeError("diagnostic test failure")
    except RuntimeError as error:
        diagnostic_log_path = web_app._write_startup_diagnostic_log(
            error,
            settings_path=settings_path,
        )

    assert diagnostic_log_path is not None
    assert diagnostic_log_path.is_file()

    log_text = diagnostic_log_path.read_text(encoding="utf-8")

    assert "junior startup failure" in log_text
    assert "Build: RC6 Build 1.19" in log_text
    assert "Failure stage: application_startup" in log_text
    assert "Failure category: unexpected_application_failure" in log_text
    assert "Error type: RuntimeError" in log_text
    assert "Stack frames:" in log_text
    assert "test_unexpected_startup_failure_writes_diagnostic_log" in log_text
    assert "diagnostic test failure" not in log_text
    assert "local variables are intentionally omitted" in log_text
    assert str(settings_path.resolve()) in log_text


def test_startup_log_records_safe_desktop_runtime_details(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "config" / "settings.yaml"

    try:
        raise RuntimeError("private runtime detail")
    except RuntimeError as error:
        diagnostic_log_path = web_app._write_startup_diagnostic_log(
            error,
            settings_path=settings_path,
            failure_stage="native_window_initialization",
            safe_details={
                "python_runtime_file": "present; 445952 bytes; sha256=abc123",
                "processor_architecture": "AMD64",
            },
        )

    assert diagnostic_log_path is not None
    log_text = diagnostic_log_path.read_text(encoding="utf-8")
    assert "Failure stage: native_window_initialization" in log_text
    assert "Safe runtime details:" in log_text
    assert "processor_architecture: AMD64" in log_text
    assert "python_runtime_file: present; 445952 bytes; sha256=abc123" in log_text
    assert "private runtime detail" not in log_text


def test_main_reports_server_startup_failure_and_support_contact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings_path = tmp_path / "config" / "settings.yaml"
    diagnostic_log_path = tmp_path / "logs" / "startup-errors.log"

    class FailingApp:
        def run(self, **_kwargs) -> None:
            raise RuntimeError("server startup failure")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "junior-web",
            "--settings",
            str(settings_path),
        ],
    )
    monkeypatch.setattr(
        web_app,
        "create_app",
        lambda **_kwargs: FailingApp(),
    )
    monkeypatch.setattr(
        web_app,
        "_write_startup_diagnostic_log",
        lambda *_args, **_kwargs: diagnostic_log_path,
    )

    with pytest.raises(SystemExit) as exit_error:
        web_app.main()

    captured = capsys.readouterr()

    assert exit_error.value.code == 1
    assert captured.out == ""
    assert "unexpected problem" in captured.err
    assert "claytonmgraves@outlook.com" in captured.err
    assert str(diagnostic_log_path) in captured.err
    assert "Error type: RuntimeError" in captured.err
    assert "server startup failure" not in captured.err
    assert "exception message was omitted" in captured.err
    assert "Traceback" not in captured.err
