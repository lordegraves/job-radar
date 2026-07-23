"""Manage Junior's guarded systemd user service and timer on Linux."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Protocol

from job_radar.schedule_service import (
    ScanSchedule,
    ScheduleIntegrationStatus,
)


SERVICE_NAME = "junior-scan.service"
TIMER_NAME = "junior-scan.timer"
MANAGED_MARKER = "# Managed by Junior. Do not edit while scheduling is enabled."
_SYSTEMD_WEEKDAYS = {
    "monday": "Mon",
    "tuesday": "Tue",
    "wednesday": "Wed",
    "thursday": "Thu",
    "friday": "Fri",
    "saturday": "Sat",
    "sunday": "Sun",
}


class LinuxSchedulerError(RuntimeError):
    """Report a safe, actionable systemd scheduling failure."""


class CompletedCommand(Protocol):
    returncode: int
    stdout: str


CommandRunner = Callable[[Sequence[str]], CompletedCommand]


@dataclass(frozen=True)
class LinuxUnitPaths:
    directory: Path
    service: Path
    timer: Path


def default_user_unit_paths() -> LinuxUnitPaths:
    configured_home = os.environ.get("XDG_CONFIG_HOME")
    config_root = (
        Path(configured_home).expanduser()
        if configured_home
        else Path.home() / ".config"
    )
    directory = config_root / "systemd" / "user"
    return LinuxUnitPaths(
        directory=directory,
        service=directory / SERVICE_NAME,
        timer=directory / TIMER_NAME,
    )


def inspect_linux_timer(
    *,
    unit_paths: LinuxUnitPaths | None = None,
    command_runner: CommandRunner | None = None,
) -> ScheduleIntegrationStatus:
    """Inspect only Junior's two marked units and the user timer state."""
    paths = unit_paths or default_user_unit_paths()
    if sys.platform != "linux" and command_runner is None:
        return ScheduleIntegrationStatus(
            platform_name="Linux",
            available=False,
            installed=False,
            enabled=False,
            state="Unavailable",
            message="Linux systemd scheduling is available only on Linux.",
        )

    service_exists = paths.service.is_file()
    timer_exists = paths.timer.is_file()
    if not service_exists and not timer_exists:
        return ScheduleIntegrationStatus(
            platform_name="Linux",
            available=True,
            installed=False,
            enabled=False,
            state="Not installed",
            message="Junior's Linux scan timer is not installed.",
        )
    if service_exists != timer_exists:
        return ScheduleIntegrationStatus(
            platform_name="Linux",
            available=True,
            installed=False,
            enabled=False,
            state="Needs repair",
            message=(
                "Only part of Junior's Linux schedule exists. "
                "Apply the schedule to repair it."
            ),
        )
    _require_managed(paths.service)
    _require_managed(paths.timer)

    runner = command_runner or _run_systemctl
    result = runner(("systemctl", "--user", "is-enabled", TIMER_NAME))
    enabled = result.returncode == 0
    return ScheduleIntegrationStatus(
        platform_name="Linux",
        available=True,
        installed=True,
        enabled=enabled,
        state="Installed and enabled" if enabled else "Installed but disabled",
        message=(
            "systemd is ready to start Junior on the saved schedule."
            if enabled
            else "Junior's Linux timer exists but will not start scans."
        ),
    )


def apply_linux_schedule(
    schedule: ScanSchedule,
    *,
    user_data_root: str | Path,
    unit_paths: LinuxUnitPaths | None = None,
    command_runner: CommandRunner | None = None,
    executable: str | Path | None = None,
) -> str:
    """Atomically install/update the user units, or disable an off schedule."""
    paths = unit_paths or default_user_unit_paths()
    runner = command_runner or _run_systemctl
    status = inspect_linux_timer(
        unit_paths=paths,
        command_runner=runner,
    )
    if not schedule.enabled:
        if not status.installed:
            return "Scheduling is off. No Linux timer is installed."
        return disable_linux_timer(
            unit_paths=paths,
            command_runner=runner,
        )
    if not schedule.weekdays:
        raise LinuxSchedulerError(
            "Choose at least one weekday before applying the Linux schedule."
        )

    service_text, timer_text = render_linux_units(
        schedule,
        user_data_root=user_data_root,
        executable=executable,
    )
    prior_service = _read_optional_managed(paths.service)
    prior_timer = _read_optional_managed(paths.timer)
    paths.directory.mkdir(parents=True, exist_ok=True)

    try:
        _atomic_write(paths.service, service_text)
        _atomic_write(paths.timer, timer_text)
        _require_success(
            runner(("systemctl", "--user", "daemon-reload")),
            "Junior could not reload the Linux user service manager.",
        )
        _require_success(
            runner(
                (
                    "systemctl",
                    "--user",
                    "enable",
                    "--now",
                    TIMER_NAME,
                )
            ),
            (
                "Junior could not enable its Linux scan timer. "
                "Confirm that systemd user services are available."
            ),
        )
    except BaseException:
        _restore_optional(paths.service, prior_service)
        _restore_optional(paths.timer, prior_timer)
        runner(("systemctl", "--user", "daemon-reload"))
        if status.installed and status.enabled:
            runner(
                (
                    "systemctl",
                    "--user",
                    "enable",
                    "--now",
                    TIMER_NAME,
                )
            )
        raise

    return (
        "Linux scan timer updated."
        if status.installed
        else "Linux scan timer installed."
    )


