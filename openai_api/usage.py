"""OpenAI chat completion のトークン使用量ログ。"""
import logging
from typing import Any

from openai_api.config import DEFAULT_OPENAI_MODEL, OPENAI_MODEL


def _get(obj: Any, name: str, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _fmt(value: int | None) -> int | str:
    if value is None:
        return "-"
    return value


def log_configured_model() -> None:
    """ジョブ開始時に、実際に使うモデルと既定値を1行出す。"""
    logging.info(
        "OpenAI configured model=%s default=%s",
        OPENAI_MODEL,
        DEFAULT_OPENAI_MODEL,
    )


def log_openai_usage(
    response: Any,
    *,
    purpose: str,
    content_id: str | None = None,
) -> None:
    """response.usage の input / output を作品ごとに1行出す。"""
    usage = _get(response, "usage")
    details = _get(usage, "prompt_tokens_details")
    model = _as_text(_get(response, "model")) or "-"
    label = (content_id or "").strip() or "-"
    logging.info(
        "OpenAI usage purpose=%s content_id=%s model=%s "
        "prompt_tokens=%s completion_tokens=%s total_tokens=%s cached_tokens=%s",
        purpose,
        label,
        model,
        _fmt(_as_int(_get(usage, "prompt_tokens"))),
        _fmt(_as_int(_get(usage, "completion_tokens"))),
        _fmt(_as_int(_get(usage, "total_tokens"))),
        _fmt(_as_int(_get(details, "cached_tokens"))),
    )
