from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ontocore.models import JobStatus

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    extractor TEXT NOT NULL,
    model TEXT NOT NULL,
    status TEXT NOT NULL,
    error TEXT,
    created_at TEXT NOT NULL DEFAULT '',
    progress_done INTEGER NOT NULL DEFAULT 0,
    progress_total INTEGER NOT NULL DEFAULT 0
)
"""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    embed_provider_id: str | None = None
    error_kind: str | None = None
    guide_object_iris: list[str] = field(default_factory=list)
    guide_relation_iris: list[str] = field(default_factory=list)
    guide_instance_iris: list[str] = field(default_factory=list)
    created_at: str = ""
    progress_done: int = 0
    progress_total: int = 0


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
            if "embed_provider_id" not in cols:
                conn.execute("ALTER TABLE jobs ADD COLUMN embed_provider_id TEXT")
            if "error_kind" not in cols:
                conn.execute("ALTER TABLE jobs ADD COLUMN error_kind TEXT")
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
            if "created_at" not in cols:
                conn.execute("ALTER TABLE jobs ADD COLUMN created_at TEXT NOT NULL DEFAULT ''")
                now = _utc_now_iso()
                conn.execute(
                    "UPDATE jobs SET created_at = ? WHERE created_at = '' OR created_at IS NULL",
                    (now,),
                )
            if "progress_done" not in cols:
                conn.execute(
                    "ALTER TABLE jobs ADD COLUMN progress_done INTEGER NOT NULL DEFAULT 0",
                )
            if "progress_total" not in cols:
                conn.execute(
                    "ALTER TABLE jobs ADD COLUMN progress_total INTEGER NOT NULL DEFAULT 0",
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
        embed_provider_id: str | None = None,
        error_kind: str | None = None,
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
            embed_provider_id=embed_provider_id or None,
            error_kind=error_kind or None,
            guide_object_iris=guide_object_iris or [],
            guide_relation_iris=guide_relation_iris or [],
            guide_instance_iris=guide_instance_iris or [],
            created_at=_utc_now_iso(),
            progress_done=0,
            progress_total=0,
        )
        with sqlite3.connect(self._path) as conn:
            conn.execute(
                "INSERT INTO jobs (id, filename, extractor, model, status, error, provider_id, thinking, "
                "embed_model, embed_provider_id, error_kind, guide_object_iris, guide_relation_iris, "
                "guide_instance_iris, created_at, progress_done, progress_total) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                    job.embed_provider_id,
                    job.error_kind,
                    json.dumps(job.guide_object_iris),
                    json.dumps(job.guide_relation_iris),
                    json.dumps(job.guide_instance_iris),
                    job.created_at,
                    job.progress_done,
                    job.progress_total,
                ),
            )
        return job

    def get(self, job_id: str) -> Job:
        with sqlite3.connect(self._path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT id, filename, extractor, model, status, error, provider_id, thinking, "
                "embed_model, embed_provider_id, error_kind, guide_object_iris, guide_relation_iris, "
                "guide_instance_iris, created_at, progress_done, progress_total "
                "FROM jobs WHERE id = ?",
                (job_id,),
            )
            row = cur.fetchone()
            if row is None:
                raise KeyError(job_id)
            return _row_to_job(row)

    def list_jobs(self) -> list[Job]:
        with sqlite3.connect(self._path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT id, filename, extractor, model, status, error, provider_id, thinking, "
                "embed_model, embed_provider_id, error_kind, guide_object_iris, guide_relation_iris, "
                "guide_instance_iris, created_at, progress_done, progress_total "
                "FROM jobs ORDER BY created_at DESC",
            )
            return [_row_to_job(row) for row in cur.fetchall()]

    def set_progress(self, job_id: str, done: int, total: int) -> Job:
        with sqlite3.connect(self._path) as conn:
            cur = conn.execute(
                "UPDATE jobs SET progress_done = ?, progress_total = ? WHERE id = ?",
                (done, total, job_id),
            )
            if cur.rowcount == 0:
                raise KeyError(job_id)
        return self.get(job_id)

    def update(
        self,
        job_id: str,
        *,
        filename: str | None = None,
        model: str,
        provider_id: str,
        thinking: bool = False,
        embed_model: str,
        embed_provider_id: str,
        guide_object_iris: list[str] | None = None,
        guide_relation_iris: list[str] | None = None,
        guide_instance_iris: list[str] | None = None,
    ) -> Job:
        job = self.get(job_id)
        new_filename = filename if filename is not None else job.filename
        with sqlite3.connect(self._path) as conn:
            cur = conn.execute(
                "UPDATE jobs SET filename = ?, model = ?, provider_id = ?, thinking = ?, "
                "embed_model = ?, embed_provider_id = ?, guide_object_iris = ?, "
                "guide_relation_iris = ?, guide_instance_iris = ? WHERE id = ?",
                (
                    new_filename,
                    model,
                    provider_id,
                    1 if thinking else 0,
                    embed_model,
                    embed_provider_id,
                    json.dumps(guide_object_iris or []),
                    json.dumps(guide_relation_iris or []),
                    json.dumps(
                        guide_instance_iris
                        if guide_instance_iris is not None
                        else job.guide_instance_iris
                    ),
                    job_id,
                ),
            )
            if cur.rowcount == 0:
                raise KeyError(job_id)
        return self.get(job_id)

    def set_status(
        self,
        job_id: str,
        status: JobStatus,
        error: str | None = None,
        error_kind: str | None = None,
    ) -> Job:
        with sqlite3.connect(self._path) as conn:
            cur = conn.execute(
                "UPDATE jobs SET status = ?, error = ?, error_kind = ? WHERE id = ?",
                (status, error, error_kind, job_id),
            )
            if cur.rowcount == 0:
                raise KeyError(job_id)
        return self.get(job_id)

    def fail_interrupted_jobs(self, *, error: str, error_kind: str = "business") -> int:
        with sqlite3.connect(self._path) as conn:
            cur = conn.execute(
                "UPDATE jobs SET status = ?, error = ?, error_kind = ? "
                "WHERE status IN ('running', 'extracting', 'merging', 'aligning')",
                ("failed", error, error_kind),
            )
            return int(cur.rowcount)


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
    embed_provider_id = row["embed_provider_id"] if "embed_provider_id" in keys else None
    if embed_provider_id == "":
        embed_provider_id = None
    error_kind = row["error_kind"] if "error_kind" in keys else None
    if error_kind == "":
        error_kind = None
    created_at = row["created_at"] if "created_at" in keys and row["created_at"] is not None else ""
    progress_done = int(row["progress_done"]) if "progress_done" in keys and row["progress_done"] is not None else 0
    progress_total = (
        int(row["progress_total"]) if "progress_total" in keys and row["progress_total"] is not None else 0
    )
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
        embed_provider_id=embed_provider_id,
        error_kind=error_kind,
        guide_object_iris=_load_iris(row, keys, "guide_object_iris"),
        guide_relation_iris=_load_iris(row, keys, "guide_relation_iris"),
        guide_instance_iris=_load_iris(row, keys, "guide_instance_iris"),
        created_at=created_at,
        progress_done=progress_done,
        progress_total=progress_total,
    )
