#!/usr/bin/env python3
"""tachiyomi_url があるが画像未取得の行を後埋めする。

候補:
  tachiyomi_url IS NOT NULL
  AND COALESCE(tachiyomi_page_count, 0) = 0
  AND COALESCE(tachiyomi_capture_fail_count, 0) < 3

- S3 に既にあれば件数だけ同期
- 空なら capture → upload → tachiyomi_page_count を UPDATE
- キャプチャ失敗時は fail_count を +1。3 回で後埋め対象外
- --sync-only なら S3 同期のみ（キャプチャしない）

例:
  .venv\\Scripts\\python.exe scripts/process/backfill_tachiyomi.py --dry-run
  .venv\\Scripts\\python.exe scripts/process/backfill_tachiyomi.py --limit 20
  .venv\\Scripts\\python.exe scripts/process/backfill_tachiyomi.py --sync-only --limit 200
  .venv\\Scripts\\python.exe scripts/process/backfill_tachiyomi.py --db supabase3 --limit 10
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dotenv import load_dotenv

from db.storageS3 import (
    S3_BUCKET,
    S3_BUCKET_3,
    count_objects_under_prefix,
    upload_local_image_to_s3,
    upload_local_image_to_s3_bucket3,
)
from db.supabase_client import supabase, supabase2, supabase3
from utils.get_tachiyomi import TachiyomiCaptureSession, capture_all_tachiyomi_pages
from utils.logger import setup_logger
from utils.supabase_retry import call_with_retry, execute_with_retry

load_dotenv()
setup_logger("backfill_tachiyomi.log")

UploadFn = Callable[..., str | None]

DB_CHOICES = ("default", "supabase2", "supabase3")
CAPTURE_FAIL_THRESHOLD = 3


def resolve_db_target(name: str) -> tuple[Any, UploadFn, str | None]:
    if name == "default":
        return supabase, upload_local_image_to_s3, S3_BUCKET
    if name == "supabase2":
        if supabase2 is None:
            raise RuntimeError("SUPABASE_URL2 / SUPABASE_KEY2 が未設定です")
        return supabase2, upload_local_image_to_s3, S3_BUCKET
    if name == "supabase3":
        if supabase3 is None:
            raise RuntimeError("SUPABASE_URL3 / SUPABASE_KEY3 が未設定です")
        return supabase3, upload_local_image_to_s3_bucket3, S3_BUCKET_3
    raise ValueError(f"unknown db target: {name}")


def fetch_pending_tachiyomi_rows(
    client: Any,
    *,
    limit: int,
    content_id: str | None = None,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """未取得かつ失敗回数が閾値未満、tachiyomi_url ありの行を取得する。"""
    query = (
        client.table("trn_dmm_items")
        .select(
            "id,content_id,title,floor,tachiyomi_url,"
            "tachiyomi_page_count,tachiyomi_capture_fail_count"
        )
        .not_.is_("tachiyomi_url", "null")
        .neq("tachiyomi_url", "")
        .or_("tachiyomi_page_count.is.null,tachiyomi_page_count.eq.0")
        .or_(
            "tachiyomi_capture_fail_count.is.null,"
            f"tachiyomi_capture_fail_count.lt.{CAPTURE_FAIL_THRESHOLD}"
        )
        .order("content_id")
        .range(offset, offset + limit - 1)
    )
    if content_id:
        query = query.eq("content_id", content_id)
    result = execute_with_retry(lambda: query)
    return list(result.data or [])


def update_tachiyomi_fields(
    client: Any,
    content_id: str,
    fields: dict[str, Any],
) -> bool:
    result = execute_with_retry(
        lambda: client.table("trn_dmm_items")
        .update(fields)
        .eq("content_id", content_id)
    )
    return bool(result.data)


def record_capture_failure(
    client: Any,
    content_id: str,
    current_fail_count: Any,
) -> int:
    """失敗回数を +1。閾値到達で後埋め対象外になる。"""
    new_count = int(current_fail_count or 0) + 1
    update_tachiyomi_fields(
        client,
        content_id,
        {
            "tachiyomi_page_count": 0,
            "tachiyomi_capture_fail_count": new_count,
        },
    )
    if new_count >= CAPTURE_FAIL_THRESHOLD:
        logging.warning(
            "[ABANDON] キャプチャ失敗 %d 回到達 → 後埋め対象外: %s",
            new_count,
            content_id,
        )
    else:
        logging.warning(
            "[FAIL-COUNT] %s fail_count=%d/%d",
            content_id,
            new_count,
            CAPTURE_FAIL_THRESHOLD,
        )
    return new_count


def upload_tachiyomi_paths(
    paths: list[str],
    *,
    content_id: str,
    floor: str,
    upload_fn: UploadFn,
) -> int:
    uploaded = 0
    for idx, path in enumerate(paths):
        url = call_with_retry(
            lambda p=path, i=idx: upload_fn(
                p, content_id=content_id, index=i + 1, floor=floor
            ),
            log_label="S3 アップロード",
        )
        if url:
            uploaded += 1
        else:
            logging.error("[IMG-FAIL] %s idx=%d path=%s", content_id, idx + 1, path)
    return uploaded


def cleanup_local_files(paths: list[str]) -> None:
    for path in paths:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        except OSError as exc:
            logging.warning("一時ファイル削除失敗 %s: %s", path, exc)


def process_one_row(
    row: dict[str, Any],
    *,
    client: Any,
    upload_fn: UploadFn,
    bucket: str | None,
    dry_run: bool,
    sync_only: bool = False,
    session: TachiyomiCaptureSession | None = None,
) -> str:
    """1件処理。戻り値: synced | captured | skipped | failed"""
    content_id = row.get("content_id")
    floor = row.get("floor") or ""
    tachiyomi_url = row.get("tachiyomi_url")
    title = row.get("title") or ""
    fail_count = row.get("tachiyomi_capture_fail_count")

    if not content_id or not tachiyomi_url:
        logging.warning("[SKIP] content_id / tachiyomi_url 不足: %s", row)
        return "skipped"
    if not floor:
        logging.warning("[SKIP] floor 未設定: %s", content_id)
        return "skipped"

    existing = count_objects_under_prefix(
        floor, content_id, bucket=bucket
    )
    if existing > 0:
        logging.info(
            "[SYNC] S3 既存 %d 件 → page_count 更新: %s (%s)",
            existing,
            title,
            content_id,
        )
        if not dry_run:
            if not update_tachiyomi_fields(
                client,
                content_id,
                {
                    "tachiyomi_page_count": existing,
                    "tachiyomi_capture_fail_count": 0,
                },
            ):
                return "failed"
        return "synced"

    if sync_only:
        logging.info("[SKIP] S3 空のため sync-only でスキップ: %s (%s)", title, content_id)
        return "skipped"

    logging.info("[CAPTURE] 開始: %s (%s)", title, content_id)
    if dry_run:
        return "captured"

    paths = capture_all_tachiyomi_pages(tachiyomi_url, session=session)
    try:
        if not paths:
            logging.warning("[EMPTY] キャプチャ 0 件: %s", content_id)
            record_capture_failure(client, content_id, fail_count)
            return "failed"

        uploaded = upload_tachiyomi_paths(
            paths,
            content_id=content_id,
            floor=floor,
            upload_fn=upload_fn,
        )
        if uploaded <= 0:
            logging.error("[FAIL] アップロード 0 件: %s", content_id)
            record_capture_failure(client, content_id, fail_count)
            return "failed"

        if not update_tachiyomi_fields(
            client,
            content_id,
            {
                "tachiyomi_page_count": uploaded,
                "tachiyomi_capture_fail_count": 0,
            },
        ):
            return "failed"
        logging.info("[OK] %s page_count=%d", content_id, uploaded)
        return "captured"
    finally:
        cleanup_local_files(paths)


def run_backfill(
    *,
    db_name: str,
    limit: int,
    dry_run: bool,
    content_id: str | None = None,
    sync_only: bool = False,
    offset: int = 0,
) -> int:
    client, upload_fn, bucket = resolve_db_target(db_name)
    rows = fetch_pending_tachiyomi_rows(
        client, limit=limit, content_id=content_id, offset=offset
    )
    logging.info(
        "候補 %d 件 (db=%s limit=%d offset=%d dry_run=%s sync_only=%s)",
        len(rows),
        db_name,
        limit,
        offset,
        dry_run,
        sync_only,
    )

    counts = {"synced": 0, "captured": 0, "skipped": 0, "failed": 0}
    has_error = False
    with TachiyomiCaptureSession() as session:
        for row in rows:
            try:
                status = process_one_row(
                    row,
                    client=client,
                    upload_fn=upload_fn,
                    bucket=bucket,
                    dry_run=dry_run,
                    sync_only=sync_only,
                    session=session,
                )
                counts[status] = counts.get(status, 0) + 1
                if status == "failed":
                    has_error = True
            except Exception as exc:
                has_error = True
                counts["failed"] += 1
                cid = row.get("content_id")
                logging.exception("登録処理に失敗: %s (%s)", cid, exc)
                if cid and not dry_run:
                    try:
                        record_capture_failure(
                            client, cid, row.get("tachiyomi_capture_fail_count")
                        )
                    except Exception:
                        logging.exception("fail_count 更新にも失敗: %s", cid)

    logging.info(
        "完了 synced=%d captured=%d skipped=%d failed=%d",
        counts["synced"],
        counts["captured"],
        counts["skipped"],
        counts["failed"],
    )
    return 1 if has_error else 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="立ち読み画像の後埋め")
    parser.add_argument(
        "--db",
        choices=DB_CHOICES,
        default="default",
        help="対象 DB（default / supabase2 / supabase3）",
    )
    parser.add_argument("--limit", type=int, default=20, help="処理上限件数")
    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="候補の開始オフセット（sync-only で CAPTURE 行を飛ばすとき用）",
    )
    parser.add_argument("--dry-run", action="store_true", help="更新・キャプチャしない")
    parser.add_argument(
        "--sync-only",
        action="store_true",
        help="S3 既存分の件数同期のみ（キャプチャしない）",
    )
    parser.add_argument("--content-id", default=None, help="特定 content_id のみ")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if args.limit < 1:
        logging.error("--limit は 1 以上である必要があります")
        sys.exit(2)
    if args.offset < 0:
        logging.error("--offset は 0 以上である必要があります")
        sys.exit(2)
    code = run_backfill(
        db_name=args.db,
        limit=args.limit,
        dry_run=args.dry_run,
        content_id=args.content_id,
        sync_only=args.sync_only,
        offset=args.offset,
    )
    sys.exit(code)


if __name__ == "__main__":
    main()
