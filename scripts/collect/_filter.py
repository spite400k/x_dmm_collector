"""収集スクリプト共通: 未登録アイテムの抽出。"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date
from typing import Any

from utils.update_items_selection import is_released

from utils.supabase_retry import execute_with_retry


def filter_unregistered_items(
    top_items: list[dict],
    *,
    exists_by_content_id: Callable[[str], bool],
) -> list[dict]:
    """取得済み一覧から content_id 未登録のアイテムだけを返す。

    既存作品や content_id 欠落はスキップし、処理全体は止めない。
    """
    items: list[dict] = []
    for item in top_items:
        content_id = item.get("content_id")
        title = item.get("title")
        url = item.get("URL")

        if not content_id:
            logging.warning("[SKIP] content_id が存在しない: %s : %s", title, url)
            continue
        if exists_by_content_id(str(content_id)):
            logging.info("[SKIP] 既に登録済: %s (%s) : %s", title, content_id, url)
            continue
        items.append(item)
    return items


def filter_released_items(
    items: list[dict],
    *,
    today: date | None = None,
) -> list[dict]:
    """配信済み（release_date <= today）のアイテムだけを返す。"""
    day = today or date.today()
    released: list[dict] = []
    for item in items:
        release_date = item.get("date") or item.get("release_date")
        if is_released(release_date, today=day):
            released.append(item)
            continue
        content_id = item.get("content_id")
        title = item.get("title")
        logging.info("[SKIP] 未配信: %s (%s)", title, content_id)
    return released


def run_items_isolated(
    items: list[dict],
    process_one: Callable[[dict], None],
) -> bool:
    """各アイテムを個別に処理し、1件失敗しても残りを続行する。

    Returns:
        1件でも失敗したら True。
    """
    has_error = False
    for item in items:
        try:
            process_one(item)
        except Exception as e:
            logging.error("登録処理に失敗: %s", str(e))
            has_error = True
    return has_error


def supabase_exists_checker(table_client: Any) -> Callable[[str], bool]:
    """Supabase table client から exists 判定関数を作る。"""

    def _exists(content_id: str) -> bool:
        exists = execute_with_retry(
            lambda: table_client.select("id").eq("content_id", content_id)
        )
        return bool(exists.data)

    return _exists
