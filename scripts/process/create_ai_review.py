import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import json
import math
import os
import sys
import time
import logging
from datetime import date, datetime, timedelta
from openai import OpenAI  # ← ★追加

from db.supabase_client import supabase
from openai_api.content_generator import scrape_product_details
from utils.content_generator_review import (
    create_driver,
    scrape_review_comments,
    scrape_product_summary,
    generate_review_insights
)
from utils.logger import setup_logger
import hashlib

from utils.screenshot import save_debug_files

# 対象の service/floor の組み合わせ一覧
targets = [
    {"site": "DMM.R18", "service": "ebook", "floor": "comic"}, # コミック
    {"site": "FANZA", "service": "doujin", "floor": "digital_doujin"}, # 同人誌
    {"site": "FANZA", "service": "digital", "floor": "videoc"}, # 動画 素人
    {"site": "DMM.R18", "service": "digital", "floor": "videoa"}, # ビデオ
    # {"site": "DMM.R18", "service": "digital", "floor": "anime"}, # アニメ
    # {"site": "FANZA", "service": "ebook", "floor": "novel"}, # 美少女ノベル・官能小説
    # {"site": "FANZA", "service": "ebook", "floor": "photo"}, # アダルト写真集・雑誌
    # {"site": "FANZA", "service": "pcgame", "floor": "digital_pcgame"}, # アダルトPCゲーム
]

#----------------------------------------------------
# 有効なバッチ
# レビューと評価点からAIレビューを作成する
#----------------------------------------------------
setup_logger("create_ai_review.log")

DMM_API_ID = os.getenv("DMM_API_ID")
DMM_AFFILIATE_ID = os.getenv("DMM_AFFILIATE_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # ★追加
client = OpenAI(api_key=OPENAI_API_KEY)       # ★追加

BATCH_SIZE = 100
SLEEP_BETWEEN_BATCH = 5

# =========================
# ユーティリティ関数
# =========================

# 既存のあらすじ取得
def get_saved_summary(content_id):
    result = supabase.table("dmm_ai_review_summaries")\
        .select("summary_text")\
        .eq("content_id", content_id)\
        .limit(1)\
        .execute()

    if result.data:
        return result.data[0].get("summary_text")

    return None

# レビュー変更チェック
def has_no_review_changed(content_id: str, new_reviews: list):

    response = supabase.table("dmm_raw_reviews") \
        .select("review_id") \
        .eq("content_id", content_id) \
        .execute()

    existing_ids = {r["review_id"] for r in response.data}

    new_ids = {
        hashlib.md5(r["text"].encode()).hexdigest()
        for r in new_reviews
    }

    logging.info(f"既存レビューID数: {len(existing_ids)}, 新規レビューID数: {len(new_ids)}")
    logging.info(f"レビュー変更チェック trueは変更なし、falseは変更あり: {len(existing_ids) == len(new_ids)}")
    return len(new_ids) == len(existing_ids)


def generate_review_id(content_id: str, text: str) -> str:
    base = content_id + text.strip()
    return hashlib.md5(base.encode("utf-8")).hexdigest()

# ==============================
# ③ 生レビュー保存
# ==============================

def save_raw_reviews(content_id: str, reviews):

    clean_reviews = []
    seen = set()

    for r in reviews:

        review_id = generate_review_id(content_id, r["text"])

        key = (content_id, review_id)

        if key in seen:
            continue

        seen.add(key)

        clean_reviews.append({
            "content_id": content_id,
            "review_id": review_id,
            "rating": int(r["rating"]),
            "review_text": r["text"],
            "review_date": r.get("date"),
            "reviewer_name": r.get("reviewer")
        })


    if not clean_reviews:
        logging.warning("⚠ 有効レビューなし")
        return

    logging.info(f"保存するレビュー件数: {len(clean_reviews)} 件")
    supabase.table("dmm_raw_reviews") \
        .upsert(clean_reviews, on_conflict="content_id,review_id") \
        .execute()

    logging.info("✅ raw_reviews保存完了")


# ==============================
# ⑦ AI結果保存
# ==============================

def save_ai_summary(summary: dict):
    response = supabase.table("dmm_ai_review_summaries") \
        .upsert(summary, on_conflict="content_id") \
        .execute()

    if response.data is None:
        raise Exception(response.error)

    logging.info(f"✅ AIレビュー保存完了: {summary['content_id']}")


# =========================
# 🎯 メイン処理
# =========================

def process_content(content_id: str, product_url: str, service_code: str, floor_code: str):

    driver = create_driver()

    try:
        logging.info("🔍 処理開始: %s (URL: %s)", content_id, product_url)

        # ① レビュー取得
        logging.info("🤖 レビュー取得中...")
        reviews = scrape_review_comments(product_url, driver, service_code, floor_code)
        if not reviews:
            logging.info("⚠ レビューなしでもあらすじとAI分析は行う: %s", content_id)
            # return  # レビューなしでもあらすじとAI分析は行うため、ここではreturnしない
        
        # logging.info(f"レビュー: {len(reviews)}件")

        # ② 変更チェック
        # logging.info("🤖 レビュー変更チェック中...")
        # logging.info(f"レビュー件数: {len(reviews)}件")
        # logging.info(f"content_id: {content_id}")
        # logging.info(f"レビュー変更チェック結果: {has_no_review_changed(content_id, reviews)}")
        if len(reviews) > 0 and has_no_review_changed(content_id, reviews):
            logging.info("レビュー変更なし → スキップ")
            return

        # ③ raw保存
        logging.info("🤖 rawレビュー保存中...")
        save_raw_reviews(content_id, reviews)

        # ④ あらすじ取得
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
            # save_debug_files(driver, product_url, prefix="summary")
            if service_code == "doujin" and floor_code == "digital_doujin":
                logging.info("同人誌あらすじ取得")
                html_summary = scrape_product_details(product_url)
            else:
                logging.info("動画あらすじ取得")
                html_summary = scrape_product_summary(product_url, driver)
            logging.info(f"初回あらすじ取得: {html_summary}")

        # ⑤ AI分析
        logging.info("🤖 AIレビュー生成中...")

        avg_rating = round(
            sum(r["rating"] for r in reviews if r["rating"]) / (len(reviews) if reviews else 1),
            2
        )

        insight = generate_review_insights(
            reviews=reviews,
            html_summary=html_summary,
            review_avg=avg_rating,
            review_count=len(reviews),
            genre_type=f"{service_code}_{floor_code}"
        )

        if not insight:
            logging.info("⚠ AI分析失敗 → あらすじとレビュー数のみ保存")
            return

        logging.info(f"AI分析: {insight}")

        # ===============================
        # ★ ここが新5軸対応部分
        # ===============================
        # ⑥ 保存整形
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
            "updated_at": datetime.utcnow().isoformat()
        }
        # ⑦ AI保存
        save_ai_summary(summary)

        # ⑧ 週次保存
        logging.info("💾 週次スコア保存中...")
        save_weekly_score(summary)

        logging.info("🎉 完了: %s", content_id)

    except Exception as e:
        logging.info("❌ エラー: %s", e)
    finally:
        driver.quit()


