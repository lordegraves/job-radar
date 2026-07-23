"""Select the host scheduler while preserving one shared scan workflow."""

from pathlib import Path
import os
import sys

from job_radar.linux_scheduler import (
    LinuxSchedulerError,
    apply_linux_schedule,
    disable_linux_timer,
    inspect_linux_timer,
    remove_linux_timer,
)
from job_radar.schedule_service import (
    ScanSchedule,
    ScheduleIntegrationStatus,
)
from job_radar.windows_scheduler import (
    WindowsSchedulerError,
    apply_windows_schedule,
    disable_windows_task,
    inspect_windows_task,
    remove_windows_task,
)


class SchedulerIntegrationError(RuntimeError):
    """Expose one safe error boundary to the Settings interface."""


def inspect_scheduler() -> ScheduleIntegrationStatus:
    if os.name == "nt":
        return inspect_windows_task()
    if sys.platform == "linux":
        return inspect_linux_timer()
    return ScheduleIntegrationStatus(
        platform_name="Operating system",
        available=False,
        installed=False,
        enabled=False,
        state="Unavailable",
        message="Automatic scheduling is not supported on this operating system.",
    )


def apply_scheduler(
    schedule: ScanSchedule,
    *,
    user_data_root: str | Path,
) -> str:
    try:
        if os.name == "nt":
            return apply_windows_schedule(schedule)
        if sys.platform == "linux":
            return apply_linux_schedule(
                schedule,
                user_data_root=user_data_root,
            )
    except (LinuxSchedulerError, WindowsSchedulerError) as error:
        raise SchedulerIntegrationError(str(error)) from error
    raise SchedulerIntegrationError(
        "Automatic scheduling is not supported on this operating system."
    )


def disable_scheduler() -> str:
    try:
        if os.name == "nt":
            return disable_windows_task()
        if sys.platform == "linux":
            return disable_linux_timer()
    except (LinuxSchedulerError, WindowsSchedulerError) as error:
        raise SchedulerIntegrationError(str(error)) from error
    raise SchedulerIntegrationError(
        "Automatic scheduling is not supported on this operating system."
    )


def remove_scheduler() -> str:
    try:
        if os.name == "nt":
            return remove_windows_task()
        if sys.platform == "linux":
            return remove_linux_timer()
    except (LinuxSchedulerError, WindowsSchedulerError) as error:
        raise SchedulerIntegrationError(str(error)) from error
    raise SchedulerIntegrationError(
        "Automatic scheduling is not supported on this operating system."
    )
