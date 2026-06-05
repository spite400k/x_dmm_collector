import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# main_update_actress_profile.py

import os
import re
import time
import logging
import requests
from datetime import datetime
from bs4 import BeautifulSoup

from db.supabase_client import supabase
from utils.logger import setup_logger

setup_logger("main_update_actress_profile.log")

BATCH_SIZE = 1000
SLEEP_TIME = 0.3

BASE_URL = "https://osusume.dmm.co.jp/list/?actress="

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "ja-JP,ja;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
    "Cookie": "age_check_done=1"
}

session = requests.Session()
session.headers.update(headers)
session.get("https://osusume.dmm.co.jp/")

DMM_API_ID = os.getenv("DMM_API_ID")
DMM_AFFILIATE_ID = os.getenv("DMM_AFFILIATE_ID")
# =================================
# 対象女優取得
# =================================

def get_target_actresses():

    response = supabase.table("mst_actress") \
        .select("actress_id,name") \
        .range(0, BATCH_SIZE-1) \
        .execute()

    return response.data or []

# ----------------------------------------------------
# DMM 女優検索API
# ----------------------------------------------------
def get_actress_image(actress_id: str):
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

        if not actresses:
            return None

        actress = actresses[0]

        image = actress.get("imageURL", {})

        # large優先
        return image.get("large") or image.get("small")

    except Exception as e:
        logging.error(f"❌ ActressSearch API 呼び出し失敗: {actress_id} ({e})")
        return None
    
# =================================
# プロフィール取得
# =================================

def scrape_actress_profile(actress_id):

    url = BASE_URL + str(actress_id)

    try:

        res = session.get(url, timeout=20)

        if res.status_code != 200:
            logging.warning(f"取得失敗: {actress_id}")
            return None

        soup = BeautifulSoup(res.text, "html.parser")

        data = {}

        # -------------------------
        # 画像
        # -------------------------

        img = get_actress_image(actress_id)

        if img:
            data["image_url"] = img

        logging.info(f"画像URL: {data.get('image_url')}")

        # -------------------------
        # FANZA活動期間
        # -------------------------

        career = soup.find("span", string="FANZA活動期間")

        if career:
            value = career.find_next("span").text.strip()
            data["fanza_activity"] = value

        # -------------------------
        # プロフィール
        # -------------------------

        profile_tag = soup.select_one("#profile-detail + p")

        if profile_tag:
            data["profile"] = profile_tag.text.strip()

        # -------------------------
        # 経歴
        # -------------------------

        career_tag = soup.select_one("#personality + p")

        if career_tag:
            data["career_text"] = career_tag.text.strip()

        # -------------------------
        # 作品・受賞歴
        # -------------------------

        award_tag = soup.select_one("#award + p")

        if award_tag:
            data["awards"] = award_tag.text.strip()

        # -------------------------
        # サイズ
        # -------------------------

        text = soup.get_text()

        size_match = re.search(
            r"T(\d+)cm\s*B(\d+)cm\s*\((.*?)カップ\)\s*W(\d+)cm\s*H(\d+)cm",
            text
        )

        if size_match:
            data["height"] = int(size_match.group(1))
            data["bust"] = int(size_match.group(2))
            data["cup"] = size_match.group(3)
            data["waist"] = int(size_match.group(4))
            data["hip"] = int(size_match.group(5))

        # -------------------------
        # デビュー日
        # -------------------------

        debut_match = re.search(
            r"(\d{4})年(\d{1,2})月(\d{1,2})日に配信開始",
            text
        )

        if debut_match:

            y = debut_match.group(1)
            m = debut_match.group(2)
            d = debut_match.group(3)

            data["debut_date"] = f"{y}-{m.zfill(2)}-{d.zfill(2)}"

        # -------------------------
        # 作品数
        # -------------------------

        works_match = re.search(
            r"『(\d+)』作品を配信",
            text
        )

        if works_match:
            data["works_count"] = int(works_match.group(1))

        # -------------------------
        # お気に入り数
        # -------------------------

        fav_match = re.search(
            r"お気に入り登録数が(\d+)万人",
            text
        )

        if fav_match:
            data["favorite_count"] = int(fav_match.group(1)) * 10000

        return data

    except Exception as e:

        logging.error(f"取得エラー {actress_id} {e}")
        return None


# =================================
# DB保存
# =================================

def save_profile(actress_id, profile):

    if not profile:
        return

    profile["updated_at"] = datetime.utcnow().isoformat()

    supabase.table("mst_actress") \
        .update(profile) \
        .eq("actress_id", actress_id) \
        .execute()

    logging.info(f"保存完了: {actress_id}")


# =================================
# メイン処理
# =================================

def main():

    logging.info("=== 女優プロフィール取得開始 ===")

    actresses = get_target_actresses()

    if not actresses:
        logging.info("対象女優なし")
        return

    total = len(actresses)

    for i, actress in enumerate(actresses, start=1):

        actress_id = actress["actress_id"]
        name = actress["name"]

        logging.info(f"[{i}/{total}] 取得: {name}")

        profile = scrape_actress_profile(actress_id)

        if profile:
            save_profile(actress_id, profile)

        time.sleep(SLEEP_TIME)

    logging.info("🎉 プロフィール更新完了")


if __name__ == "__main__":
    main()