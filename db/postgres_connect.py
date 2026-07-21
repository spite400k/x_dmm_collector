"""Postgres 接続ヘルパー（Supabase / GitHub Actions 向け）。

Supabase の直結ホスト ``db.*.supabase.co:5432`` は IPv6 専用のため、
GitHub Actions など IPv4 のみの環境では ``Network is unreachable`` になる。
GHA では Dashboard の **Session pooler**（``*.pooler.supabase.com``）を使う。
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

import psycopg2
from psycopg2.extensions import connection as PgConnection

_IPV6_UNREACHABLE = re.compile(
    r"network is unreachable|no route to host",
    re.IGNORECASE,
)


def _looks_like_supabase_direct_host(host: str | None) -> bool:
    if not host:
        return False
    return host.startswith("db.") and host.endswith(".supabase.co")


def _ipv6_hint(label: str, host: str | None) -> str:
    return (
        f"{label} 接続失敗: Supabase 直結 (db.*.supabase.co) は IPv6 専用で、"
        f"GitHub Actions 等の IPv4 環境からは到達できません"
        f"（host={host!r}）。"
        f"Dashboard → Connect → Session pooler の接続情報を使い、"
        f"{label}_URL（推奨）または "
        f"host=*.pooler.supabase.com / user=postgres.<project-ref> / port=5432 "
        f"を設定してください。"
    )


def connect_postgres(
    *,
    url: str | None = None,
    host: str | None = None,
    dbname: str | None = None,
    user: str | None = None,
    password: str | None = None,
    port: str | int | None = 5432,
    sslmode: str = "require",
    label: str = "DB",
    autocommit: bool = False,
) -> PgConnection:
    """psycopg2 で接続する。IPv6 到達不可時は対処を含む RuntimeError を送出。"""
    try:
        if url:
            conn = psycopg2.connect(url, sslmode=sslmode)
        else:
            if not host:
                raise RuntimeError(f"{label}_HOST または {label}_URL が未設定です。")
            conn = psycopg2.connect(
                host=host,
                dbname=dbname,
                user=user,
                password=password,
                port=port if port is not None else 5432,
                sslmode=sslmode,
            )
        conn.autocommit = autocommit
        return conn
    except Exception as exc:
        err = str(exc)
        host_for_hint = host
        if url and not host_for_hint:
            host_for_hint = urlparse(url).hostname
        if _IPV6_UNREACHABLE.search(err) or (
            _looks_like_supabase_direct_host(host_for_hint) and "unreachable" in err.lower()
        ):
            logging.error(_ipv6_hint(label, host_for_hint))
            raise RuntimeError(_ipv6_hint(label, host_for_hint)) from exc
        logging.exception("%s接続失敗", label)
        raise


def connect_from_env(
    prefix: str = "DB",
    *,
    host_fallback: Callable[[], str] | None = None,
    default_dbname: str = "postgres",
    default_user: str = "postgres",
    default_port: str | int = 5432,
    label: str | None = None,
) -> PgConnection:
    """``{prefix}_URL`` または ``{prefix}_HOST`` 等から接続する。

    GHA では ``DB_URL`` / ``MESUGAKI_DB_URL`` に Session pooler の URI を推奨。
    """
    display = label or prefix
    url = os.getenv(f"{prefix}_URL")
    if not url and prefix == "DB":
        url = os.getenv("DATABASE_URL")

    host = os.getenv(f"{prefix}_HOST")
    if not host and not url and host_fallback is not None:
        host = host_fallback()

    return connect_postgres(
        url=url,
        host=host,
        dbname=os.getenv(f"{prefix}_NAME", default_dbname),
        user=os.getenv(f"{prefix}_USER", default_user),
        password=os.getenv(f"{prefix}_PASSWORD"),
        port=os.getenv(f"{prefix}_PORT", default_port),
        label=display,
    )


def connection_kwargs_for_tests(**overrides: Any) -> dict[str, Any]:
    """テスト用: デフォルト kwargs を返す。"""
    base: dict[str, Any] = {
        "host": "db.example.supabase.co",
        "dbname": "postgres",
        "user": "postgres",
        "password": "secret",
        "port": 5432,
        "label": "DB",
    }
    base.update(overrides)
    return base
