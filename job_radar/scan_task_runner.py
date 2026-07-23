"""Run one GUI-started scan without blocking the rest of the local app."""

import threading
from collections.abc import Callable
from typing import Any


class ScanTaskRunner:
    """Guard and run one in-process scan worker at a time."""

    def __init__(self, handle_scan: Callable[..., Any]) -> None:
        self._handle_scan = handle_scan
        self._lock = threading.Lock()
        self._running = False
        self._failed = False
        self._worker: threading.Thread | None = None

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
