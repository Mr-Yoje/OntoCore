from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, field

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
    embed_model: str | None = None
    guide_object_iris: list[str] = field(default_factory=list)
    guide_relation_iris: list[str] = field(default_factory=list)
    guide_instance_iris: list[str] = field(default_factory=list)


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
            if "embed_model" not in cols:
                conn.execute("ALTER TABLE jobs ADD COLUMN embed_model TEXT")
            if "guide_object_iris" not in cols:
                conn.execute(
                    "ALTER TABLE jobs ADD COLUMN guide_object_iris TEXT NOT NULL DEFAULT '[]'",
                )
            if "guide_relation_iris" not in cols:
                conn.execute(
                    "ALTER TABLE jobs ADD COLUMN guide_relation_iris TEXT NOT NULL DEFAULT '[]'",
                )
            if "guide_instance_iris" not in cols:
                conn.execute(
                    "ALTER TABLE jobs ADD COLUMN guide_instance_iris TEXT NOT NULL DEFAULT '[]'",
                )

    def create(
        self,
        filename: str,
        extractor: str,
        model: str,
        *,
        provider_id: str | None = None,
        thinking: bool = False,
        embed_model: str | None = None,
        guide_object_iris: list[str] | None = None,
        guide_relation_iris: list[str] | None = None,
        guide_instance_iris: list[str] | None = None,
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
            embed_model=embed_model or None,
            guide_object_iris=guide_object_iris or [],
            guide_relation_iris=guide_relation_iris or [],
            guide_instance_iris=guide_instance_iris or [],
        )
        with sqlite3.connect(self._path) as conn:
            conn.execute(
                "INSERT INTO jobs (id, filename, extractor, model, status, error, provider_id, thinking, "
                "embed_model, guide_object_iris, guide_relation_iris, guide_instance_iris) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    job.id,
                    job.filename,
                    job.extractor,
                    job.model,
                    job.status,
                    job.error,
                    job.provider_id,
                    1 if job.thinking else 0,
                    job.embed_model,
                    json.dumps(job.guide_object_iris),
                    json.dumps(job.guide_relation_iris),
                    json.dumps(job.guide_instance_iris),
                ),
            )
        return job

    def get(self, job_id: str) -> Job:
        with sqlite3.connect(self._path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT id, filename, extractor, model, status, error, provider_id, thinking, "
                "embed_model, guide_object_iris, guide_relation_iris, guide_instance_iris "
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


def _load_iris(row: sqlite3.Row, keys: list[str], column: str) -> list[str]:
    if column not in keys or row[column] is None:
        return []
    return json.loads(row[column])


def _row_to_job(row: sqlite3.Row) -> Job:
    keys = row.keys()
    thinking = bool(row["thinking"]) if "thinking" in keys and row["thinking"] is not None else False
    provider_id = row["provider_id"] if "provider_id" in keys else None
    embed_model = row["embed_model"] if "embed_model" in keys else None
    if embed_model == "":
        embed_model = None
    return Job(
        id=row["id"],
        filename=row["filename"],
        extractor=row["extractor"],
        model=row["model"],
        status=row["status"],
        error=row["error"],
        provider_id=provider_id,
        thinking=thinking,
        embed_model=embed_model,
        guide_object_iris=_load_iris(row, keys, "guide_object_iris"),
        guide_relation_iris=_load_iris(row, keys, "guide_relation_iris"),
        guide_instance_iris=_load_iris(row, keys, "guide_instance_iris"),
    )
