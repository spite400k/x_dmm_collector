"""収集スクリプト共通: 未登録アイテムの抽出。"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any


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


def supabase_exists_checker(table_client: Any) -> Callable[[str], bool]:
    """Supabase table client から exists 判定関数を作る。"""

    def _exists(content_id: str) -> bool:
        exists = table_client.select("id").eq("content_id", content_id).execute()
        return bool(exists.data)

    return _exists
