import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

"""
メスガキサイト向け: trn_dmm_items の DMM API 情報をバッチ更新する。

接続先は db/supabase_client_mesugaki.py（デフォルト URL: メスガキ用プロジェクト）。
環境変数:
  - MESUGAKI_SUPABASE_KEY: 必須（メスガキ Supabase のキー）
  - MESUGAKI_SUPABASE_URL: 任意（省略時はメスガキ用デフォルト URL）
"""
import os
import sys
import re
import time
import logging
from typing import Any
from datetime import datetime
import requests
from openai import OpenAI  # ← ★追加

from db.supabase_client_mesugaki import supabase
from pykakasi import kakasi

# ----------------------------------------------------
# 設定
# ----------------------------------------------------
from utils.logger import setup_logger

setup_logger("main_update_mesugaki.log")

DMM_API_ID = os.getenv("DMM_API_ID")
DMM_AFFILIATE_ID = os.getenv("DMM_AFFILIATE_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # ★追加
client = OpenAI(api_key=OPENAI_API_KEY)       # ★追加

BATCH_SIZE = 100
SLEEP_BETWEEN_BATCH = 5


# ----------------------------------------------------
# 共通: 数値変換
# ----------------------------------------------------
def parse_price(price_str):
    if not price_str:
        return None
    match = re.search(r"\d+", price_str.replace(",", ""))
    return int(match.group()) if match else None


def as_list(x: Any) -> list:
    """API が単一 dict / null / list のいずれでもリストとして扱う。"""
    if x is None:
        return []
    if isinstance(x, list):
        return x
    if isinstance(x, dict):
        return [x]
    return []


# ----------------------------------------------------
# 🧠 Safe化＋概要化AI生成
# ----------------------------------------------------
SAFE_WORD_MAPPING = {
    "セックス": "ラブシーン",
    "エロ": "大人向け表現",
    "濡れる": "感情が高まる",
    "胸": "身体の特徴",
    "おっぱい": "胸部",
    "陰部": "体の一部",
    "フェラ": "接触シーン",
    "挿入": "スキンシーン",
    "裸": "衣服が少ない姿",
    "快感": "感情の高まり",
    "チンポ": "身体の一部",
    "チ○ポ": "身体の一部",
    "ヌく": "癒しを与える",
    "ヌいて": "癒してくれる",
    "射精": "クライマックス",
    "勃起": "興奮",
    "本番": "親密なシーン",
    "罵倒": "S気質な表現",
    "キャバ嬢": "接客業の女性",
    "風俗嬢": "接客業の女性",
    "痴女": "積極的な性格",
    "バニーガール": "バニースタイル",
    "中出し": "親密な演出",
    "AV": "ビデオ作品",
    "自慰": "セルフケア",
    "変態": "ユニークな趣味",
}


def safe_text_by_word_mapping(auto_summary: str, auto_point: str) -> tuple[str, str]:
    """ワード置換でR18表現をSoft化"""
    s = (auto_summary or "").strip()
    p = (auto_point or "").strip()
    if not s and not p:
        return "", ""
    safe_auto_summary = auto_summary or ""
    safe_auto_point = auto_point or ""
    for r18_word, safe_word in SAFE_WORD_MAPPING.items():
        safe_auto_summary = safe_auto_summary.replace(r18_word, safe_word)
        safe_auto_point = safe_auto_point.replace(r18_word, safe_word)
    return safe_auto_summary, safe_auto_point

def generate_safe_summary_point(
    title: str,
    auto_summary: str | None,
    auto_point: str | None,
    *,
    content_id: str | None = None,
) -> tuple[str, str]:
    """
    ワード置換済み文章で要約・ポイント生成
    - AIには直接的R18表現は渡さない
    - Safe化文章を要約・ポイント化
    """
    prefix = f"{content_id}: " if content_id else ""
    safe_auto_summary, safe_auto_point = safe_text_by_word_mapping(auto_summary, auto_point)

    if not safe_auto_summary.strip() and not safe_auto_point.strip():
        logging.info("%s要約・ポイント: 入力が空のため OpenAI はスキップ", prefix)
        return "", ""

    logging.info("%s要約・ポイント: OpenAI 呼び出し中…", prefix)

    prompt = f"""
次の成人向け作品紹介文を、性的表現を避けつつ内容を維持したSafeSearch対応テキストに変換してください。
- 読者に魅力が伝わるように、官能的・情緒的な表現を使って自然に書き換えてください。
- 卑猥な単語や直接的な性表現は禁止です。
- 出力は以下の形式で日本語で返してください:

【あらすじ・概要】
(ここにSafe化されたsummary)

【おすすめポイント】
(ここにSafe化されたポイントを箇条書きで)
---
作品タイトル: {title}
概要文:
{safe_auto_summary}
作品ポイント:
{safe_auto_point}
"""

    try:
        res = client.chat.completions.create(
            # model="gpt-4o-nano",
            # model="gpt-5.4-nano-2025-08-07",
            model="gpt-5.4-nano",
            messages=[{"role": "user", "content": prompt}],
            # temperature=0.7,
        )
        raw_content = res.choices[0].message.content
        text = (raw_content or "").strip()

        match = re.split(r"【おすすめポイント】", text)
        auto_summary = match[0].replace("【あらすじ・概要】", "").strip() if len(match) > 0 else text
        auto_point = (match[1] or "").strip() if len(match) > 1 else ""

        return auto_summary, auto_point

    except Exception as e:
        logging.error("%s❌ Safe化AI生成失敗: %s", prefix, e)
        return "", ""

# ----------------------------------------------------
# 🧠 Safe化AI生成関数
# ----------------------------------------------------
def generate_safe_text(title: str, summary: str = "") -> tuple[str, str]:
    """
    R18の文章を、Google SafeSearch対応のやわらかい表現に自動変換。
    戻り値: (auto_summary_soft, auto_point_soft)
    """
    try:
        prompt = f"""
次の成人向け作品紹介文を、性的表現を避けつつ内容を維持したSafeSearch対応テキストに変換してください。
- 読者に魅力が伝わるように、官能的・情緒的な表現を使って自然に書き換えてください。
- 卑猥な単語や直接的な性表現は禁止です。
- 出力は以下の形式で日本語で返してください:

【あらすじ・概要】
(ここにSafe化されたsummary)

【おすすめポイント】
(ここにSafe化されたポイントを箇条書きで)
---
作品タイトル: {title}
概要文:
{summary}
"""
        res = client.chat.completions.create(
            model="gpt-5.4-nano",  # 高速・低コストで十分
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
        )
        raw_content = res.choices[0].message.content
        text = (raw_content or "").strip()
        # 分割
        match = re.split(r"【おすすめポイント】", text)
        auto_summary = match[0].replace("【あらすじ・概要】", "").strip() if len(match) > 0 else text
        auto_point = (match[1] or "").strip() if len(match) > 1 else ""
        return auto_summary, auto_point

    except Exception as e:
        logging.error(f"❌ Safe化AI生成失敗: {e}")
        return None, None

# ----------------------------------------------------
# DMM 女優検索API
# ----------------------------------------------------
def fetch_actress_detail(actress_id: str):
    url = "https://api.dmm.com/affiliate/v3/ActressSearch"
    params = {
        "api_id": DMM_API_ID,
        "affiliate_id": DMM_AFFILIATE_ID,
        "actress_id": actress_id,
        "output": "json",
    }

    try:
        res = requests.get(url, params=params, timeout=10)
        res.raise_for_status()
        data = res.json()
        result = data.get("result") or {}
        actresses = as_list(result.get("actress"))
        return actresses[0] if actresses else None
    except Exception as e:
        logging.error(f"❌ ActressSearch API 呼び出し失敗: {actress_id} ({e})")
        return None

# ----------------------------------------------------
# 日本語→ローマ字変換
# ----------------------------------------------------
kakasi_obj = kakasi()
kakasi_obj.setMode("H", "a")
kakasi_obj.setMode("K", "a")
kakasi_obj.setMode("J", "a")
kakasi_obj.setMode("r", "Hepburn")
converter = kakasi_obj.getConverter()

def to_romanized(text: str) -> str | None:
    if not text:
        return None
    return converter.do(text).replace(" ", "").capitalize()

# ----------------------------------------------------
# 女優・監督・ジャンルUPSERT
# ----------------------------------------------------
def upsert_actresses(actresses: list[dict]):
    if not actresses:
        return
    for a in actresses:
        actress_id = a.get("id")
        if not actress_id:
            continue
        detail = fetch_actress_detail(actress_id) or a
        try:
            supabase.table("mst_actress").upsert(
                {
                    "actress_id": detail.get("id"),
                    "name": detail.get("name"),
                    "name_kana": detail.get("ruby"),
                    "name_en": to_romanized(detail.get("ruby")),
                    "image_url": (detail.get("imageURL") or {}).get("large"),
                    "updated_at": datetime.utcnow().isoformat(),
                },
                on_conflict=["actress_id"],
            ).execute()
        except Exception as e:
            logging.error(f"❌ 女優UPSERT失敗: {a} ({e})")
        time.sleep(0.5)

def upsert_genres(genres: list[dict], service_code: str, floor_code: str):
    if not genres:
        return
    for g in genres:
        try:
            supabase.table("mst_genre").upsert(
                {
                    "genre_id": g.get("id"),
                    "genres_name": g.get("name"),
                    "genre_ruby": g.get("ruby"),
                    "floor_id": g.get("floor_id"),
                    "created_at": datetime.utcnow().isoformat(),
                },
                on_conflict=["genre_id"],
            ).execute()
        except Exception as e:
            logging.error(f"❌ ジャンルUPSERT失敗: {g} ({e})")

        try:
            supabase.table("mst_genre_sort").upsert(
                {
                    "service_code": service_code,
                    "floor_code": floor_code,
                    "genre_id": g.get("id"),
                    "genres_name": g.get("name"),
                    "genre_ruby": g.get("ruby"),
                    "created_at": datetime.utcnow().isoformat(),
                },
                on_conflict=["service_code,floor_code,genre_id"],
            ).execute()
        except Exception as e:
            logging.error(f"❌ ジャンルソート順UPSERT失敗: {g} ({e})")


def upsert_directors(directors: list[dict]):
    if not directors:
        return
    for d in directors:
        try:
            supabase.table("mst_director").upsert(
                {
                    "director_id": d.get("id"),
                    "name": d.get("name"),
                    "updated_at": datetime.utcnow().isoformat(),
                },
                on_conflict=["director_id"],
            ).execute()
        except Exception as e:
            logging.error(f"❌ 監督UPSERT失敗: {d} ({e})")

# ----------------------------------------------------
# DMM API
# ----------------------------------------------------
def fetch_item_by_content_id(content_id: str):
    url = "https://api.dmm.com/affiliate/v3/ItemList"
    params = {
        "api_id": DMM_API_ID,
        "affiliate_id": DMM_AFFILIATE_ID,
        "site": "DMM.R18",
        "cid": content_id,
        "output": "json",
    }
    try:
        res = requests.get(url, params=params, timeout=10)
        res.raise_for_status()
        data = res.json()
        result = data.get("result") or {}
        items = result.get("items") or []
        if not isinstance(items, list):
            items = []
        return items[0] if items else None
    except Exception as e:
        logging.error(f"❌ DMM API呼び出し失敗: {content_id} ({e})")
        return None

# ----------------------------------------------------
# trn_dmm_items 更新
# ----------------------------------------------------
def update_dmm_item(
    content_id: str,
    item: dict,
    auto_summary: str | None,
    auto_point: str | None,
):
    try:
        review = item.get("review") or {}
        review_count = review.get("count")
        review_average = review.get("average")

        prices = item.get("prices") or {}
        price = parse_price(prices.get("price"))
        list_price = parse_price(prices.get("list_price"))
        deliveries = prices.get("deliveries") or {}
        if not isinstance(deliveries, dict):
            deliveries = {}
        delivery = deliveries.get("delivery")

        iteminfo = item.get("iteminfo") or {}
        campaign = iteminfo.get("campaign")

        actresses = as_list(iteminfo.get("actress"))
        directors = as_list(iteminfo.get("director"))
        genres = as_list(iteminfo.get("genre"))

        # ★ sampleImageURL（画像URL群）
        sample_block = item.get("sampleImageURL") or {}
        if not isinstance(sample_block, dict):
            sample_block = {}
        sample_l = sample_block.get("sample_l") or {}
        if not isinstance(sample_l, dict):
            sample_l = {}
        sample_images = sample_l.get("image") or []
        if not isinstance(sample_images, list):
            sample_images = []

        # マスタ更新
        # upsert_actresses(actresses)
        # upsert_genres(genres,item.get("service_code"),item.get("floor_code"))
        # upsert_directors(directors)

        title = item.get("title", "")
        # 🧠 Safe化AI生成
        # auto_summary, auto_point = generate_safe_summary_point(
        #     title,
        #     auto_summary,
        #     auto_point,
        #     content_id=content_id,
        # )

        raw_json = item
        actress_ids = [a.get("id") for a in actresses] if actresses else None
        actress_names = [a.get("name") for a in actresses] if actresses else None
        director_ids = [d.get("id") for d in directors] if directors else None
        director_names = [d.get("name") for d in directors] if directors else None
        genre_ids = [g.get("id") for g in genres] if genres else None
        genre_names = [g.get("name") for g in genres] if genres else None

        # ★ 更新データに sample_images を追加

        update_data = {
            "review_count": review_count,
            "review_average": review_average,
            "price": price,
            "list_price": list_price,
            "auto_summary": auto_summary,
            "auto_point": auto_point,
            "campaign": campaign,
            "actress_ids": actress_ids,
            "actress": actresses,
            "director_ids": director_ids,
            "director": directors,
            # "genre_ids": genre_ids,
            # "genre": genre_names,
            "delivery": delivery,
            "sample_images": sample_images,  # ← 追加（配列カラム）
            "raw_json": raw_json,
            "updated_at": datetime.utcnow().isoformat(),
        }

        res = (
            supabase.table("trn_dmm_items")
            .update(update_data)
            .eq("content_id", content_id)
            .execute()
        )

        if res.data:
            logging.info("✅ 更新完了: %s（Supabase 反映済み）", content_id)
        else:
            logging.warning(f"⚠️ 該当データなし: {content_id}")

    except Exception as e:
        logging.error(f"❌ 更新失敗: {content_id} ({e})")

# ----------------------------------------------------
# バッチ処理・メイン
# ----------------------------------------------------
def process_batch(
    batch_items,
    batch_index: int,
    total_batches: int,
    range_start: int,
    total: int,
):
    """range_start: 全体リスト上のこのバッチ先頭の0-basedインデックス"""
    batch_t0 = time.perf_counter()
    batch_end = min(range_start + len(batch_items), total)
    logging.info(
        "=== バッチ %s/%s 開始（当バッチ %s 件）全体進捗: %s〜%s / %s 件 ===",
        batch_index,
        total_batches,
        len(batch_items),
        range_start + 1,
        batch_end,
        total,
    )
    for idx_in_batch, row in enumerate(batch_items, start=1):
        content_id = row.get("content_id")
        if not content_id:
            logging.warning("⚠️ content_id が無い行をスキップします: %s", row)
            continue
        global_num = range_start + idx_in_batch
        pct = (global_num / total) * 100 if total else 0.0
        logging.info(
            "[%s/%s] (%.1f%%) %s 処理開始…",
            global_num,
            total,
            pct,
            content_id,
        )
        item = fetch_item_by_content_id(content_id)
        if item:
            update_dmm_item(
                content_id,
                item,
                row.get("auto_summary"),
                row.get("auto_point"),
            )
        else:
            logging.warning("⚠️ データ取得失敗: %s", content_id)
        time.sleep(0.5)
    elapsed = time.perf_counter() - batch_t0
    logging.info(
        "=== バッチ %s/%s 完了（%.1f 秒、1件あたり平均 %.2f 秒）===",
        batch_index,
        total_batches,
        elapsed,
        elapsed / len(batch_items) if batch_items else 0.0,
    )

# ----------------------------------------------------
# メイン
# ----------------------------------------------------
def main():
    logging.info("=== trn_dmm_items のAPI更新を開始 ===")

    missing_env = [
        name
        for name, val in (
            ("DMM_API_ID", DMM_API_ID),
            ("DMM_AFFILIATE_ID", DMM_AFFILIATE_ID),
            ("OPENAI_API_KEY", OPENAI_API_KEY),
        )
        if not val
    ]
    if missing_env:
        logging.error(
            "必須環境変数が未設定です: %s",
            ", ".join(missing_env),
        )
        sys.exit(1)

    # -----------------------------
    # 全件取得（1000件制限対策）
    # -----------------------------
    all_items = []
    limit = 1000
    start = 0

    while True:
        response = (
            supabase
            .table("trn_dmm_items")
            .select("content_id, auto_summary, auto_point")
            .order("content_id")
            .range(start, start + limit - 1)
            .execute()
        )

        data = response.data or []

        if not data:
            break

        all_items.extend(data)
        start += limit

        logging.info("Supabase 取得中… 累計 %s 件（オフセット %s）", len(all_items), start)

    if not all_items:
        logging.info("対象データが存在しません。処理を終了します。")
        sys.exit(0)

    total = len(all_items)
    total_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
    logging.info(
        "リスト取得完了: 全 %s 件。バッチサイズ %s → 全 %s バッチで処理します。",
        total,
        BATCH_SIZE,
        total_batches,
    )

    # -----------------------------
    # バッチ処理
    # -----------------------------
    update_count = 0
    run_t0 = time.perf_counter()

    for i in range(0, total, BATCH_SIZE):
        batch_items = all_items[i : i + BATCH_SIZE]
        batch_index = (i // BATCH_SIZE) + 1

        process_batch(batch_items, batch_index, total_batches, i, total)
        update_count += len(batch_items)

        if i + BATCH_SIZE < total:
            logging.info(
                "⏸ 次バッチまで %s 秒待機（残りバッチ: %s）…",
                SLEEP_BETWEEN_BATCH,
                total_batches - batch_index,
            )
            time.sleep(SLEEP_BETWEEN_BATCH)

    run_elapsed = time.perf_counter() - run_t0
    logging.info(
        "🎉 全作品の更新が完了しました。処理 %s 件 / 合計 %.1f 分（%.1f 秒）",
        update_count,
        run_elapsed / 60.0,
        run_elapsed,
    )


if __name__ == "__main__":
    main()
