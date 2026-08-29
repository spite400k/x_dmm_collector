import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

"""
メスガキサイト向け: レビューと評価点から AI レビューを作成するバッチ。

接続先は db/supabase_client_mesugaki.py（デフォルト URL: メスガキ用プロジェクト）。
環境変数:
  - MESUGAKI_DB_PASSWORD: 必須（メスガキ DB の postgres パスワード）
  - MESUGAKI_DB_HOST: 任意（省略時は MESUGAKI_SUPABASE_URL から db.{ref}.supabase.co を生成）
  - MESUGAKI_DB_NAME / MESUGAKI_DB_USER / MESUGAKI_DB_PORT: 任意
  - OPENAI_API_KEY: AIレビュー時は必須（--raw-only 時は不要）
  - OPENAI_MODEL: 任意（未設定時は gpt-5.4-nano）
  - DMM_API_ID, DMM_AFFILIATE_ID: 任意（DMM API 利用時）

実行例:
  python scripts/process/create_ai_review_mesugaki.py --raw-only   # 生レビュー保存のみ
"""
import argparse
import hashlib
import logging
import math
import os
import sys
import time
from datetime import date, datetime, timedelta

from openai import OpenAI

import httpx
from db.supabase_client_mesugaki import supabase
from openai_api.config import OPENAI_MODEL
from utils.content_generator_review import (
    AGE_GATE_SYNOPSIS_MARKERS,
    create_driver,
    ensure_driver_alive,
    quit_driver_safe,
    scrape_doujin_synopsis,
    scrape_product_summary,
    scrape_review_comments,
    generate_review_insights,
    usable_saved_summary,
    build_fallback_synopsis,
)
from utils.copy_framework_ab import build_product_context_from_row, enrich_ai_summary_for_ab
from selenium.common.exceptions import InvalidSessionIdException
from utils.logger import setup_logger
from utils.supabase_retry import execute_with_retry

# 対象の service/floor の組み合わせ一覧
targets = [
    {"site": "DMM.R18", "service": "ebook", "floor": "comic"},  # コミック
    {"site": "FANZA", "service": "doujin", "floor": "digital_doujin"},  # 同人誌
]

# ----------------------------------------------------
# 有効なバッチ
# レビューと評価点からAIレビューを作成する（メスガキサイト）
# ----------------------------------------------------
setup_logger("create_ai_review_mesugaki.log")

