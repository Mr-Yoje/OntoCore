from __future__ import annotations

from pathlib import Path


def uploads_dir(data_dir: Path) -> Path:
    path = Path(data_dir) / "uploads"
    path.mkdir(parents=True, exist_ok=True)
    return path


def upload_path(data_dir: Path, job_id: str) -> Path:
    return uploads_dir(data_dir) / job_id


def save_upload(data_dir: Path, job_id: str, data: bytes) -> Path:
    path = upload_path(data_dir, job_id)
    path.write_bytes(data)
    return path


def load_upload(data_dir: Path, job_id: str) -> bytes | None:
    path = upload_path(data_dir, job_id)
    if not path.is_file():
        return None
    return path.read_bytes()
