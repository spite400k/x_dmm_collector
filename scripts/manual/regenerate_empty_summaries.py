#!/usr/bin/env python3
"""auto_summary / auto_point が空の行を raw_json から再生成する。

収集時と同じ generate_content → Safe 化の順で埋め、成功時は safe_generated_at を立てる。
既存の auto_comment は空のときだけ上書きする。

例:
  .venv\\Scripts\\python.exe scripts/manual/regenerate_empty_summaries.py --dry-run
  .venv\\Scripts\\python.exe scripts/manual/regenerate_empty_summaries.py --limit 3
  .venv\\Scripts\\python.exe scripts/manual/regenerate_empty_summaries.py --content-id 13dsvr01740
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor

from db.postgres_connect import connect_from_env
from db.supabase_client import supabase
from openai_api.content_generator import generate_content
from scripts.process import update_items as update_items_mod
from utils.logger import setup_logger

load_dotenv()
setup_logger("regenerate_empty_summaries.log")


def is_blank(value: str | None) -> bool:
    return not (value or "").strip()


def fetch_empty_summary_rows(
    conn,
    *,
    limit: int | None = None,
    content_id: str | None = None,
) -> list[dict[str, Any]]:
    sql = """
        SELECT content_id, title, auto_comment, auto_summary, auto_point, raw_json
        FROM trn_dmm_items
        WHERE coalesce(auto_summary, '') = ''
          AND coalesce(auto_point, '') = ''
          AND raw_json IS NOT NULL
    """
    params: list[Any] = []
    if content_id:
        sql += " AND content_id = %s"
        params.append(content_id)
    sql += " ORDER BY content_id"
    if limit is not None:
        sql += " LIMIT %s"
        params.append(limit)

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, params)
        return list(cur.fetchall())


def build_update_payload(
    row: dict[str, Any],
    ai_content: dict[str, Any],
    *,
    safe_summary: str,
    safe_point: str,
    safe_ok: bool,
) -> dict[str, Any] | None:
    """更新ペイロードを組む。埋められる項目が無ければ None。"""
    payload: dict[str, Any] = {
        "updated_at": datetime.utcnow().isoformat(),
    }
    has_fill = False

    new_summary = safe_summary if safe_ok else (ai_content.get("auto_summary") or "")
    new_point = safe_point if safe_ok else (ai_content.get("auto_point") or "")

    if is_blank(row.get("auto_summary")) and not is_blank(new_summary):
        payload["auto_summary"] = new_summary
        has_fill = True
    if is_blank(row.get("auto_point")) and not is_blank(new_point):
        payload["auto_point"] = new_point
        has_fill = True
    if is_blank(row.get("auto_comment")):
        comment = (ai_content.get("auto_comment") or "").strip()
        if comment:
            payload["auto_comment"] = comment
            has_fill = True

    if not has_fill:
        return None

    if safe_ok and ("auto_summary" in payload or "auto_point" in payload):
        payload["safe_generated_at"] = datetime.utcnow().isoformat()

    return payload


def regenerate_row(row: dict[str, Any]) -> dict[str, Any] | None:
    raw = row.get("raw_json")
    if not isinstance(raw, dict):
        logging.warning("raw_json が不正: %s", row.get("content_id"))
        return None

    ai_content = generate_content(raw) or {}
    summary_in = ai_content.get("auto_summary") or ""
    point_in = ai_content.get("auto_point") or ""
    if is_blank(summary_in) and is_blank(point_in):
        logging.warning("generate_content が空: %s", row.get("content_id"))
        return None

    title = row.get("title") or raw.get("title") or ""
    safe_summary, safe_point, safe_ok = update_items_mod.generate_safe_summary_point(
        title, summary_in, point_in
    )
    if not safe_ok:
        logging.warning(
            "Safe 化失敗のため generate_content 結果をそのまま保存候補: %s",
            row.get("content_id"),
        )

    return build_update_payload(
        row,
        ai_content,
        safe_summary=safe_summary,
        safe_point=safe_point,
        safe_ok=safe_ok,
    )


def apply_update(content_id: str, payload: dict[str, Any]) -> bool:
    res = (
        supabase.table("trn_dmm_items")
        .update(payload)
        .eq("content_id", content_id)
        .execute()
    )
    return bool(res.data)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="空の auto_summary / auto_point を raw_json から再生成"
    )
    parser.add_argument("--limit", type=int, default=None, help="処理件数上限")
    parser.add_argument("--content-id", default=None, help="単一 content_id のみ")
    parser.add_argument(
        "--sleep",
        type=float,
        default=1.0,
        help="1件ごとの待機秒（デフォルト 1.0）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="対象件数・ID を表示するだけで更新しない",
    )
    args = parser.parse_args()

    conn = connect_from_env("DB")
    try:
        rows = fetch_empty_summary_rows(
            conn, limit=args.limit, content_id=args.content_id
        )
    finally:
        conn.close()

    logging.info("再生成対象: %d 件", len(rows))
    if not rows:
        return

    if args.dry_run:
        preview = [r["content_id"] for r in rows[:20]]
        logging.info(
            "dry-run: 先頭 %s%s",
            preview,
            "..." if len(rows) > 20 else "",
        )
        return

    ok_count = 0
    skip_count = 0
    fail_count = 0

    for i, row in enumerate(rows, start=1):
        cid = row["content_id"]
        logging.info("[%d/%d] %s 再生成中...", i, len(rows), cid)
        try:
            payload = regenerate_row(row)
            if not payload:
                skip_count += 1
                continue
            if apply_update(cid, payload):
                logging.info("更新完了: %s (keys=%s)", cid, sorted(payload.keys()))
                ok_count += 1
            else:
                logging.warning("更新対象なし: %s", cid)
                fail_count += 1
        except Exception:
            logging.exception("再生成失敗: %s", cid)
            fail_count += 1
        time.sleep(args.sleep)

    logging.info(
        "完了: success=%d skip=%d fail=%d / total=%d",
        ok_count,
        skip_count,
        fail_count,
        len(rows),
    )


if __name__ == "__main__":
    main()
