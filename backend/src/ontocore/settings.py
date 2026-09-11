from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any


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


def _as_provider(raw: dict[str, Any], *, fallback_key: str = "") -> dict[str, Any]:
    key = raw.get("api_key")
    if key is None or str(key) == "":
        key = fallback_key
    return {
        "id": str(raw.get("id") or uuid.uuid4()),
        "label": str(raw.get("label") or "未命名供应商").strip() or "未命名供应商",
        "prefix": str(raw.get("prefix") or "openai").strip() or "openai",
        "api_base": str(raw.get("api_base") or "").strip(),
        "api_key": str(key or ""),
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
            }
        )
    ]


def load_settings(data_dir: Path) -> dict[str, Any]:
    path = data_dir / "settings.json"
    if not path.exists():
        return {"providers": []}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return {"providers": []}
    if isinstance(raw.get("providers"), list):
        return {"providers": [_as_provider(item) for item in raw["providers"] if isinstance(item, dict)]}
    return {"providers": _from_legacy(raw)}


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
    data = {"providers": normalized}
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "settings.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return data
