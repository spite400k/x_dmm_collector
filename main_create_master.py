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
    url = "https://api.dmm.com/affiliate/v3/floorList"
    params = {
        "api_id": DMM_API_ID,
        "affiliate_id": DMM_AFFILIATE_ID,
        "output": "json"
    }
    res = requests.get(url, params=params)
    result = res.json()

    sites = result.get("result", {}).get("site", [])
    if not sites:
        logging.error("[SITE] サイトデータが空です")
        return

    for site in sites:
        site_name = site.get("name")
        site_code = site.get("code")

        # mst_site に登録
        supabase.table("mst_site").upsert({
            "site_name": site_name,
            "site_code": site_code
        }, on_conflict=["site_code"]).execute()

        services = site.get("service", [])
        for service in services:
            service_name = service.get("name")
            service_code = service.get("code")

            # mst_service に登録
            supabase.table("mst_service").upsert({
                "service_name": service_name,
                "service_code": service_code,
                "site_code": site_code,
            }).execute()

        logging.info("[SITE] site=%s (%s) に %d 個の service を登録", site_name, site_code, len(services))

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
    response.raise_for_status()
    result = response.json()

    sites = result.get("result", {}).get("site", [])
    floors = []

    for site in sites:
        site_name = site.get("name")
        site_code = site.get("code")
        for service in site.get("service", []):
            service_name = service.get("name")
            for floor in service.get("floor", []):
                floors.append({
                    "floor_id": int(floor.get("id")),
                    "floor_name": floor.get("name"),
                    "floor_code": floor.get("code"),
                    "site_name": site_name,
                    "site_code": site_code,
                    "service_name": service_name,
                    "service_code": service.get("code"),
                })

    logging.info("[FLOOR] フロア件数: %d", len(floors))
    supabase.table("mst_floor").upsert(floors, on_conflict="floor_id").execute()


# ---------------------------------------------
def sync_genre_master(floor_id):
    logging.info("[GENRE] ジャンル一覧の取得開始（floor: %s）", floor_id)

    url = "https://api.dmm.com/affiliate/v3/GenreSearch"
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
            "genres_name": g["name"],
            "genre_code": g["code"],
            "floor_id": floor_id,
            "floor_code": g.get("floor_code", ""),
            "floor_name": g.get("floor_name", ""),
            "service_code": g.get("service_code", ""),
            "service_name": g.get("service_name", ""),
            "site_code": g.get("site_code", ""),
            "site_name": g.get("site_name", ""),
        })

    logging.info("[GENRE] ジャンル件数: %d", len(data))
    supabase.table("mst_genre").upsert(data, on_conflict="genre_id").execute()

# ---------------------------------------------
def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    # 1. サイト/サービスマスタ登録
    # sync_site_and_service_master()
    # 1. フロアマスタ登録
    # sync_floor_master()

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
