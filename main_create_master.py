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
# サイトとサービスのマスタを同期する
def sync_site_and_service_master():
    logging.info("[SITE] サイト/サービス一覧の取得開始")

    try:
        res = requests.get(
            "https://api.dmm.com/affiliate/v3/floorList",
            params={
                "api_id": DMM_API_ID,
                "affiliate_id": DMM_AFFILIATE_ID,
                "output": "json"
            },
            timeout=10
        )
        res.raise_for_status()
        result = res.json()
    except requests.exceptions.RequestException as e:
        logging.error("[SITE] APIリクエスト失敗: %s", str(e))
        return

    sites = result.get("result", {}).get("site", [])
    if not sites:
        logging.error("[SITE] サイト情報が空または不正です")
        return

    for site in sites:
        site_name = site.get("name")
        site_code = site.get("code")

        try:
            # mst_site に登録
            supabase.table("mst_site").upsert({
                "site_name": site_name,
                "site_code": site_code
            }, on_conflict=["site_code"]).execute()
        except Exception as e:
            logging.warning("[SITE] mst_site upsert失敗: %s", str(e))

        services = site.get("service", [])
        for service in services:
            try:
                # mst_service に登録
                supabase.table("mst_service").upsert({
                    "service_name": service.get("name"),
                    "service_code": service.get("code"),
                    "site_code": site_code,
                }, on_conflict=["service_code"]).execute()
            except Exception as e:
                logging.warning("[SERVICE] mst_service upsert失敗: %s", str(e))

        logging.info("[SITE] site=%s (%s) に %d 個の service を登録", site_name, site_code, len(services))

# ---------------------------------------------
def sync_floor_master():
    logging.info("[FLOOR] フロア一覧の取得開始")

    try:
        res = requests.get(
            "https://api.dmm.com/affiliate/v3/FloorList",
            params={
                "api_id": DMM_API_ID,
                "affiliate_id": DMM_AFFILIATE_ID,
                "output": "json"
            },
            timeout=10
        )
        res.raise_for_status()
        result = res.json()
    except requests.exceptions.RequestException as e:
        logging.error("[FLOOR] APIリクエスト失敗: %s", str(e))
        return

    sites = result.get("result", {}).get("site", [])
    if not sites:
        logging.error("[FLOOR] サイト情報が空または不正です")
        return

    floors = []

    for site in sites:
        for service in site.get("service", []):
            for floor in service.get("floor", []):
                floors.append({
                    "floor_id": int(floor.get("id")),
                    "floor_name": floor.get("name"),
                    "floor_code": floor.get("code"),
                    "site_name": site.get("name"),
                    "site_code": site.get("code"),
                    "service_name": service.get("name"),
                    "service_code": service.get("code"),
                })

    logging.info("[FLOOR] フロア件数: %d", len(floors))

    try:
        supabase.table("mst_floor").upsert(floors, on_conflict="floor_id").execute()
    except Exception as e:
        logging.error("[FLOOR] mst_floor upsert失敗: %s", str(e))

# ---------------------------------------------
def sync_genre_master(floor_id):
    logging.info("[GENRE] ジャンル一覧の取得開始（floor_id: %s）", floor_id)

    try:
        res = requests.get(
            "https://api.dmm.com/affiliate/v3/GenreSearch",
            params={
                "api_id": DMM_API_ID,
                "affiliate_id": DMM_AFFILIATE_ID,
                "floor_id": floor_id,
                "output": "json"
            },
            timeout=10
        )
        res.raise_for_status()
        result = res.json()
    except requests.exceptions.RequestException as e:
        logging.error("[GENRE] APIリクエスト失敗（floor_id=%s）: %s", floor_id, str(e))
        return

    genres = result.get("result", {}).get("genre", [])
    if not genres:
        logging.warning("[GENRE] ジャンルが空です（floor_id=%s）", floor_id)
        return

    data = []
    for g in genres:
        data.append({
            "genre_id": int(g["genre_id"]),
            "genres_name": g["name"],
            "genre_ruby": g["ruby"],
            "floor_id": floor_id,
        })

    logging.info("[GENRE] ジャンル件数: %d", len(data))

    try:
        supabase.table("mst_genre").upsert(data, on_conflict="genre_id").execute()
    except Exception as e:
        logging.error("[GENRE] mst_genre upsert失敗: %s", str(e))

# ---------------------------------------------
def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

    try:
        # sync_site_and_service_master()
        # sync_floor_master()

        floors = supabase.table("mst_floor").select("floor_id").execute().data
        for floor in floors:
            floor_id = floor["floor_id"]
            try:
                sync_genre_master(floor_id)
            except Exception as e:
                logging.warning("[GENRE] floor_id=%s のジャンル取得失敗: %s", floor_id, str(e))

    except Exception as e:
        logging.critical("[FATAL] 処理中に例外発生: %s", str(e))

if __name__ == "__main__":
    main()
