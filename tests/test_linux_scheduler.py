"""Verify guarded systemd scheduling using disposable units and fake commands."""

from dataclasses import dataclass
from pathlib import Path

import pytest

from job_radar.linux_scheduler import (
    LinuxSchedulerError,
    LinuxUnitPaths,
    MANAGED_MARKER,
    SERVICE_NAME,
    TIMER_NAME,
    apply_linux_schedule,
    disable_linux_timer,
    inspect_linux_timer,
    remove_linux_timer,
    render_linux_units,
)
from job_radar.schedule_service import ScanSchedule


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


def _paths(tmp_path: Path) -> LinuxUnitPaths:
    directory = tmp_path / "systemd" / "user"
    return LinuxUnitPaths(
        directory=directory,
        service=directory / SERVICE_NAME,
        timer=directory / TIMER_NAME,
    )


def _schedule(*, enabled: bool = True) -> ScanSchedule:
    return ScanSchedule(
        enabled=enabled,
        run_time="07:15",
        weekdays=("monday", "wednesday", "friday") if enabled else (),
        email_delivery=True,
    )


def test_rendered_units_use_shared_runner_and_explicit_data_root(
    tmp_path: Path,
) -> None:
    service, timer = render_linux_units(
        _schedule(),
        user_data_root=tmp_path / "Junior Data",
        executable="/opt/junior/python",
    )

    assert service.startswith(MANAGED_MARKER)
    assert '"/opt/junior/python" "-m" "job_radar.scheduled_scan"' in service
    assert '"--user-data-root"' in service
    assert "Junior Data" in service
    assert timer.startswith(MANAGED_MARKER)
    assert "OnCalendar=Mon,Wed,Fri *-*-* 07:15:00" in timer
    assert "Persistent=true" in timer


def test_apply_installs_only_junior_units_atomically(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    runner = _Runner([_Result(0), _Result(0)])

    message = apply_linux_schedule(
        _schedule(),
        user_data_root=tmp_path / "data",
        unit_paths=paths,
        command_runner=runner,
        executable="/opt/junior/python",
    )

    assert message == "Linux scan timer installed."
    assert paths.service.read_text(encoding="utf-8").startswith(MANAGED_MARKER)
    assert paths.timer.read_text(encoding="utf-8").startswith(MANAGED_MARKER)
    assert runner.commands == [
        ("systemctl", "--user", "daemon-reload"),
        ("systemctl", "--user", "enable", "--now", TIMER_NAME),
    ]
    assert list(paths.directory.glob("*.tmp")) == []


def test_apply_refuses_to_overwrite_unmanaged_unit(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    paths.directory.mkdir(parents=True)
    paths.service.write_text("[Service]\nExecStart=/other/app\n", encoding="utf-8")
    paths.timer.write_text("[Timer]\nOnCalendar=daily\n", encoding="utf-8")

    with pytest.raises(LinuxSchedulerError, match="not created by Junior"):
        apply_linux_schedule(
            _schedule(),
            user_data_root=tmp_path / "data",
            unit_paths=paths,
            command_runner=_Runner([]),
        )

    assert "other/app" in paths.service.read_text(encoding="utf-8")


def test_failed_enable_restores_prior_managed_units(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    paths.directory.mkdir(parents=True)
    old_service = f"{MANAGED_MARKER}\nold service\n"
    old_timer = f"{MANAGED_MARKER}\nold timer\n"
    paths.service.write_text(old_service, encoding="utf-8")
    paths.timer.write_text(old_timer, encoding="utf-8")
    runner = _Runner(
        [
            _Result(0, "enabled"),
            _Result(0),
            _Result(1),
            _Result(0),
            _Result(0),
        ]
    )

    with pytest.raises(
        LinuxSchedulerError,
        match="could not enable",
    ):
        apply_linux_schedule(
            _schedule(),
            user_data_root=tmp_path / "data",
            unit_paths=paths,
            command_runner=runner,
        )

    assert paths.service.read_text(encoding="utf-8") == old_service
    assert paths.timer.read_text(encoding="utf-8") == old_timer


def test_inspect_disable_and_remove_managed_timer(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    service, timer = render_linux_units(
        _schedule(),
        user_data_root=tmp_path / "data",
    )
    paths.directory.mkdir(parents=True)
    paths.service.write_text(service, encoding="utf-8")
    paths.timer.write_text(timer, encoding="utf-8")

    status = inspect_linux_timer(
        unit_paths=paths,
        command_runner=_Runner([_Result(0, "enabled")]),
    )
    disable_runner = _Runner([_Result(0, "enabled"), _Result(0)])
    remove_runner = _Runner(
        [_Result(1, "disabled"), _Result(0), _Result(0)]
    )

    assert status.enabled is True
    assert (
        disable_linux_timer(
            unit_paths=paths,
            command_runner=disable_runner,
        )
        == "Linux scheduled scans disabled."
    )
    assert (
        remove_linux_timer(
            unit_paths=paths,
            command_runner=remove_runner,
        )
        == "Linux scan timer removed."
    )
    assert not paths.service.exists()
    assert not paths.timer.exists()
    assert remove_runner.commands[-1] == (
        "systemctl",
        "--user",
        "daemon-reload",
    )
