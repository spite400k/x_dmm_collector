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

from db.supabase_client_mesugaki import supabase
from utils.content_generator_review import (
    create_driver,
    ensure_driver_alive,
    quit_driver_safe,
    scrape_doujin_synopsis,
    scrape_product_summary,
    scrape_review_comments,
    generate_review_insights,
)
from selenium.common.exceptions import InvalidSessionIdException
from utils.logger import setup_logger

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
    result = (
        supabase.table("dmm_ai_review_summaries")
        .select("summary_text")
        .eq("content_id", content_id)
        .limit(1)
        .execute()
    )

    if result.data:
        return result.data[0].get("summary_text")

    return None


def has_no_review_changed(content_id: str, new_reviews: list):
    response = (
        supabase.table("dmm_raw_reviews")
        .select("review_id")
        .eq("content_id", content_id)
        .execute()
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
    supabase.table("dmm_raw_reviews").upsert(
        clean_reviews, on_conflict="content_id,review_id"
    ).execute()

    logging.info("✅ raw_reviews保存完了")


def save_ai_summary(summary: dict):
    response = supabase.table("dmm_ai_review_summaries").upsert(
        summary, on_conflict="content_id"
    ).execute()

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

    supabase.table("trn_dmm_score_history").upsert(
        row, on_conflict="content_id,snapshot_date"
    ).execute()

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

        if len(reviews) > 0 and has_no_review_changed(content_id, reviews):
            logging.info("レビュー変更なし → スキップ")
            return

        logging.info("🤖 rawレビュー保存中...")
        save_raw_reviews(content_id, reviews)

        logging.info("🤖 あらすじ取得中...")
        saved_summary = get_saved_summary(content_id)
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
            logging.info("初回あらすじ取得: %s", html_summary)

        logging.info("🤖 AIレビュー生成中...")

        avg_rating = round(
            sum(r["rating"] for r in reviews if r["rating"])
            / (len(reviews) if reviews else 1),
            2,
        )

        insight = generate_review_insights(
            reviews=reviews,
            html_summary=html_summary,
            review_avg=avg_rating,
            review_count=len(reviews),
            genre_type=f"{service_code}_{floor_code}",
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
            "ai_model": "gpt-5.4-nano",
            "prompt_version": "v3_structured",
            "updated_at": datetime.utcnow().isoformat(),
        }
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
                    content_id, product_url, service_code, floor_code, driver
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
            response = (
                supabase.table("trn_dmm_items")
                .select("content_id, item_url,service,floor")
                .eq("service", target["service"])
                .eq("floor", target["floor"])
                # .gte("release_date", release_date)
                .order("created_at")
                .range(start, start + limit - 1)
                .execute()
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


def main():
    parser = argparse.ArgumentParser(
        description="メスガキ向け AI レビュー / 生レビュー保存バッチ",
    )
    parser.add_argument(
        "--raw-only",
        action="store_true",
        help="生レビュー（dmm_raw_reviews）の保存のみ実行（AI・あらすじなし）",
    )
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

    all_items = fetch_all_items()

    if not all_items:
        logging.info("対象データが存在しません。処理を終了します。")
        sys.exit(0)

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
