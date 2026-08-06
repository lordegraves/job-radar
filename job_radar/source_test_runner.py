"""Test several company sources in the background without importing jobs."""

import threading
from collections.abc import Callable, Iterable
from typing import Any


class SourceTestRunner:
    """Run one bounded sequential source-test batch while the GUI stays usable."""

    def __init__(
        self,
        test_source: Callable[[str], Any],
        *,
        record_unexpected_failure: Callable[[str, str], None] | None = None,
    ) -> None:
        self._test_source = test_source
        self._record_unexpected_failure = record_unexpected_failure
        self._lock = threading.Lock()
        self._running = False
        self._completed = 0
        self._total = 0
        self._failed = 0
        self._current: str | None = None
        self._current_label: str | None = None
        self._current_step: str | None = None
        self._labels: dict[str, str] = {}
        self._results: list[dict[str, object]] = []

    def start(
        self,
        employer_ids: Iterable[str],
        *,
        labels: dict[str, str] | None = None,
    ) -> bool:
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
            self._current_label = None
            self._current_step = "Preparing the source test queue."
            self._labels = dict(labels or {})
            self._results = []
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
                "current_label": self._current_label,
                "current_step": self._current_step,
                "results": tuple(dict(item) for item in self._results),
            }

    def _run(self, employer_ids: tuple[str, ...]) -> None:
        for employer_id in employer_ids:
            with self._lock:
                self._current = employer_id
                self._current_label = self._labels.get(employer_id, employer_id)
                self._current_step = (
                    "Connecting to the public recruiting source and checking "
                    "whether Junior can read current jobs."
                )
            failed = False
            message = "Junior could not test this source safely."
            job_count: int | None = None
            tested_at: str | None = None
            try:
                result = self._test_source(employer_id)
                failed = getattr(result, "state", None) != "success"
                message = (
                    getattr(result, "message", None)
                    or "The source test finished without a detailed result."
                )
                job_count = getattr(result, "job_count", None)
                tested_at = getattr(result, "tested_at", None)
            except Exception as error:
                # Never expose exception text: it can contain a private URL or
                # response. The exception class and employer ID are sufficient
                # to distinguish a Junior worker/database problem from a
                # recruiting source that genuinely rejected the request.
                failed = True
                error_type = type(error).__name__
                if self._record_unexpected_failure is not None:
                    self._record_unexpected_failure(employer_id, error_type)
                message = (
                    "Junior's source test stopped unexpectedly, so no source-"
                    "health conclusion was reached. Open Diagnostics and "
                    "download the error log if this continues."
                )
            with self._lock:
                self._completed += 1
                self._failed += int(failed)
                self._results.append(
                    {
                        "employer_id": employer_id,
                        "employer_name": self._labels.get(employer_id, employer_id),
                        "state": "failed" if failed else "success",
                        "message": message,
                        "job_count": job_count,
                        "tested_at": tested_at,
                    }
                )
        with self._lock:
            self._current = None
            self._current_label = None
            self._current_step = (
                "Testing finished with source failures."
                if self._failed
                else "Testing finished successfully."
            )
            self._running = False
