"""Test several company sources in the background without importing jobs."""

import threading
from collections.abc import Callable, Iterable
from typing import Any


class SourceTestRunner:
    """Run one bounded sequential source-test batch while the GUI stays usable."""

    def __init__(self, test_source: Callable[[str], Any]) -> None:
        self._test_source = test_source
        self._lock = threading.Lock()
        self._running = False
        self._completed = 0
        self._total = 0
        self._failed = 0
        self._current: str | None = None

    def start(self, employer_ids: Iterable[str]) -> bool:
        ids = tuple(dict.fromkeys(item for item in employer_ids if item))
        if not ids:
            return False
        with self._lock:
            if self._running:
                return False
            self._running = True
            self._completed = 0
            self._total = len(ids)
            self._failed = 0
            self._current = None
        threading.Thread(
            target=self._run,
            args=(ids,),
            name="junior-source-test-worker",
            daemon=True,
        ).start()
        return True

    def status(self) -> dict[str, object]:
        with self._lock:
            return {
                "running": self._running,
                "completed": self._completed,
                "total": self._total,
                "failed": self._failed,
                "current": self._current,
            }

    def _run(self, employer_ids: tuple[str, ...]) -> None:
        for employer_id in employer_ids:
            with self._lock:
                self._current = employer_id
            failed = False
            try:
                result = self._test_source(employer_id)
                failed = getattr(result, "state", None) != "success"
            except Exception:
                # The connection service owns safe persisted diagnostics.
                failed = True
            with self._lock:
                self._completed += 1
                self._failed += int(failed)
        with self._lock:
            self._current = None
            self._running = False
