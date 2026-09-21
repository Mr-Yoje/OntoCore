from __future__ import annotations

import base64
import hashlib
import json
import os
import sqlite3
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken


def list_litellm_prefixes() -> list[str]:
    import litellm

    mapping = getattr(litellm, "models_by_provider", None) or {}
    names = {str(name).strip() for name in mapping if str(name).strip()}
    return sorted(names)


def resolve_litellm_model(prefix: str, model: str) -> str:
    name = (model or "").strip()
    if not name:
        return name
    if "/" in name:
        return name
    head = (prefix or "openai").strip().strip("/")
    return f"{head}/{name}" if head else name


def models_endpoint(api_base: str) -> str:
    base = (api_base or "").strip().rstrip("/")
    if not base:
        raise ValueError("请填写 Base URL")
    if base.endswith("/models"):
        return base
    if base.endswith("/v1"):
        return f"{base}/models"
    return f"{base}/v1/models"


def list_provider_models(api_base: str, api_key: str) -> list[str]:
    url = models_endpoint(api_base)
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
        raise RuntimeError(detail or f"HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(str(exc.reason or exc)) from exc
    rows = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        rows = payload.get("models") if isinstance(payload, dict) else []
    if not isinstance(rows, list):
        raise RuntimeError("模型列表格式无法识别")
    names: list[str] = []
    for item in rows:
        if isinstance(item, str) and item.strip():
            names.append(item.strip())
        elif isinstance(item, dict) and item.get("id"):
            names.append(str(item["id"]).strip())
    unique = sorted({name for name in names if name})
    if not unique:
        raise RuntimeError("模型列表为空")
    return unique


_PROVIDERS_TABLE = """
CREATE TABLE IF NOT EXISTS providers (
    id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    prefix TEXT NOT NULL,
    api_base TEXT NOT NULL,
    api_key_enc TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    sort_order INTEGER NOT NULL
)
"""


def _db_path(data_dir: Path) -> Path:
    return data_dir / "ontocore.db"


def _connect(data_dir: Path) -> sqlite3.Connection:
    data_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_db_path(data_dir))
    conn.execute(_PROVIDERS_TABLE)
    return conn


def _fernet(data_dir: Path) -> Fernet:
    env = (os.environ.get("ONTOCORE_SECRET_KEY") or "").strip()
    if env:
        raw = env.encode("utf-8")
        if len(raw) == 44:
            key = raw
        else:
            key = base64.urlsafe_b64encode(hashlib.sha256(raw).digest())
        return Fernet(key)
    path = data_dir / "master.key"
    if path.exists():
        return Fernet(path.read_bytes().strip())
    key = Fernet.generate_key()
    path.write_bytes(key)
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return Fernet(key)


def _encrypt_key(data_dir: Path, api_key: str) -> str:
    text = (api_key or "").strip()
    if not text:
        return ""
    return _fernet(data_dir).encrypt(text.encode("utf-8")).decode("ascii")


