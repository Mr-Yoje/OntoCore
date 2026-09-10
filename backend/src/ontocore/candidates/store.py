from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from typing import Literal

from ontocore.models import (
    ExtractionResult,
    InstanceCandidateStatus,
    TypeCandidateKind,
    TypeCandidateStatus,
)


@dataclass
class StoredTypeCandidate:
    id: str
    kind: TypeCandidateKind
    job_id: str
    status: TypeCandidateStatus
    payload: dict


@dataclass
class StoredInstanceCandidate:
    id: str
    kind: Literal["instance", "instance_rel"]
    job_id: str
    status: InstanceCandidateStatus
    payload: dict


_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS candidates (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    layer TEXT NOT NULL,
    kind TEXT NOT NULL,
    status TEXT NOT NULL,
    payload_json TEXT NOT NULL
)
"""


class CandidateStore:
    def __init__(self, sqlite_path: str) -> None:
        self._path = sqlite_path
        with sqlite3.connect(self._path) as conn:
            conn.execute(_CREATE_TABLE)

    def replace_job_results(self, job_id: str, result: ExtractionResult) -> None:
        rows: list[tuple[str, str, str, str, str, str]] = []
        for item in result.object_candidates:
            rows.append((
                str(uuid.uuid4()), job_id, "type", "object", "proposed",
                json.dumps(asdict(item)),
            ))
        for item in result.attribute_candidates:
            rows.append((
                str(uuid.uuid4()), job_id, "type", "attribute", "proposed",
                json.dumps(asdict(item)),
            ))
        for item in result.relation_candidates:
            rows.append((
                str(uuid.uuid4()), job_id, "type", "relation", "proposed",
                json.dumps(asdict(item)),
            ))
        for item in result.instance_suggestions:
            rows.append((
                str(uuid.uuid4()), job_id, "instance", "instance", "proposed",
                json.dumps(asdict(item)),
            ))
        for item in result.instance_rel_suggestions:
            rows.append((
                str(uuid.uuid4()), job_id, "instance", "instance_rel", "proposed",
                json.dumps(asdict(item)),
            ))
        with sqlite3.connect(self._path) as conn:
            conn.execute("DELETE FROM candidates WHERE job_id = ?", (job_id,))
            if rows:
                conn.executemany(
                    "INSERT INTO candidates "
                    "(id, job_id, layer, kind, status, payload_json) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    rows,
                )

    def list_type_candidates(self, job_id: str) -> list[StoredTypeCandidate]:
        with sqlite3.connect(self._path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT id, job_id, kind, status, payload_json "
                "FROM candidates WHERE job_id = ? AND layer = 'type' "
                "ORDER BY rowid",
                (job_id,),
            )
            return [_row_to_type(row) for row in cur.fetchall()]

    def list_instance_candidates(self, job_id: str) -> list[StoredInstanceCandidate]:
        with sqlite3.connect(self._path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT id, job_id, kind, status, payload_json "
                "FROM candidates WHERE job_id = ? AND layer = 'instance' "
                "ORDER BY rowid",
                (job_id,),
            )
            return [_row_to_instance(row) for row in cur.fetchall()]

    def get_type(self, candidate_id: str) -> StoredTypeCandidate:
        with sqlite3.connect(self._path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT id, job_id, kind, status, payload_json "
                "FROM candidates WHERE id = ? AND layer = 'type'",
                (candidate_id,),
            )
            row = cur.fetchone()
            if row is None:
                raise KeyError(candidate_id)
            return _row_to_type(row)

    def set_type_status(
        self, candidate_id: str, status: TypeCandidateStatus,
    ) -> StoredTypeCandidate:
        with sqlite3.connect(self._path) as conn:
            cur = conn.execute(
                "UPDATE candidates SET status = ? "
                "WHERE id = ? AND layer = 'type'",
                (status, candidate_id),
            )
            if cur.rowcount == 0:
                raise KeyError(candidate_id)
        return self.get_type(candidate_id)

    def set_instance_status(
        self, candidate_id: str, status: InstanceCandidateStatus,
    ) -> StoredInstanceCandidate:
        with sqlite3.connect(self._path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "UPDATE candidates SET status = ? "
                "WHERE id = ? AND layer = 'instance'",
                (status, candidate_id),
            )
            if cur.rowcount == 0:
                raise KeyError(candidate_id)
            row = conn.execute(
                "SELECT id, job_id, kind, status, payload_json "
                "FROM candidates WHERE id = ?",
                (candidate_id,),
            ).fetchone()
        return _row_to_instance(row)


def _row_to_type(row: sqlite3.Row) -> StoredTypeCandidate:
    return StoredTypeCandidate(
        id=row["id"],
        kind=row["kind"],
        job_id=row["job_id"],
        status=row["status"],
        payload=json.loads(row["payload_json"]),
    )


def _row_to_instance(row: sqlite3.Row) -> StoredInstanceCandidate:
    return StoredInstanceCandidate(
        id=row["id"],
        kind=row["kind"],
        job_id=row["job_id"],
        status=row["status"],
        payload=json.loads(row["payload_json"]),
    )
