from __future__ import annotations

import re
import sys
import traceback
import uuid
from pathlib import Path

from loguru import logger

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


def public_llm_message(raw: str) -> str:
    text = (raw or "").strip() or "联通测试失败"
    low = text.lower()
    if "credential" in low or "api_key" in low or "unauthorized" in low or "401" in low:
        return "密钥无效或未填写，请检查 API Key"
    if "timeout" in low or "timed out" in low:
        return "连接超时，请检查 Base URL 或网络"
    if _looks_like_offline(low):
        return "无法连接服务，请检查网络"
    if "404" in low or "not found" in low:
        return "接口不存在，请检查 Base URL 和模型名称"
    if "429" in low:
        return "请求过于频繁，请稍后再试"
    if _looks_like_dump(text) or not _has_cjk(text):
        return "模型调用失败"
    lines = [line for line in text.splitlines() if "Traceback" not in line and 'File "' not in line]
    cleaned = "\n".join(lines).strip() or "模型调用失败"
    if "OC-" in cleaned or _looks_like_dump(cleaned):
        return "模型调用失败"
    return cleaned[:400]
