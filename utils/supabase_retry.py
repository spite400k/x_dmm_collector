"""Supabase REST 呼び出しのリトライ（接続エラー向け）"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TypeVar

import httpx

T = TypeVar("T")

RETRYABLE_ERRORS = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.NetworkError,
    OSError,
)

DEFAULT_RETRIES = 5
DEFAULT_BASE_DELAY = 3.0


def execute_with_retry(
    request_builder: Callable[[], T],
    *,
    retries: int = DEFAULT_RETRIES,
    base_delay: float = DEFAULT_BASE_DELAY,
) -> T:
    """request_builder().execute() を接続エラー時に指数バックオフでリトライする。"""
    last_exc: BaseException | None = None
    for attempt in range(retries):
        try:
            return request_builder().execute()
        except RETRYABLE_ERRORS as exc:
            last_exc = exc
            if attempt >= retries - 1:
                raise
            delay = base_delay * (2**attempt)
            logging.warning(
                "Supabase 接続失敗 (%s)。%.0f 秒後にリトライ (%d/%d)",
                exc,
                delay,
                attempt + 1,
                retries,
            )
            time.sleep(delay)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("execute_with_retry: unreachable")
