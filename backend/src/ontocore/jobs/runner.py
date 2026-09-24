from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Callable


class JobRunner:
    """Runs JobService.run in-process via a thread pool (or inline when sync=True)."""

    def __init__(
        self,
        run_job: Callable[[str, str, bytes], object] | None = None,
        *,
        sync: bool = False,
        max_workers: int = 4,
    ) -> None:
        self._run_job = run_job
        self._sync = sync
        self._pool: ThreadPoolExecutor | None = None if sync else ThreadPoolExecutor(max_workers=max_workers)

    def bind(self, run_job: Callable[[str, str, bytes], object]) -> None:
        self._run_job = run_job

    def submit(self, job_id: str, filename: str, data: bytes) -> None:
        if self._run_job is None:
            raise RuntimeError("JobRunner has no run_job bound")
        if self._sync:
            self._run_job(job_id, filename, data)
            return
        assert self._pool is not None
        self._pool.submit(self._run_job, job_id, filename, data)