DMM_API_ID = os.getenv("DMM_API_ID")
DMM_AFFILIATE_ID = os.getenv("DMM_AFFILIATE_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

BATCH_SIZE = 100
SLEEP_BETWEEN_BATCH = 5

# =========================
# ユーティリティ関数
# =========================


def get_saved_summary(content_id):
    result = execute_with_retry(
        lambda: supabase.table("dmm_ai_review_summaries")
        .select("summary_text")
        .eq("content_id", content_id)
        .limit(1)
    )

    if result.data:
        return result.data[0].get("summary_text")

    return None


def has_no_review_changed(content_id: str, new_reviews: list):
    response = execute_with_retry(
        lambda: supabase.table("dmm_raw_reviews")
        .select("review_id")
        .eq("content_id", content_id)
    )

    existing_ids = {r["review_id"] for r in response.data}

    new_ids = {
        generate_review_id(content_id, r["text"]) for r in new_reviews
    }

    unchanged = new_ids == existing_ids
    logging.info(
        "既存レビューID数: %s, 新規レビューID数: %s, 変更なし: %s",
        len(existing_ids),
        len(new_ids),
        unchanged,
    )
    return unchanged


def generate_review_id(content_id: str, text: str) -> str:
    base = content_id + text.strip()
    return hashlib.md5(base.encode("utf-8")).hexdigest()


def save_raw_reviews(content_id: str, reviews):
    clean_reviews = []
    seen = set()

    for r in reviews:
        review_id = generate_review_id(content_id, r["text"])
        key = (content_id, review_id)

        if key in seen:
            continue

        seen.add(key)

        clean_reviews.append(
            {
                "content_id": content_id,
                "review_id": review_id,
                "rating": int(r["rating"]),
                "review_text": r["text"],
                "review_date": r.get("date"),
                "reviewer_name": r.get("reviewer"),
            }
        )

    if not clean_reviews:
        logging.warning("⚠ 有効レビューなし")
        return

    logging.info("保存するレビュー件数: %s 件", len(clean_reviews))
    execute_with_retry(
        lambda: supabase.table("dmm_raw_reviews").upsert(
            clean_reviews, on_conflict="content_id,review_id"
        )
    )

    logging.info("✅ raw_reviews保存完了")


def save_ai_summary(summary: dict):
    response = execute_with_retry(
        lambda: supabase.table("dmm_ai_review_summaries").upsert(
            summary, on_conflict="content_id"
        )
    )

    if response.data is None:
        raise Exception(response.error)

    logging.info("✅ AIレビュー保存完了: %s", summary["content_id"])


def calculate_final_score(summary: dict):
    content = summary.get("content_score") or 0
    emotion = summary.get("emotion_score") or 0
    attraction = summary.get("attraction_score") or 0
    axis1 = summary.get("genre_axis1_score") or 0
    axis2 = summary.get("genre_axis2_score") or 0

    review_count = summary.get("review_count") or 0
    avg_rating = summary.get("avg_rating") or 0

    if review_count <= 0:
        return 0

    common_score = content * 0.25 + emotion * 0.20 + attraction * 0.15
    genre_score = axis1 * 0.20 + axis2 * 0.20
    ai_score = common_score + genre_score

    rating_factor = avg_rating / 5

    max_review = 20
    trust_base = min(
        math.log(review_count + 1) / math.log(max_review + 1),
        1,
    )
    trust_factor = 0.5 + trust_base * 0.5

    final_score = ai_score * rating_factor * trust_factor

    return round(min(final_score, 100), 2)


def save_weekly_score(summary: dict):
    today = datetime.utcnow()
    snapshot_date = today.date().isoformat()

    final_score = calculate_final_score(summary)

    row = {
        "content_id": summary["content_id"],
        "final_score": final_score,
        "review_count": summary["review_count"],
        "avg_rating": summary["avg_rating"],
        "snapshot_date": snapshot_date,
    }

    execute_with_retry(
        lambda: supabase.table("trn_dmm_score_history").upsert(
            row, on_conflict="content_id,snapshot_date"
        )
    )

    logging.info(
        "📊 週次スコア保存完了: %s → %s",
        summary["content_id"],
        final_score,
    )


def process_content(
    content_id: str,
    product_url: str,
    service_code: str,
    floor_code: str,
    driver,
    fallback_summary=None,
    title=None,
    genres=None,
    product_row: dict | None = None,
):
    try:
        logging.info("🔍 処理開始: %s (URL: %s)", content_id, product_url)

        logging.info("🤖 レビュー取得中...")
        reviews = scrape_review_comments(
            product_url, driver, service_code, floor_code
        )
        if not reviews:
            logging.info(
                "⚠ レビューなしでもあらすじとAI分析は行う: %s", content_id
            )

        saved_summary = usable_saved_summary(get_saved_summary(content_id))
        if len(reviews) > 0 and saved_summary and has_no_review_changed(content_id, reviews):
            logging.info("レビュー変更なし → スキップ")
            return

        logging.info("🤖 rawレビュー保存中...")
        save_raw_reviews(content_id, reviews)

        logging.info("🤖 あらすじ取得中...")
        if saved_summary:
            logging.info("既存あらすじ使用")
            html_summary = saved_summary
            if len(reviews) == 0:
                logging.info("レビュー０件、かつあらすじ保存済なのでスキップ")
                return
        else:
            logging.info("初回あらすじ取得")
            if service_code == "doujin" and floor_code == "digital_doujin":
                logging.info("同人誌あらすじ取得（既存ブラウザ）")
                html_summary = scrape_doujin_synopsis(driver, product_url)
            else:
                logging.info("動画あらすじ取得")
                html_summary = scrape_product_summary(product_url, driver)
            html_summary = usable_saved_summary(html_summary)
            if not html_summary:
                html_summary = build_fallback_synopsis(
                    auto_summary=fallback_summary,
                    title=title,
                    genres=genres,
                )
                if html_summary:
                    logging.info(
                        "あらすじスクレイプ失敗 → auto_summary / タイトル / ジャンルを使用"
                    )
            logging.info("初回あらすじ取得: %s", html_summary)
            if not html_summary:
                logging.warning("⚠ あらすじなし → AI生成をスキップ: %s", content_id)
                return

        logging.info("🤖 AIレビュー生成中...")

        avg_rating = round(
            sum(r["rating"] for r in reviews if r["rating"])
            / (len(reviews) if reviews else 1),
            2,
        )

        product_context = build_product_context_from_row(
            product_row
            or {
                "title": title,
                "genres": genres,
            },
            service_code,
            floor_code,
        )

        insight = generate_review_insights(
            reviews=reviews,
            html_summary=html_summary,
            review_avg=avg_rating,
            review_count=len(reviews),
            genre_type=f"{service_code}_{floor_code}",
            product_context=product_context,
        )

        if not insight:
            logging.info("⚠ AI分析失敗 → あらすじとレビュー数のみ保存")
            return

        logging.info("AI分析: %s", insight)

        logging.info("💾 AIレビュー保存中...")
        summary = {
            "content_id": content_id,
            "review_digest": insight.get("review_digest"),
            "content_score": int(insight.get("content_score", 0)),
            "emotion_score": int(insight.get("emotion_score", 0)),
            "attraction_score": int(insight.get("attraction_score", 0)),
            "genre_axis1_score": int(insight.get("genre_axis1_score", 0)),
            "genre_axis2_score": int(insight.get("genre_axis2_score", 0)),
            "reader_types": insight.get("reader_types"),
            "warning_points": insight.get("warning_points"),
            "review_count": len(reviews),
            "avg_rating": avg_rating,
            "summary_text": html_summary,
            "ai_model": OPENAI_MODEL,
            "updated_at": datetime.utcnow().isoformat(),
        }
        enrich_ai_summary_for_ab(summary, insight, content_id)
        save_ai_summary(summary)

        logging.info("💾 週次スコア保存中...")
        save_weekly_score(summary)

        logging.info("🎉 完了: %s", content_id)

    except InvalidSessionIdException:
        raise
    except Exception as e:
        logging.info("❌ エラー: %s", e)


def process_content_raw_only(
    content_id: str,
    product_url: str,
    service_code: str,
    floor_code: str,
    driver,
):
    """スクレイプして dmm_raw_reviews に保存するだけ（AI・あらすじなし）。"""
    try:
        logging.info("🔍 [rawのみ] 処理開始: %s (URL: %s)", content_id, product_url)

        reviews = scrape_review_comments(
            product_url, driver, service_code, floor_code
        )
        if not reviews:
            logging.info("⚠ レビューなし → スキップ: %s", content_id)
            return

        if has_no_review_changed(content_id, reviews):
            logging.info("レビュー変更なし → スキップ: %s", content_id)
            return

        save_raw_reviews(content_id, reviews)
        logging.info("🎉 raw保存完了: %s (%s件)", content_id, len(reviews))

    except InvalidSessionIdException:
        raise
    except Exception as e:
        logging.info("❌ エラー: %s", e)


def _process_item_with_retry(
    driver,
    raw_only: bool,
    content_id: str,
    product_url: str,
    service_code: str,
    floor_code: str,
    fallback_summary=None,
    title=None,
    genres=None,
    product_row: dict | None = None,
):
    """セッション切れ時は driver を再作成して1回リトライする。"""
    for attempt in range(2):
        driver = ensure_driver_alive(driver)
        try:
            if raw_only:
                process_content_raw_only(
                    content_id, product_url, service_code, floor_code, driver
                )
            else:
                process_content(
                    content_id,
                    product_url,
                    service_code,
                    floor_code,
                    driver,
                    fallback_summary=fallback_summary,
                    title=title,
                    genres=genres,
                    product_row=product_row,
                )
            return driver
        except InvalidSessionIdException:
            if attempt == 0:
                logging.warning(
                    "セッション切れ (%s) → driver 再作成してリトライ",
                    content_id,
                )
                quit_driver_safe(driver)
                driver = create_driver()
                continue
            raise
    return driver


def process_batch(batch_items, batch_index, total, raw_only: bool = False):
    logging.info(
        "=== 🧩 バッチ %s 開始 (%s件) [メスガキ] ===",
        batch_index,
        len(batch_items),
    )
    driver = create_driver()
    try:
        for i, row in enumerate(batch_items, start=1):
            content_id = row["content_id"]
            service_code = row["service"]
            floor_code = row["floor"]
            product_url = row["item_url"]
            logging.info(
                "%s週目 [%s/%s] %s 処理中...",
                batch_index,
                i + (batch_index - 1) * BATCH_SIZE,
                total,
                content_id,
            )
            t0 = time.perf_counter()
            driver = _process_item_with_retry(
                driver,
                raw_only,
                content_id,
                product_url,
                service_code,
                floor_code,
                fallback_summary=row.get("auto_summary"),
                title=row.get("title"),
                genres=row.get("genres"),
                product_row=row,
            )
            logging.info(
                "⏱ %s 処理時間: %.1f秒",
                content_id,
                time.perf_counter() - t0,
            )
            time.sleep(0.3)
    finally:
        quit_driver_safe(driver)
    logging.info("=== ✅ バッチ %s 完了 ===", batch_index)


def fetch_all_items():
    all_items = []
    limit = 1000

    for target in targets:
        start = 0
        while True:
            response = execute_with_retry(
                lambda target=target, start=start: supabase.table("trn_dmm_items")
                .select(
                    "content_id, item_url, service, floor, auto_summary, title, "
                    "genres, price, actress, series, maker"
                )
                .eq("service", target["service"])
                .eq("floor", target["floor"])
                .order("created_at")
                .range(start, start + limit - 1)
            )

            data = response.data or []
            logging.info(
                "%s %s 取得件数: %s 件 (start=%s)",
                target["service"],
                target["floor"],
                len(data),
                start,
            )

            if not data:
                break

            all_items.extend(data)
            start += limit

        logging.info("取得済み件数: %s 件", len(all_items))

    return all_items


def fetch_age_gate_items(limit: int | None = None):
    summaries = []
    start = 0
    page = 1000
    or_filter = ",".join(
        f"summary_text.ilike.%{marker}%" for marker in AGE_GATE_SYNOPSIS_MARKERS
    )
    while True:
        response = execute_with_retry(
            lambda start=start: supabase.table("dmm_ai_review_summaries")
            .select("content_id")
            .or_(or_filter)
            .range(start, start + page - 1)
        )
        data = response.data or []
        if not data:
            break
        summaries.extend(data)
        start += page
        if len(data) < page:
            break

    content_ids = [row["content_id"] for row in summaries]
    if limit is not None:
        content_ids = content_ids[:limit]
    logging.info("年齢確認あらすじ件数: %s", len(content_ids))
    if not content_ids:
        return []

    items = []
    chunk_size = 50
    for i in range(0, len(content_ids), chunk_size):
        chunk = content_ids[i : i + chunk_size]
        response = execute_with_retry(
            lambda chunk=chunk: supabase.table("trn_dmm_items")
            .select(
                "content_id, item_url, service, floor, auto_summary, title, "
                "genres, price, actress, series, maker"
            )
            .in_("content_id", chunk)
        )
        items.extend(response.data or [])
    return items


def main():
    parser = argparse.ArgumentParser(
        description="メスガキ向け AI レビュー / 生レビュー保存バッチ",
    )
    parser.add_argument(
        "--raw-only",
        action="store_true",
        help="生レビュー（dmm_raw_reviews）の保存のみ実行（AI・あらすじなし）",
    )
    parser.add_argument(
        "--regenerate-age-gate",
        action="store_true",
        help="年齢確認ページの定型文があらすじとして保存された作品だけ再生成",
    )
    parser.add_argument("--dry-run", action="store_true", help="対象 content_id を表示して終了")
    parser.add_argument("--limit", type=int, default=None, help="処理件数の上限")
    args = parser.parse_args()
    raw_only = args.raw_only

    if raw_only:
        logging.info("=== [メスガキ] 生レビュー保存のみを開始 ===")
    else:
        logging.info("=== [メスガキ] trn_dmm_items の AI レビュー更新を開始 ===")
        missing_env = [
            name
            for name, val in (("OPENAI_API_KEY", OPENAI_API_KEY),)
            if not val
        ]
        if missing_env:
            logging.error("必須環境変数が未設定です: %s", ", ".join(missing_env))
            sys.exit(1)

    try:
        if args.regenerate_age_gate:
            all_items = fetch_age_gate_items(limit=args.limit)
        else:
            all_items = fetch_all_items()
            if args.limit is not None:
                all_items = all_items[: args.limit]
    except httpx.ConnectError as exc:
        logging.error(
            "Supabase への接続に失敗しました。ネットワーク/DNS を確認してください: %s",
            exc,
        )
        sys.exit(1)

    if not all_items:
        logging.info("対象データが存在しません。処理を終了します。")
        sys.exit(0)

    if args.dry_run:
        preview = [row["content_id"] for row in all_items]
        logging.info("dry-run: %s 件 %s", len(preview), preview)
        print("\n".join(preview))
        return

    total = len(all_items)
    mode_label = "生レビュー保存" if raw_only else "AIレビュー更新"
    logging.info("全 %s 件の作品を%s対象として処理します。", total, mode_label)

    update_count = 0

    for i in range(0, total, BATCH_SIZE):
        batch_items = all_items[i : i + BATCH_SIZE]
        batch_index = (i // BATCH_SIZE) + 1

        process_batch(batch_items, batch_index, total, raw_only=raw_only)
        update_count += len(batch_items)

        if i + BATCH_SIZE < total:
            logging.info(
                "⏸ %s秒待機中（次のバッチまで）...", SLEEP_BETWEEN_BATCH
            )
            time.sleep(SLEEP_BETWEEN_BATCH)

    logging.info(
        "🎉 [メスガキ] %sが完了しました。%s 件処理しました。",
        mode_label,
        update_count,
    )


if __name__ == "__main__":
    main()
