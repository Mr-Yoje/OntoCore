from __future__ import annotations

import re
import sys
import traceback
import uuid
from pathlib import Path
from typing import Literal

from loguru import logger

from ontocore.error_catalog import fault_detail

KIND_BUSINESS = "business"
KIND_SYSTEM = "system"


def new_request_id() -> str:
    return uuid.uuid4().hex[:12]


def configure_logging(data_dir: str | Path) -> None:
    root = Path(data_dir)
    log_dir = root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(
        sys.stderr,
        level="INFO",
        backtrace=True,
        diagnose=False,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {message}",
    )
    logger.add(
        str(log_dir / "ontocore_{time:YYYY-MM-DD}.log"),
        rotation="00:00",
        retention="14 days",
        encoding="utf-8",
        level="DEBUG",
        backtrace=True,
        diagnose=False,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {message}",
    )


def log_fault(
    *,
    code: str,
    kind: str,
    detail: str,
    request_id: str | None = None,
    exc: BaseException | None = None,
) -> None:
    rid = request_id or "-"
    message = f"{code} kind={kind} request_id={rid} {detail}"
    if exc is not None:
        stack = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        logger.opt(exception=exc).error(message)
        logger.error(stack)
    else:
        logger.error(message)


def fault_body(*, detail: str, code: str, kind: str, request_id: str) -> dict:
    return {"detail": detail, "code": code, "kind": kind, "request_id": request_id}


_DUMP_MARKERS = (
    "traceback",
    'file "',
    "litellm",
    "internalservererror",
    "openaiexception",
    "openaierror",
    "rel=",
    "data:image",
    "<!doctype",
    "<html",
    "<head",
    "<body",
    "<script",
    "href=",
)
_EXCEPTION_CLASS = re.compile(r"(?:[A-Za-z_][\w.]*Error|[A-Za-z_][\w.]*Exception)\b")


def _has_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


def _looks_like_offline(low: str) -> bool:
    return any(
        marker in low
        for marker in (
            "connection",
            "connect",
            "name or service not known",
            "getaddrinfo",
            "errno 11001",
            "winerror 10051",
            "winerror 10065",
            "unreachable",
            "network is down",
            "failed to resolve",
            "nodename nor servname",
            "failed to fetch",
            "networkerror",
            "offline",
        )
    )


def _looks_like_dump(text: str) -> bool:
    low = text.lower()
    if any(marker in low for marker in _DUMP_MARKERS):
        return True
    if "<" in text and ">" in text:
        return True
    return _EXCEPTION_CLASS.search(text) is not None


_PROVIDER_CODES = {
    "settings": {
        "auth": "OC-5004",
        "timeout": "OC-5005",
        "offline": "OC-5006",
        "not_found": "OC-5007",
        "rate": "OC-5008",
        "other": "OC-5009",
    },
    "job": {
        "auth": "OC-3102",
        "timeout": "OC-3104",
        "offline": "OC-3105",
        "not_found": "OC-3106",
        "rate": "OC-3107",
        "other": "OC-3101",
    },
}


def map_provider_fault(raw: str, *, domain: Literal["settings", "job"]) -> str:
    text = (raw or "").strip()
    low = text.lower()
    codes = _PROVIDER_CODES[domain]
    if "credential" in low or "api_key" in low or "unauthorized" in low or "401" in low:
        return codes["auth"]
    if "timeout" in low or "timed out" in low:
        return codes["timeout"]
    if _looks_like_offline(low):
        return codes["offline"]
    if "404" in low or "not found" in low:
        return codes["not_found"]
    if "429" in low:
        return codes["rate"]
    return codes["other"]


def public_llm_message(raw: str, *, domain: Literal["settings", "job"] = "settings") -> str:
    return fault_detail(map_provider_fault(raw, domain=domain))
