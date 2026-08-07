"""Verify clean shutdown can wait for a synthetic background scan."""

from pathlib import Path
import threading

from job_radar.scan_task_runner import ScanTaskRunner


def _write_process_marker(marker_path: str) -> None:
    Path(marker_path).write_text("finished", encoding="utf-8")


def test_wait_blocks_until_background_scan_finishes() -> None:
    release = threading.Event()
    completed: list[bool] = []

    def fake_scan() -> None:
        release.wait(timeout=2)
        completed.append(True)

    runner = ScanTaskRunner(fake_scan)
    assert runner.start()
    release.set()

    runner.wait()

    assert completed == [True]
    assert not runner.is_running


def test_process_worker_finishes_outside_the_server_process(tmp_path: Path) -> None:
    marker = tmp_path / "scan-finished.txt"
    runner = ScanTaskRunner(_write_process_marker, isolate_process=True)

    assert runner.start(marker_path=str(marker))
    runner.wait()

    assert marker.read_text(encoding="utf-8") == "finished"
    assert not runner.is_running
    assert not runner.failed
