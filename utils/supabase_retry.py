"""接続エラー向けのリトライ（Supabase REST / S3 など）"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TypeVar

import httpx

T = TypeVar("T")

try:
    from botocore.exceptions import (
        ConnectionClosedError,
        ConnectTimeoutError,
        EndpointConnectionError,
        ReadTimeoutError as BotoReadTimeoutError,
    )
except ImportError:  # pragma: no cover
    _BOTOCORE_RETRYABLE: tuple[type[BaseException], ...] = ()
else:
    _BOTOCORE_RETRYABLE = (
        ConnectionClosedError,
        ConnectTimeoutError,
        EndpointConnectionError,
        BotoReadTimeoutError,
    )

RETRYABLE_ERRORS = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.NetworkError,
    httpx.RemoteProtocolError,
    OSError,
) + _BOTOCORE_RETRYABLE

DEFAULT_RETRIES = 5
DEFAULT_BASE_DELAY = 3.0


def call_with_retry(
    fn: Callable[[], T],
    *,
    retries: int = DEFAULT_RETRIES,
    base_delay: float = DEFAULT_BASE_DELAY,
    log_label: str = "接続",
) -> T:
    """接続エラー時に指数バックオフで fn() をリトライする。"""
    last_exc: BaseException | None = None
    for attempt in range(retries):
        try:
            return fn()
        except RETRYABLE_ERRORS as exc:
            last_exc = exc
            if attempt >= retries - 1:
                raise
            delay = base_delay * (2**attempt)
            logging.warning(
                "%s失敗 (%s)。%.0f 秒後にリトライ (%d/%d)",
                log_label,
                exc,
                delay,
                attempt + 1,
                retries,
            )
            time.sleep(delay)
    if last_exc is not None:  # pragma: no cover — for ループ内で raise 済みの防御コード
        raise last_exc
    raise RuntimeError("call_with_retry: unreachable")


def execute_with_retry(
    request_builder: Callable[[], T],
    *,
    retries: int = DEFAULT_RETRIES,
    base_delay: float = DEFAULT_BASE_DELAY,
) -> T:
    """request_builder().execute() を接続エラー時に指数バックオフでリトライする。"""
    return call_with_retry(
        lambda: request_builder().execute(),
        retries=retries,
        base_delay=base_delay,
        log_label="Supabase 接続",
    )
