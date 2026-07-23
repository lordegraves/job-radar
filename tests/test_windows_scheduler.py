"""Verify Junior manages only its named Windows task through mocked commands."""

from dataclasses import dataclass
from pathlib import Path

from job_radar.schedule_service import ScanSchedule
from job_radar.windows_scheduler import (
    JUNIOR_TASK_NAME,
    apply_windows_schedule,
    disable_windows_task,
    inspect_windows_task,
    remove_windows_task,
)


ENABLED_TASK_XML = """<?xml version="1.0"?>
<Task xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Settings><Enabled>true</Enabled></Settings>
</Task>
"""

DISABLED_TASK_XML = """<?xml version="1.0"?>
<Task xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Settings><Enabled>false</Enabled></Settings>
</Task>
"""


@dataclass(frozen=True)
class _Result:
    returncode: int
    stdout: str = ""


class _Runner:
    def __init__(self, results: list[_Result]) -> None:
        self.results = list(results)
        self.commands: list[tuple[str, ...]] = []

    def __call__(self, command):
        self.commands.append(tuple(command))
        return self.results.pop(0)


def test_inspect_reports_missing_task_without_exposing_command_output() -> None:
    runner = _Runner([_Result(1, "private localized scheduler error")])

    status = inspect_windows_task(command_runner=runner)

    assert status.installed is False
    assert status.state == "Not installed"
    assert "private localized scheduler error" not in status.message
    assert runner.commands[0][3] == JUNIOR_TASK_NAME


def test_inspect_reads_enabled_state_from_task_xml() -> None:
    runner = _Runner([_Result(0, DISABLED_TASK_XML)])

    status = inspect_windows_task(command_runner=runner)

    assert status.installed is True
    assert status.enabled is False
    assert status.state == "Installed but disabled"


def test_apply_creates_one_limited_interactive_task() -> None:
    runner = _Runner([_Result(1), _Result(0)])
    schedule = ScanSchedule(
        enabled=True,
        run_time="07:15",
        weekdays=("monday", "wednesday", "friday"),
        email_delivery=True,
    )

    message = apply_windows_schedule(
        schedule,
        command_runner=runner,
        executable=Path(r"C:\Junior\python.exe"),
    )

    create_command = runner.commands[1]
    assert message == "Windows scheduled task installed."
    assert create_command[:4] == (
        "schtasks.exe",
        "/Create",
        "/TN",
        JUNIOR_TASK_NAME,
    )
    assert create_command[create_command.index("/D") + 1] == "MON,WED,FRI"
    assert create_command[create_command.index("/ST") + 1] == "07:15"
    assert "/RL" in create_command
    assert create_command[create_command.index("/RL") + 1] == "LIMITED"
    assert "/IT" in create_command
    assert "/RP" not in create_command
    action = create_command[create_command.index("/TR") + 1]
    assert r"C:\Junior\python.exe" in action
    assert "-m job_radar.scheduled_scan" in action


def test_apply_off_schedule_disables_existing_task() -> None:
    runner = _Runner([_Result(0, ENABLED_TASK_XML), _Result(0)])
    schedule = ScanSchedule(
        enabled=False,
        run_time="09:00",
        weekdays=(),
        email_delivery=False,
    )

    message = apply_windows_schedule(schedule, command_runner=runner)

    assert message == "Windows scheduled scans disabled."
    assert runner.commands[1] == (
        "schtasks.exe",
        "/Change",
        "/TN",
        JUNIOR_TASK_NAME,
        "/Disable",
    )


def test_disable_and_remove_target_only_junior_task() -> None:
    disable_runner = _Runner([_Result(0, ENABLED_TASK_XML), _Result(0)])
    remove_runner = _Runner([_Result(0, ENABLED_TASK_XML), _Result(0)])

    assert (
        disable_windows_task(command_runner=disable_runner)
        == "Windows scheduled scans disabled."
    )
    assert (
        remove_windows_task(command_runner=remove_runner)
        == "Windows scheduled task removed."
    )
    assert disable_runner.commands[-1][3] == JUNIOR_TASK_NAME
    assert disable_runner.commands[-1][-1] == "/Disable"
    assert remove_runner.commands[-1] == (
        "schtasks.exe",
        "/Delete",
        "/TN",
        JUNIOR_TASK_NAME,
        "/F",
    )
