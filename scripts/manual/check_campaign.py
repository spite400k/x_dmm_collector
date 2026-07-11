import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import os
import sys
import re
import time
import logging
from datetime import datetime
import requests
from openai import OpenAI  # ← ★追加

from db.supabase_client import supabase
from pykakasi import kakasi

# ----------------------------------------------------
# 設定
# ----------------------------------------------------
from utils.logger import setup_logger

setup_logger("main.log")

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

def generate_safe_summary_point(title: str, auto_summary: str, auto_point ) -> tuple[str, str]:
    """
    ワード置換済み文章で要約・ポイント生成
    - AIには直接的R18表現は渡さない
    - Safe化文章を要約・ポイント化
    """
    safe_auto_summary, safe_auto_point = safe_text_by_word_mapping(auto_summary,auto_point)

    if not safe_auto_summary.strip() and not safe_auto_point.strip():
        return "", ""

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
        text = res.choices[0].message.content.strip()

        match = re.split(r"【おすすめポイント】", text)
        auto_summary = match[0].replace("【あらすじ・概要】", "").strip() if len(match) > 0 else text
        auto_point = match[1].strip() if len(match) > 1 else ""

        return auto_summary, auto_point

    except Exception as e:
        logging.error(f"❌ Safe化AI生成失敗: {e}")
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
        text = res.choices[0].message.content.strip()
        # 分割
        match = re.split(r"【おすすめポイント】", text)
        auto_summary = match[0].replace("【あらすじ・概要】", "").strip() if len(match) > 0 else text
        auto_point = match[1].strip() if len(match) > 1 else ""
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
        actresses = data.get("result", {}).get("actress", [])
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
                    "image_url": detail.get("imageURL", {}).get("large"),
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
        items = data.get("result", {}).get("items", [])
        return items[0] if items else None
    except Exception as e:
        logging.error(f"❌ DMM API呼び出し失敗: {content_id} ({e})")
        return None

# ----------------------------------------------------
# trn_dmm_items 更新
# ----------------------------------------------------
def update_dmm_item(content_id: str, item: dict, auto_summary: str, auto_point: str):
    try:
        review_count = item.get("review", {}).get("count")
        review_average = item.get("review", {}).get("average")

        price = parse_price(item.get("prices", {}).get("price"))
        list_price = parse_price(item.get("prices", {}).get("list_price"))
        delivery = item.get("prices", {}).get("deliveries", {}).get("delivery")

        iteminfo = item.get("iteminfo", {})
        campaign = iteminfo.get("campaign")

        actresses = iteminfo.get("actress")
        directors = iteminfo.get("director")
        genres = iteminfo.get("genre")

        # ★ sampleImageURL（画像URL群）
        sample_images = (
            item.get("sampleImageURL", {})
            .get("sample_l", {})
            .get("image", [])
        )

        # マスタ更新
        # upsert_actresses(actresses)
        # upsert_genres(genres,item.get("service_code"),item.get("floor_code"))
        # upsert_directors(directors)

        title = item.get("title", "")
        # 🧠 Safe化AI生成
        # auto_summary, auto_point = generate_safe_summary_point(title, auto_summary, auto_point )

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
            # "auto_summary": auto_summary,
            # "auto_point": auto_point,
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
        if campaign:
            logging.info(f"✅ キャンペーン有り: {content_id} :{campaign}")
        else:
            logging.info(f"❌ キャンペーンなし: {content_id}")

        # res = (
        #     supabase.table("trn_dmm_items")
        #     .update(update_data)
        #     .eq("content_id", content_id)
        #     .execute()
        # )

        # if res.data:
        #     logging.info(f"✅ 更新完了: {content_id}")
        # else:
        #     logging.warning(f"⚠️ 該当データなし: {content_id}")

    except Exception as e:
        logging.error(f"❌ 更新失敗: {content_id} ({e})")

# ----------------------------------------------------
# バッチ処理・メイン
# ----------------------------------------------------
def process_batch(batch_items, batch_index,total):
    logging.info(f"=== 🧩 バッチ {batch_index} 開始 ({len(batch_items)}件) ===")
    for i, row in enumerate(batch_items, start=1):
        content_id = row["content_id"]
        logging.info(f"[{i}/{total}] {content_id} 処理中...")
        item = fetch_item_by_content_id(content_id)
        if item:
            update_dmm_item(content_id, item, row["auto_summary"], row["auto_point"])
        else:
            logging.warning(f"⚠️ データ取得失敗: {content_id}")
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

        process_batch(batch_items, batch_index,total)
        update_count += len(batch_items)

        if i + BATCH_SIZE < total:
            logging.info(f"⏸ {SLEEP_BETWEEN_BATCH}秒待機中（次のバッチまで）...")
            time.sleep(SLEEP_BETWEEN_BATCH)

    logging.info(f"🎉 全ての作品データ更新が完了しました。{update_count} 件処理しました。")


if __name__ == "__main__":
    main()
