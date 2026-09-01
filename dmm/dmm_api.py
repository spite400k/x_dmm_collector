import os
import requests
import logging
import json
from dotenv import load_dotenv
from db.supabase_client import supabase as default_supabase_client
from utils.supabase_retry import call_with_retry

load_dotenv()

DMM_API_ID = os.getenv("DMM_API_ID")
DMM_AFFILIATE_ID = os.getenv("DMM_AFFILIATE_ID")
API_URL = "https://api.dmm.com/affiliate/v3/ItemList"
DEFAULT_API_TIMEOUT = 30
DMM_API_RETRIES = 3
DMM_API_RETRY_DELAY = 2.0

os.makedirs("logs", exist_ok=True)
from utils.logger import setup_logger

setup_logger("dmm_api.log")


def get_highest_resolution_movie(movie_info: dict):
    if not isinstance(movie_info, dict):
        return None

    best_url = None
    best_area = 0

    for key, url in movie_info.items():
        if key.startswith("size_") and isinstance(url, str):
            try:
                _, w, h = key.split("_")
                area = int(w) * int(h)
                if area > best_area:
                    best_area = area
                    best_url = url
            except Exception:
                continue

    return best_url


def _request_item_list(params: dict) -> dict:
    """ItemList API を timeout 付きで呼び、接続エラー・5xx はリトライする。"""

    def _do_request() -> dict:
        logging.info("DMM APIへリクエスト送信: %s", API_URL)
        logging.info("送信パラメータ: %s", params)
        response = requests.get(API_URL, params=params, timeout=DEFAULT_API_TIMEOUT)
        if response.status_code >= 500:
            raise requests.ConnectionError(
                f"DMM API server error: HTTP {response.status_code}"
            )
        response.raise_for_status()
        result = response.json()
        if result["result"]["status"] != 200:
            message = result["result"].get("message", "unknown error")
            logging.error("APIエラー: %s", message)
            raise RuntimeError(f"API error: {message}")
        return result

    return call_with_retry(
        _do_request,
        retries=DMM_API_RETRIES,
        base_delay=DMM_API_RETRY_DELAY,
        log_label="DMM API",
    )


def fetch_items(
    site,
    service,
    floor,
    hits=1,
    offset=1,
    sort="rank",
    min_sample_count=10,
    supabase_client=None,
    keyword=None,
):
    client = default_supabase_client if supabase_client is None else supabase_client

    params = {
        "api_id": DMM_API_ID,
        "affiliate_id": DMM_AFFILIATE_ID,
        "site": site,
        "service": service,
        "hits": hits,
        "offset": offset,
        "sort": sort,
        "output": "json",
    }
    if floor is not None:
        params["floor"] = floor
    if keyword is not None:
        params["keyword"] = keyword

    result = _request_item_list(params)
    items = result["result"]["items"]

    filtered_items = []
    for item in items:
        content_id = item.get("content_id")
        if not content_id:
            continue

        try:
            existing = client.table("trn_dmm_items").select("id").eq("content_id", content_id).execute()
            if existing.data and len(existing.data) > 0:
                logging.info("[SKIP] 既に登録済み: %s", content_id)
                continue
        except Exception as e:
            logging.warning("[ERROR] Supabase 照会失敗: %s", e)
            continue

        sample_images = item.get("sampleImageURL", {}).get("sample_l", {}).get("image", [])
        if isinstance(sample_images, list):
            item["sampleMovieURL_highest"] = get_highest_resolution_movie(item.get("sampleMovieURL", {}))
            item["campaign_data"] = item.get("campaign", None)
            filtered_items.append(item)

    logging.info("サンプル画像 %d 枚以上のアイテム件数: %d", min_sample_count, len(filtered_items))
    return filtered_items


def fetch_items_merged_sorts(
    site,
    service,
    floor,
    hits=1,
    offset=1,
    sorts=("rank", "date", "review"),
    min_sample_count=10,
    supabase_client=None,
    keyword=None,
):
    merged = []
    seen = set()
    for sort_key in sorts:
        batch = fetch_items(
            site=site,
            service=service,
            floor=floor,
            hits=hits,
            offset=offset,
            sort=sort_key,
            min_sample_count=min_sample_count,
            supabase_client=supabase_client,
            keyword=keyword,
        )
        for item in batch:
            cid = item.get("content_id")
            if not cid or cid in seen:
                continue
            seen.add(cid)
            merged.append(item)
    logging.info(
        "統合取得完了 sorts=%s → %d 件（重複除去後）",
        sorts,
        len(merged),
    )
    return merged


def fetch_items_search_keyword(site, service, floor, keyword, hits=10, offset=1, sort="rank"):
    params = {
        "api_id": DMM_API_ID,
        "affiliate_id": DMM_AFFILIATE_ID,
        "site": site,
        "service": service,
        "floor": floor,
        "keyword": keyword,
        "hits": hits,
        "offset": offset,
        "sort": sort,
        "output": "json",
    }

    result = _request_item_list(params)
    formatted_response = json.dumps(result, ensure_ascii=False, indent=2)
    logging.info("APIレスポンス全文:\n%s", formatted_response)
    logging.info("取得件数: %d", len(result["result"]["items"]))
    return result["result"]["items"]