# =========================
# 実行例
# ==========================

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

    # ---- AI総合（最大100）----
    common_score = (
        content * 0.25 +
        emotion * 0.20 +
        attraction * 0.15
    )  # 合計60%

    genre_score = (
        axis1 * 0.20 +
        axis2 * 0.20
    )  # 合計40%

    ai_score = common_score + genre_score

    # ---- レビュー補正 ----
    rating_factor = avg_rating / 5

    max_review = 20
    trust_base = min(
        math.log(review_count + 1) / math.log(max_review + 1),
        1
    )

    trust_factor = 0.5 + trust_base * 0.5

    final_score = ai_score * rating_factor * trust_factor

    return round(min(final_score, 100), 2)

# ⑧ 週次スコア保存
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

    supabase.table("trn_dmm_score_history") \
        .upsert(row, on_conflict="content_id,snapshot_date") \
        .execute()

    logging.info(f"📊 週次スコア保存完了: {summary['content_id']} → {final_score}")

# ----------------------------------------------------
# バッチ処理・メイン
# ----------------------------------------------------
def process_batch(batch_items, batch_index, total):
    logging.info(f"=== 🧩 バッチ {batch_index} 開始 ({len(batch_items)}件) ===")
    for i, row in enumerate(batch_items, start=1):
        content_id = row["content_id"]
        service_code = row["service"]
        floor_code = row["floor"]
        product_url = row["item_url"]
        logging.info(f"{batch_index}週目 [{i + (batch_index-1) * BATCH_SIZE}/{total}] {content_id} 処理中...")
        process_content(content_id, product_url, service_code, floor_code)

        time.sleep(0.5)
    logging.info(f"=== ✅ バッチ {batch_index} 完了 ===")


# ----------------------------------------------------
# メイン
# ----------------------------------------------------
def main():
    logging.info("=== trn_dmm_items のAPI更新を開始 ===")

    # -----------------------------
    # 全件取得（1000件制限対策）
    # -----------------------------
    all_items = []
    limit = 1000
    # start = 0

    release_date = (date.today() - timedelta(days=31)).isoformat()

    for target in targets:
        start=0
        while True:

            response = (
                supabase
                .table("trn_dmm_items")
                .select("content_id, item_url,service,floor")
                .eq("service", target["service"])
                .eq("floor", target["floor"])
                .gte("release_date", release_date) # 31日前の作品から取得
                #  .eq("content_id", "k568agotp12163")
                # .in_("content_id", ["d_7323132","dejo006","d_730232","d_723897","d_723141","b915awnmg04125","d_692522","k568agotp12114","k924aruuu14637","pfes00115","simw005","k740aplst08540","d_607638","deas044","deas044","orecz448","orecz469","d_708748","d_738130","d_671925","s788ahmlj00067","s011akamj02815","orecz469","orecz482","d_603074","simw005","d_727814","d_603074","d_738312","d_672378","b472abnen03917","d_744379","b472abnen03947","d_740374"])
                .order("created_at")
                .range(start, start + limit - 1)
                .execute()
            )

            data = response.data or []
            logging.info(
                f"{target['service']} {target['floor']} 取得件数: {len(data)} 件 (start={start})"
            )

            if not data:
                break

            all_items.extend(data)
            start += limit

            # if start >= limit:
            #     break

        logging.info(f"取得済み件数: {len(all_items)} 件")

    if not all_items:
        logging.info("対象データが存在しません。処理を終了します。")
        sys.exit(0)

    total = len(all_items)
    logging.info(f"全 {total} 件の作品を更新対象として処理します。")

    # -----------------------------
    # バッチ処理
    # -----------------------------
    update_count = 0

    for i in range(0, total, BATCH_SIZE):
        batch_items = all_items[i : i + BATCH_SIZE]
        batch_index = (i // BATCH_SIZE) + 1

        process_batch(batch_items, batch_index, total)
        update_count += len(batch_items)

        if i + BATCH_SIZE < total:
            logging.info(f"⏸ {SLEEP_BETWEEN_BATCH}秒待機中（次のバッチまで）...")
            time.sleep(SLEEP_BETWEEN_BATCH)

    logging.info(f"🎉 全ての作品データ更新が完了しました。{update_count} 件処理しました。")


if __name__ == "__main__":
    main()
