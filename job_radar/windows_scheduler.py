"""Manage Junior's one Windows Task Scheduler entry without stored secrets."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
import getpass
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Protocol
from xml.etree import ElementTree

from job_radar.schedule_service import ScanSchedule


JUNIOR_TASK_NAME = r"\Junior Scheduled Scan"
_WINDOWS_WEEKDAYS = {
    "monday": "MON",
    "tuesday": "TUE",
    "wednesday": "WED",
    "thursday": "THU",
    "friday": "FRI",
    "saturday": "SAT",
    "sunday": "SUN",
}


class WindowsSchedulerError(RuntimeError):
    """Report a safe, actionable Task Scheduler failure."""


class CompletedCommand(Protocol):
    returncode: int
    stdout: str


CommandRunner = Callable[[Sequence[str]], CompletedCommand]


@dataclass(frozen=True)
class WindowsTaskStatus:
    available: bool
    installed: bool
    enabled: bool
    state: str
    message: str


def inspect_windows_task(
    *,
    task_name: str = JUNIOR_TASK_NAME,
    command_runner: CommandRunner | None = None,
) -> WindowsTaskStatus:
    """Inspect only Junior's named task and sanitize command failures."""
    if os.name != "nt" and command_runner is None:
        return WindowsTaskStatus(
            available=False,
            installed=False,
            enabled=False,
            state="Unavailable",
            message="Windows Task Scheduler is available only on Windows.",
        )

    runner = command_runner or _run_schtasks
    result = runner(("schtasks.exe", "/Query", "/TN", task_name, "/XML", "ONE"))
    if result.returncode != 0:
        return WindowsTaskStatus(
            available=True,
            installed=False,
            enabled=False,
            state="Not installed",
            message="Junior's Windows scheduled task is not installed.",
        )

    try:
        root = ElementTree.fromstring(result.stdout)
    except ElementTree.ParseError as error:
        raise WindowsSchedulerError(
            "Windows returned an unreadable task definition. "
            "Remove and recreate Junior's scheduled task."
        ) from error

    enabled_element = root.find(".//{*}Settings/{*}Enabled")
    enabled = (
        enabled_element is None
        or (enabled_element.text or "").strip().casefold() == "true"
    )
    return WindowsTaskStatus(
        available=True,
        installed=True,
        enabled=enabled,
        state="Installed and enabled" if enabled else "Installed but disabled",
        message=(
            "Windows is ready to start Junior on the saved schedule."
            if enabled
            else "The Windows task exists but will not start scans."
        ),
    )


def apply_windows_schedule(
    schedule: ScanSchedule,
    *,
    task_name: str = JUNIOR_TASK_NAME,
    command_runner: CommandRunner | None = None,
    executable: str | Path | None = None,
) -> str:
    """Create/update the task when on, or disable it when the schedule is off."""
    runner = command_runner or _run_schtasks
    existing = inspect_windows_task(
        task_name=task_name,
        command_runner=runner,
    )
    if not schedule.enabled:
        if not existing.installed:
            return "Scheduling is off. No Windows task is installed."
        _require_success(
            runner(("schtasks.exe", "/Change", "/TN", task_name, "/Disable")),
            "Junior could not disable its Windows scheduled task.",
        )
        return "Windows scheduled scans disabled."

    if not schedule.weekdays:
        raise WindowsSchedulerError(
            "Choose at least one weekday before applying the Windows schedule."
        )

    action = subprocess.list2cmdline(
        [
            str(executable or sys.executable),
            "-m",
            "job_radar.scheduled_scan",
        ]
    )
    days = ",".join(_WINDOWS_WEEKDAYS[day] for day in schedule.weekdays)
    username = getpass.getuser()
    _require_success(
        runner(
            (
                "schtasks.exe",
                "/Create",
                "/TN",
                task_name,
                "/TR",
                action,
                "/SC",
                "WEEKLY",
                "/MO",
                "1",
                "/D",
                days,
                "/ST",
                schedule.run_time,
                "/RU",
                username,
                "/RL",
                "LIMITED",
                "/IT",
                "/F",
            )
        ),
        (
            "Junior could not create or update its Windows scheduled task. "
            "Confirm that Task Scheduler is available for your Windows account."
        ),
    )
    return (
        "Windows scheduled task updated."
        if existing.installed
        else "Windows scheduled task installed."
    )


def disable_windows_task(
    *,
    task_name: str = JUNIOR_TASK_NAME,
    command_runner: CommandRunner | None = None,
) -> str:
    runner = command_runner or _run_schtasks
    status = inspect_windows_task(
        task_name=task_name,
        command_runner=runner,
    )
    if not status.installed:
        return "Junior's Windows scheduled task is not installed."
    _require_success(
        runner(("schtasks.exe", "/Change", "/TN", task_name, "/Disable")),
        "Junior could not disable its Windows scheduled task.",
    )
    return "Windows scheduled scans disabled."


def remove_windows_task(
    *,
    task_name: str = JUNIOR_TASK_NAME,
    command_runner: CommandRunner | None = None,
) -> str:
    runner = command_runner or _run_schtasks
    status = inspect_windows_task(
        task_name=task_name,
        command_runner=runner,
    )
    if not status.installed:
        return "Junior's Windows scheduled task is not installed."
    _require_success(
        runner(("schtasks.exe", "/Delete", "/TN", task_name, "/F")),
        "Junior could not remove its Windows scheduled task.",
    )
    return "Windows scheduled task removed."


def _run_schtasks(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    if shutil.which("schtasks.exe") is None:
        raise WindowsSchedulerError(
            "Windows Task Scheduler is unavailable on this computer."
        )
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        return subprocess.run(
            list(command),
            capture_output=True,
            check=False,
            text=True,
            timeout=30,
            creationflags=creation_flags,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise WindowsSchedulerError(
            "Junior could not communicate with Windows Task Scheduler."
        ) from error


def _require_success(result: CompletedCommand, message: str) -> None:
    if result.returncode != 0:
        raise WindowsSchedulerError(message)
