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
    provider_id: str | None = None
    thinking: bool = False


class JobStore:
    def __init__(self, sqlite_path: str) -> None:
        self._path = sqlite_path
        with sqlite3.connect(self._path) as conn:
            conn.execute(_CREATE_TABLE)
            cols = {row[1] for row in conn.execute("PRAGMA table_info(jobs)")}
            if "provider_id" not in cols:
                conn.execute("ALTER TABLE jobs ADD COLUMN provider_id TEXT")
            if "thinking" not in cols:
                conn.execute("ALTER TABLE jobs ADD COLUMN thinking INTEGER NOT NULL DEFAULT 0")

    def create(
        self,
        filename: str,
        extractor: str,
        model: str,
        *,
        provider_id: str | None = None,
        thinking: bool = False,
    ) -> Job:
        job = Job(
            id=str(uuid.uuid4()),
            filename=filename,
            extractor=extractor,
            model=model,
            status="queued",
            error=None,
            provider_id=provider_id,
            thinking=thinking,
        )
        with sqlite3.connect(self._path) as conn:
            conn.execute(
                "INSERT INTO jobs (id, filename, extractor, model, status, error, provider_id, thinking) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    job.id,
                    job.filename,
                    job.extractor,
                    job.model,
                    job.status,
                    job.error,
                    job.provider_id,
                    1 if job.thinking else 0,
                ),
            )
        return job

    def get(self, job_id: str) -> Job:
        with sqlite3.connect(self._path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT id, filename, extractor, model, status, error, provider_id, thinking "
                "FROM jobs WHERE id = ?",
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
    keys = row.keys()
    thinking = bool(row["thinking"]) if "thinking" in keys and row["thinking"] is not None else False
    provider_id = row["provider_id"] if "provider_id" in keys else None
    return Job(
        id=row["id"],
        filename=row["filename"],
        extractor=row["extractor"],
        model=row["model"],
        status=row["status"],
        error=row["error"],
        provider_id=provider_id,
        thinking=thinking,
    )
