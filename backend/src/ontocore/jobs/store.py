from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass

from ontocore.models import JobStatus

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    extractor TEXT NOT NULL,
    model TEXT NOT NULL,
    status TEXT NOT NULL,
    error TEXT
)
"""


@dataclass
class Job:
    id: str
    filename: str
    extractor: str
    model: str
    status: JobStatus
    error: str | None


class JobStore:
    def __init__(self, sqlite_path: str) -> None:
        self._path = sqlite_path
        with sqlite3.connect(self._path) as conn:
            conn.execute(_CREATE_TABLE)

    def create(self, filename: str, extractor: str, model: str) -> Job:
        job = Job(
            id=str(uuid.uuid4()),
            filename=filename,
            extractor=extractor,
            model=model,
            status="queued",
            error=None,
        )
        with sqlite3.connect(self._path) as conn:
            conn.execute(
                "INSERT INTO jobs (id, filename, extractor, model, status, error) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (job.id, job.filename, job.extractor, job.model, job.status, job.error),
            )
        return job

    def get(self, job_id: str) -> Job:
        with sqlite3.connect(self._path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT id, filename, extractor, model, status, error FROM jobs WHERE id = ?",
                (job_id,),
            )
            row = cur.fetchone()
            if row is None:
                raise KeyError(job_id)
            return _row_to_job(row)

    def set_status(
        self, job_id: str, status: JobStatus, error: str | None = None,
    ) -> Job:
        with sqlite3.connect(self._path) as conn:
            cur = conn.execute(
                "UPDATE jobs SET status = ?, error = ? WHERE id = ?",
                (status, error, job_id),
            )
            if cur.rowcount == 0:
                raise KeyError(job_id)
        return self.get(job_id)


def _row_to_job(row: sqlite3.Row) -> Job:
    return Job(
        id=row["id"],
        filename=row["filename"],
        extractor=row["extractor"],
        model=row["model"],
        status=row["status"],
        error=row["error"],
    )