def disable_linux_timer(
    *,
    unit_paths: LinuxUnitPaths | None = None,
    command_runner: CommandRunner | None = None,
) -> str:
    paths = unit_paths or default_user_unit_paths()
    status = inspect_linux_timer(
        unit_paths=paths,
        command_runner=command_runner,
    )
    if not status.installed:
        return "Junior's Linux scan timer is not installed."
    runner = command_runner or _run_systemctl
    _require_success(
        runner(("systemctl", "--user", "disable", "--now", TIMER_NAME)),
        "Junior could not disable its Linux scan timer.",
    )
    return "Linux scheduled scans disabled."


def remove_linux_timer(
    *,
    unit_paths: LinuxUnitPaths | None = None,
    command_runner: CommandRunner | None = None,
) -> str:
    paths = unit_paths or default_user_unit_paths()
    status = inspect_linux_timer(
        unit_paths=paths,
        command_runner=command_runner,
    )
    if not status.installed:
        return "Junior's Linux scan timer is not installed."
    runner = command_runner or _run_systemctl
    _require_success(
        runner(("systemctl", "--user", "disable", "--now", TIMER_NAME)),
        "Junior could not stop its Linux scan timer before removal.",
    )
    prior_service = _read_optional_managed(paths.service)
    prior_timer = _read_optional_managed(paths.timer)
    try:
        paths.service.unlink()
        paths.timer.unlink()
        _require_success(
            runner(("systemctl", "--user", "daemon-reload")),
            "Junior could not reload systemd after removing its units.",
        )
    except BaseException:
        _restore_optional(paths.service, prior_service)
        _restore_optional(paths.timer, prior_timer)
        runner(("systemctl", "--user", "daemon-reload"))
        if status.enabled:
            runner(
                (
                    "systemctl",
                    "--user",
                    "enable",
                    "--now",
                    TIMER_NAME,
                )
            )
        raise
    return "Linux scan timer removed."


def render_linux_units(
    schedule: ScanSchedule,
    *,
    user_data_root: str | Path,
    executable: str | Path | None = None,
) -> tuple[str, str]:
    """Render the shared runner for user or administrator-installed systemd."""
    days = ",".join(_SYSTEMD_WEEKDAYS[day] for day in schedule.weekdays)
    run_time = f"{schedule.run_time}:00"
    command = " ".join(
        _quote_systemd_argument(value)
        for value in (
            str(executable or sys.executable),
            "-m",
            "job_radar.scheduled_scan",
            "--user-data-root",
            str(Path(user_data_root).expanduser().resolve()),
        )
    )
    service_text = f"""{MANAGED_MARKER}
[Unit]
Description=Junior scheduled company scan

[Service]
Type=oneshot
ExecStart={command}
"""
    timer_text = f"""{MANAGED_MARKER}
[Unit]
Description=Run Junior's company scan on the saved schedule

[Timer]
OnCalendar={days} *-*-* {run_time}
Persistent=true
Unit={SERVICE_NAME}

[Install]
WantedBy=timers.target
"""
    return service_text, timer_text


def _run_systemctl(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    if shutil.which("systemctl") is None:
        raise LinuxSchedulerError(
            "systemd is unavailable on this Linux installation."
        )
    try:
        return subprocess.run(
            list(command),
            capture_output=True,
            check=False,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise LinuxSchedulerError(
            "Junior could not communicate with the Linux user service manager."
        ) from error


def _quote_systemd_argument(value: str) -> str:
    if "\n" in value or "\r" in value:
        raise LinuxSchedulerError("A scheduling path contains invalid text.")
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _read_optional_managed(path: Path) -> str | None:
    if not path.exists():
        return None
    _require_managed(path)
    return path.read_text(encoding="utf-8")


def _require_managed(path: Path) -> None:
    try:
        with path.open(encoding="utf-8") as stream:
            first_line = stream.readline().rstrip("\r\n")
    except OSError as error:
        raise LinuxSchedulerError(
            f"Junior could not inspect {path.name}."
        ) from error
    if first_line != MANAGED_MARKER:
        raise LinuxSchedulerError(
            f"Junior will not change {path.name} because it was not created "
            "by Junior."
        )


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def _restore_optional(path: Path, text: str | None) -> None:
    if text is None:
        path.unlink(missing_ok=True)
    else:
        _atomic_write(path, text)


def _require_success(result: CompletedCommand, message: str) -> None:
    if result.returncode != 0:
        raise LinuxSchedulerError(message)