def _decrypt_key(data_dir: Path, blob: str) -> str:
    raw = (blob or "").strip()
    if not raw:
        return ""
    try:
        return _fernet(data_dir).decrypt(raw.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError("无法解密已保存的密钥，请检查主密钥") from exc


def _as_provider(raw: dict[str, Any], *, fallback_key: str = "") -> dict[str, Any]:
    key = raw.get("api_key")
    if key is None or str(key) == "":
        key = fallback_key
    return {
        "id": str(raw.get("id") or uuid.uuid4()),
        "label": str(raw.get("label") or "未命名模型供应商").strip() or "未命名模型供应商",
        "prefix": str(raw.get("prefix") or "openai").strip() or "openai",
        "api_base": str(raw.get("api_base") or "").strip(),
        "api_key": str(key or ""),
        "model": str(raw.get("model") or "").strip(),
    }


def _from_legacy(raw: dict[str, Any]) -> list[dict[str, Any]]:
    if not (raw.get("api_key") or raw.get("api_base") or raw.get("model")):
        return []
    model = str(raw.get("model") or "")
    prefix = "openai"
    if "/" in model:
        prefix = model.split("/", 1)[0] or "openai"
    return [
        _as_provider(
            {
                "id": "default",
                "label": "默认供应商",
                "prefix": prefix,
                "api_base": raw.get("api_base") or "",
                "api_key": raw.get("api_key") or "",
                "model": model.split("/", 1)[-1] if "/" in model else model,
            }
        )
    ]


def _json_providers(data_dir: Path) -> list[dict[str, Any]]:
    path = data_dir / "settings.json"
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return []
    if isinstance(raw.get("providers"), list):
        return [_as_provider(item) for item in raw["providers"] if isinstance(item, dict)]
    return _from_legacy(raw)


def _scrub_settings_json(data_dir: Path) -> None:
    path = data_dir / "settings.json"
    if not path.exists():
        return
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        path.unlink(missing_ok=True)
        return
    if not isinstance(raw, dict):
        path.unlink(missing_ok=True)
        return
    raw.pop("api_key", None)
    if isinstance(raw.get("providers"), list):
        cleaned = []
        for item in raw["providers"]:
            if isinstance(item, dict):
                item = dict(item)
                item.pop("api_key", None)
                cleaned.append(item)
        raw["providers"] = cleaned
    path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")


def _public_provider(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item["id"],
        "label": item["label"],
        "prefix": item["prefix"],
        "api_base": item["api_base"],
        "model": item.get("model") or "",
        "has_api_key": bool(str(item.get("api_key") or "").strip()),
    }


def public_settings(data_dir: Path) -> dict[str, Any]:
    return {"providers": [_public_provider(item) for item in load_settings(data_dir)["providers"]]}


def load_settings(data_dir: Path) -> dict[str, Any]:
    data_dir.mkdir(parents=True, exist_ok=True)
    with _connect(data_dir) as conn:
        conn.row_factory = sqlite3.Row
        rows = list(conn.execute("SELECT * FROM providers ORDER BY sort_order, id"))
        if not rows:
            migrated = _json_providers(data_dir)
            for index, item in enumerate(migrated):
                conn.execute(
                    "INSERT INTO providers (id, label, prefix, api_base, api_key_enc, model, sort_order) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        item["id"],
                        item["label"],
                        item["prefix"],
                        item["api_base"],
                        _encrypt_key(data_dir, item["api_key"]),
                        item["model"],
                        index,
                    ),
                )
            if migrated:
                conn.commit()
                _scrub_settings_json(data_dir)
                rows = list(conn.execute("SELECT * FROM providers ORDER BY sort_order, id"))
        providers = []
        for row in rows:
            providers.append(
                {
                    "id": row["id"],
                    "label": row["label"],
                    "prefix": row["prefix"],
                    "api_base": row["api_base"],
                    "api_key": _decrypt_key(data_dir, row["api_key_enc"]),
                    "model": row["model"],
                }
            )
        return {"providers": providers}


def find_provider(settings: dict[str, Any], provider_id: str | None) -> dict[str, Any] | None:
    if not provider_id:
        return None
    for item in settings.get("providers") or []:
        if item.get("id") == provider_id:
            return item
    return None


def save_settings(data_dir: Path, providers: list[dict[str, Any]]) -> dict[str, Any]:
    current = {item["id"]: item for item in load_settings(data_dir)["providers"]}
    normalized: list[dict[str, Any]] = []
    for raw in providers:
        prev = current.get(str(raw.get("id") or ""))
        fallback = str((prev or {}).get("api_key") or "")
        normalized.append(_as_provider(raw, fallback_key=fallback))
    with _connect(data_dir) as conn:
        conn.execute("DELETE FROM providers")
        for index, item in enumerate(normalized):
            conn.execute(
                "INSERT INTO providers (id, label, prefix, api_base, api_key_enc, model, sort_order) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    item["id"],
                    item["label"],
                    item["prefix"],
                    item["api_base"],
                    _encrypt_key(data_dir, item["api_key"]),
                    item["model"],
                    index,
                ),
            )
        conn.commit()
    _scrub_settings_json(data_dir)
    return public_settings(data_dir)
