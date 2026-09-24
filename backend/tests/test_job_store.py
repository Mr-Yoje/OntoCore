"""JobStore: created_at, progress fields, list_jobs."""

from __future__ import annotations

import sqlite3
import time

from ontocore.jobs.store import JobStore


def test_create_sets_created_at_and_zero_progress(tmp_path):
    store = JobStore(str(tmp_path / "j.db"))
    job = store.create("a.txt", "llm", "m1")
    assert isinstance(job.created_at, str)
    assert job.created_at != ""
    assert job.progress_done == 0
    assert job.progress_total == 0
    loaded = store.get(job.id)
    assert loaded.created_at == job.created_at
    assert loaded.progress_done == 0
    assert loaded.progress_total == 0


def test_list_jobs_newest_first(tmp_path):
    store = JobStore(str(tmp_path / "j.db"))
    first = store.create("a.txt", "llm", "m1")
    time.sleep(0.02)
    second = store.create("b.txt", "llm", "m1")
    listed = store.list_jobs()
    assert [j.id for j in listed] == [second.id, first.id]


def test_update_job_fields(tmp_path):
    store = JobStore(str(tmp_path / "j.db"))
    job = store.create(
        "a.txt",
        "llm",
        "m1",
        provider_id="p1",
        embed_model="e1",
        embed_provider_id="p1",
        guide_object_iris=["o1"],
    )
    updated = store.update(
        job.id,
        filename="b.txt",
        model="m2",
        provider_id="p2",
        thinking=True,
        embed_model="e2",
        embed_provider_id="p2",
        guide_object_iris=["o2"],
        guide_relation_iris=["r1"],
    )
    assert updated.filename == "b.txt"
    assert updated.model == "m2"
    assert updated.provider_id == "p2"
    assert updated.thinking is True
    assert updated.embed_model == "e2"
    assert updated.embed_provider_id == "p2"
    assert updated.guide_object_iris == ["o2"]
    assert updated.guide_relation_iris == ["r1"]
    assert updated.status == "queued"


def test_migrate_adds_created_at_and_progress_columns(tmp_path):
    db = str(tmp_path / "legacy.db")
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            CREATE TABLE jobs (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                extractor TEXT NOT NULL,
                model TEXT NOT NULL,
                status TEXT NOT NULL,
                error TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO jobs (id, filename, extractor, model, status, error) "
            "VALUES ('legacy-1', 'old.txt', 'llm', 'm1', 'queued', NULL)"
        )
    store = JobStore(db)
    with sqlite3.connect(db) as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(jobs)")}
    assert "created_at" in cols
    assert "progress_done" in cols
    assert "progress_total" in cols
    job = store.get("legacy-1")
    assert job.progress_done == 0
    assert job.progress_total == 0
    assert isinstance(job.created_at, str)
