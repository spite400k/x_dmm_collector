"""Supabase REST API 用 httpx クライアント（DNS/接続エラー向けリトライ）"""

from __future__ import annotations

import httpx
from httpx import Timeout

# Windows 環境で DNS 解決が遅い/不安定な場合に備え、接続リトライと長めのタイムアウトを設定
SUPABASE_HTTP_RETRIES = 5
SUPABASE_CONNECT_TIMEOUT = 60.0
SUPABASE_READ_TIMEOUT = 120.0


def create_supabase_httpx_client() -> httpx.Client:
    transport = httpx.HTTPTransport(retries=SUPABASE_HTTP_RETRIES)
    return httpx.Client(
        transport=transport,
        timeout=Timeout(
            connect=SUPABASE_CONNECT_TIMEOUT,
            read=SUPABASE_READ_TIMEOUT,
            write=30.0,
            pool=30.0,
        ),
    )
