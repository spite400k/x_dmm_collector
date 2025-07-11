import os
import logging
import requests
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
DMM_API_ID = os.getenv("DMM_API_ID")
DMM_AFFILIATE_ID = os.getenv("DMM_AFFILIATE_ID")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---------------------------------------------
def sync_floor_master():
    logging.info("[FLOOR] フロア一覧の取得開始")

    url = "https://api.dmm.com/affiliate/v3/FloorList"
    params = {
        "api_id": DMM_API_ID,
        "affiliate_id": DMM_AFFILIATE_ID,
        "output": "json"
    }

    response = requests.get(url, params=params)
    print("[DEBUG] API raw response:")
    print(response.text)  # ← ここ！
    response.raise_for_status()

    result = response.json()
    if response.status_code != 200:
        logging.error("[FLOOR] APIエラー: %s", result.get("result", {}).get("message"))
        raise Exception("DMM API Error: " + result.get("result", {}).get("message"))

    floors = result["result"].get("floor", [])
    logging.info("[FLOOR] フロア件数: %d", len(floors))

    data = []
    for f in floors:
        data.append({
            "floor_id": f["floor_id"],
            "name": f["name"],
            "site_name": f["site_name"],
            "service_name": f["service_name"]
        })

    supabase.table("mst_floor").upsert(data, on_conflict="floor_id").execute()

# ---------------------------------------------
def sync_genre_master(floor_id):
    logging.info("[GENRE] ジャンル一覧の取得開始（floor: %s）", floor_id)

    url = "https://api.dmm.com/affiliate/v3/genrelist"
    params = {
        "api_id": DMM_API_ID,
        "affiliate_id": DMM_AFFILIATE_ID,
        "floor_id": floor_id,
        "output": "json"
    }

    response = requests.get(url, params=params)
    response.raise_for_status()

    genres = response.json()["result"]["genre"]

    data = []
    for g in genres:
        data.append({
            "genre_id": int(g["genre_id"]),
            "name": g["name"],
            "floor_id": floor_id
        })

    logging.info("[GENRE] ジャンル件数: %d", len(data))
    supabase.table("mst_genre").upsert(data, on_conflict="genre_id").execute()

# ---------------------------------------------
def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    # 1. フロアマスタ登録
    sync_floor_master()

    # 2. 主要 floor に対してジャンルマスタも登録
    floors = supabase.table("mst_floor").select("floor_id").execute().data
    for floor in floors:
        floor_id = floor["floor_id"]
        try:
            sync_genre_master(floor_id)
        except Exception as e:
            logging.warning("[GENRE] floor_id=%s のジャンル取得失敗: %s", floor_id, str(e))

if __name__ == "__main__":
    main()
