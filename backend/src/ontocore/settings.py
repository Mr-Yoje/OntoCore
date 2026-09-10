from __future__ import annotations

import json
from pathlib import Path

DEFAULT_EXTRACTOR = "hybrid"
DEFAULT_MODEL = "openai/gpt-4o-mini"


def load_settings(data_dir: Path) -> dict[str, str]:
    path = data_dir / "settings.json"
    if not path.exists():
        return {"extractor": DEFAULT_EXTRACTOR, "model": DEFAULT_MODEL}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {
        "extractor": str(raw.get("extractor") or DEFAULT_EXTRACTOR),
        "model": str(raw.get("model") or DEFAULT_MODEL),
    }


def save_settings(data_dir: Path, extractor: str, model: str) -> dict[str, str]:
    data = {"extractor": extractor, "model": model}
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "settings.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )
    return data
