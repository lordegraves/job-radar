"""Run one GUI-started scan without blocking the rest of the local app."""

import multiprocessing
import threading
from collections.abc import Callable
from typing import Any


class ScanTaskRunner:
    """Guard and run one scan worker at a time."""

    def __init__(
        self,
        handle_scan: Callable[..., Any],
        *,
        isolate_process: bool = False,
    ) -> None:
        self._handle_scan = handle_scan
        self._isolate_process = isolate_process
        self._lock = threading.Lock()
        self._running = False
        self._failed = False
        self._worker: threading.Thread | None = None
        self._process: multiprocessing.Process | None = None

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._running

    @property
    def failed(self) -> bool:
        with self._lock:
            return self._failed

    def start(self, **scan_arguments: Any) -> bool:
        """Reserve the worker before starting it so rapid clicks cannot race."""
        with self._lock:
            if self._running:
                return False

            self._running = True
            self._failed = False

        if self._isolate_process:
            process = multiprocessing.get_context("spawn").Process(
                target=_run_scan_process,
                args=(self._handle_scan, scan_arguments),
                name="junior-scan-worker",
                daemon=False,
            )
            worker = threading.Thread(
                target=self._monitor_process,
                args=(process,),
                name="junior-scan-monitor",
                daemon=False,
            )
            with self._lock:
                self._process = process
                self._worker = worker
            try:
                process.start()
                worker.start()
            except Exception:
                with self._lock:
                    self._failed = True
                    self._running = False
                    self._process = None
                    self._worker = None
                return False
            return True

        worker = threading.Thread(
            target=self._run,
            kwargs=scan_arguments,
            name="junior-scan-worker",
            daemon=False,
        )
        with self._lock:
            self._worker = worker
        worker.start()
        return True

    def wait(self) -> None:
        """Wait for an active scan to finish its normal durable writes."""
        with self._lock:
            worker = self._worker
        if worker is not None and worker is not threading.current_thread():
            worker.join()

    def _run(self, **scan_arguments: Any) -> None:
        failed = False

        try:
            self._handle_scan(**scan_arguments)
        except Exception:
            # The scan lifecycle records the safe failure details. The worker
            # deliberately does not expose raw exception text to the browser.
            failed = True
        finally:
            with self._lock:
                self._failed = failed
                self._running = False

    def _monitor_process(self, process: multiprocessing.Process) -> None:
        """Translate the child exit code into the existing safe worker state."""

        process.join()
        with self._lock:
            self._failed = process.exitcode != 0
            self._running = False
            self._process = None


def _run_scan_process(
    handle_scan: Callable[..., Any],
    scan_arguments: dict[str, Any],
) -> None:
    """Keep CPU-heavy scoring outside the desktop server's Python process."""

    try:
        handle_scan(**scan_arguments)
    except Exception:
        # The scan lifecycle owns sanitized diagnostics. A nonzero child exit
        # tells the parent only that the protected scan did not finish.
        raise SystemExit(1) from None
