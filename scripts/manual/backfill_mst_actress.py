#!/usr/bin/env python3
"""trn_dmm_items.actress_ids にあって mst_actress に無い女優を補完する。"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor

from db.postgres_connect import connect_from_env
from scripts.process.update_items import upsert_actresses
from utils.logger import setup_logger

load_dotenv()
setup_logger("backfill_mst_actress.log")


def fetch_missing_actresses(conn, *, limit: int | None) -> list[dict]:
    """未登録 ID と、作品 JSON から取れる name/ruby を返す。"""
    sql = """
        WITH exploded AS (
            SELECT
                (id_text.value)::integer AS actress_id,
                NULLIF(aelem->>'name', '') AS name,
                NULLIF(aelem->>'ruby', '') AS ruby
            FROM trn_dmm_items c
            CROSS JOIN LATERAL jsonb_array_elements_text(
                CASE
                    WHEN c.actress_ids IS NOT NULL
                         AND btrim(c.actress_ids) NOT IN ('', '[]')
                    THEN c.actress_ids::jsonb
                    WHEN c.actress IS NOT NULL
                         AND btrim(c.actress::text) NOT IN ('', '[]', 'null')
                    THEN COALESCE(
                        (
                            SELECT jsonb_agg(x->>'id')
                            FROM jsonb_array_elements(c.actress::jsonb) AS x
                            WHERE (x->>'id') ~ '^[0-9]+$'
                        ),
                        '[]'::jsonb
                    )
                    ELSE '[]'::jsonb
                END
            ) AS id_text(value)
            LEFT JOIN LATERAL jsonb_array_elements(
                CASE
                    WHEN c.actress IS NOT NULL
                         AND btrim(c.actress::text) NOT IN ('', '[]', 'null')
                    THEN c.actress::jsonb
                    ELSE '[]'::jsonb
                END
            ) AS aelem ON (aelem->>'id') = id_text.value
            WHERE id_text.value ~ '^[0-9]+$'
        ),
        named AS (
            SELECT
                actress_id,
                MAX(name) AS name,
                MAX(ruby) AS ruby
            FROM exploded
            GROUP BY actress_id
        )
        SELECT n.actress_id, n.name, n.ruby
        FROM named n
        LEFT JOIN mst_actress m ON m.actress_id = n.actress_id
        WHERE m.actress_id IS NULL
        ORDER BY n.actress_id
    """
    if limit is not None:
        sql += " LIMIT %s"
        params: tuple = (limit,)
    else:
        params = ()

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, params)
        return list(cur.fetchall())


def repair_actress_ids_from_actress_json(conn) -> int:
    """actress カラムから actress_ids が空の行を埋める。"""
    sql = """
        UPDATE trn_dmm_items c
        SET actress_ids = sub.ids_text,
            updated_at = NOW()
        FROM (
            SELECT
                content_id,
                (
                    SELECT jsonb_agg(aelem->>'id')::text
                    FROM jsonb_array_elements(c2.actress::jsonb) AS aelem
                    WHERE (aelem->>'id') ~ '^[0-9]+$'
                ) AS ids_text
            FROM trn_dmm_items c2
            WHERE (c2.actress_ids IS NULL OR btrim(c2.actress_ids) IN ('', '[]'))
              AND c2.actress IS NOT NULL
              AND btrim(c2.actress::text) NOT IN ('', '[]', 'null')
        ) sub
        WHERE c.content_id = sub.content_id
          AND sub.ids_text IS NOT NULL
          AND sub.ids_text <> '[]'
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        return cur.rowcount


def main() -> None:
    parser = argparse.ArgumentParser(description="mst_actress 未登録 ID を DMM API から補完")
    parser.add_argument("--limit", type=int, default=None, help="処理件数上限（検証用）")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="対象 ID を表示するだけで upsert しない",
    )
    args = parser.parse_args()

    conn = connect_from_env("DB")
    try:
        repaired = repair_actress_ids_from_actress_json(conn)
        conn.commit()
        logging.info("actress_ids 補完 UPDATE: %d 件", repaired)
        missing = fetch_missing_actresses(conn, limit=args.limit)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    logging.info("未登録 actress_id: %d 件", len(missing))
    if not missing:
        return

    actresses = [
        {"id": row["actress_id"], "name": row.get("name"), "ruby": row.get("ruby")}
        for row in missing
    ]
    if args.dry_run:
        preview = [a["id"] for a in actresses[:20]]
        logging.info("dry-run: 先頭 %s%s", preview, "..." if len(actresses) > 20 else "")
        return

    upsert_actresses(actresses)
    logging.info("upsert 完了: %d 件", len(actresses))


if __name__ == "__main__":
    main()
