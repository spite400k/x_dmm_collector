"""OpenAI / Anthropic 共通 chat completion クライアント。

既存コードの `client.chat.completions.create(...)` 形を維持しつつ、
`AI_PROVIDER=anthropic` のとき Anthropic Messages API へ振り替える。
戻り値は OpenAI 互換の SimpleNamespace（choices / usage / model）に正規化する。
"""
from __future__ import annotations

import logging
import os
from types import SimpleNamespace
from typing import Any

from openai_api.config import AI_PROVIDER, OPENAI_MODEL

_DEFAULT_ANTHROPIC_MAX_TOKENS = 4096
_JSON_SYSTEM_HINT = (
    "You must respond with a single valid JSON object only. "
    "Do not wrap it in markdown code fences."
)

_openai_client = None
_anthropic_client = None


def _strip_json_fence(text: str) -> str:
    content = (text or "").strip()
    if "```" not in content:
        return content
    json_str = content.split("```", 2)[1]
    if json_str.startswith("json"):
        json_str = json_str[4:]
    return json_str.strip()


def _openai_shaped_response(
    *,
    model: str | None,
    content: str,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
    cached_tokens: int | None = None,
) -> SimpleNamespace:
    usage = SimpleNamespace(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        prompt_tokens_details=SimpleNamespace(cached_tokens=cached_tokens),
    )
    message = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(model=model, usage=usage, choices=[choice])


def _split_system_messages(
    messages: list[dict[str, Any]],
) -> tuple[str | None, list[dict[str, str]]]:
    system_parts: list[str] = []
    converted: list[dict[str, str]] = []
    for msg in messages:
        role = msg.get("role") or "user"
        content = msg.get("content") or ""
        if role == "system":
            system_parts.append(str(content))
            continue
        if role not in ("user", "assistant"):
            role = "user"
        converted.append({"role": role, "content": str(content)})
    system = "\n\n".join(system_parts) if system_parts else None
    return system, converted


def _want_json(response_format: dict | None) -> bool:
    if not isinstance(response_format, dict):
        return False
    return response_format.get("type") == "json_object"


def _get_openai_client():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI

        _openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _openai_client


def _get_anthropic_client():
    global _anthropic_client
    if _anthropic_client is None:
        from anthropic import Anthropic

        _anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _anthropic_client


def _create_openai(
    *,
    model: str,
    messages: list[dict[str, Any]],
    temperature: float | None,
    max_completion_tokens: int | None,
    response_format: dict | None,
) -> Any:
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
    }
    if temperature is not None:
        kwargs["temperature"] = temperature
    if max_completion_tokens is not None:
        kwargs["max_completion_tokens"] = max_completion_tokens
    if response_format is not None:
        kwargs["response_format"] = response_format
    return _get_openai_client().chat.completions.create(**kwargs)


def _anthropic_text(response: Any) -> str:
    parts: list[str] = []
    for block in getattr(response, "content", None) or []:
        block_type = getattr(block, "type", None)
        if block_type is None and isinstance(block, dict):
            block_type = block.get("type")
            text = block.get("text", "")
        else:
            text = getattr(block, "text", "") or ""
        if block_type == "text" and text:
            parts.append(text)
    return "".join(parts)


def _create_anthropic(
    *,
    model: str,
    messages: list[dict[str, Any]],
    temperature: float | None,
    max_completion_tokens: int | None,
    response_format: dict | None,
) -> SimpleNamespace:
    system, converted = _split_system_messages(messages)
    if _want_json(response_format):
        hint = _JSON_SYSTEM_HINT
        system = f"{system}\n\n{hint}" if system else hint
    if not converted:
        converted = [{"role": "user", "content": "(empty)"}]

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": converted,
        "max_tokens": max_completion_tokens or _DEFAULT_ANTHROPIC_MAX_TOKENS,
    }
    if system:
        kwargs["system"] = system
    if temperature is not None:
        kwargs["temperature"] = temperature

    response = _get_anthropic_client().messages.create(**kwargs)
    text = _anthropic_text(response)
    if _want_json(response_format):
        text = _strip_json_fence(text)

    usage = getattr(response, "usage", None)
    prompt_tokens = getattr(usage, "input_tokens", None) if usage else None
    completion_tokens = getattr(usage, "output_tokens", None) if usage else None
    cached_tokens = getattr(usage, "cache_read_input_tokens", None) if usage else None
    total_tokens = None
    if prompt_tokens is not None or completion_tokens is not None:
        total_tokens = (prompt_tokens or 0) + (completion_tokens or 0)

    return _openai_shaped_response(
        model=getattr(response, "model", None) or model,
        content=text,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cached_tokens=cached_tokens,
    )


class _ChatCompletions:
    def create(
        self,
        *,
        model: str | None = None,
        messages: list[dict[str, Any]],
        temperature: float | None = None,
        max_completion_tokens: int | None = None,
        response_format: dict | None = None,
        **_ignored: Any,
    ) -> Any:
        resolved_model = model or OPENAI_MODEL
        if AI_PROVIDER == "anthropic":
            logging.debug("LLM chat via anthropic model=%s", resolved_model)
            return _create_anthropic(
                model=resolved_model,
                messages=messages,
                temperature=temperature,
                max_completion_tokens=max_completion_tokens,
                response_format=response_format,
            )
        logging.debug("LLM chat via openai model=%s", resolved_model)
        return _create_openai(
            model=resolved_model,
            messages=messages,
            temperature=temperature,
            max_completion_tokens=max_completion_tokens,
            response_format=response_format,
        )


class _Chat:
    def __init__(self) -> None:
        self.completions = _ChatCompletions()


class LLMClient:
    """OpenAI SDK 互換の薄いラッパ（chat.completions.create のみ）。"""

    def __init__(self) -> None:
        self.chat = _Chat()


def get_client() -> LLMClient:
    return LLMClient()


def reset_clients() -> None:
    """テスト用: 遅延生成した SDK クライアントを破棄する。"""
    global _openai_client, _anthropic_client
    _openai_client = None
    _anthropic_client = None
