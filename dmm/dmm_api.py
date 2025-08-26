import os
import requests
import logging
import json
from dotenv import load_dotenv

# .envファイル読み込み
load_dotenv()

# APIキー設定
DMM_API_ID = os.getenv("DMM_API_ID")
DMM_AFFILIATE_ID = os.getenv("DMM_AFFILIATE_ID")
API_URL = "https://api.dmm.com/affiliate/v3/ItemList"

# ログ用ディレクトリを作成（存在しなければ）
os.makedirs("logs", exist_ok=True)  

# ログ設定（ファイル + コンソール出力）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/dmm_itemlist.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

# ---------------------------------------------------------------------
# sampleMovieURL から最大解像度のURLを取得する関数
# ---------------------------------------------------------------------
def get_highest_resolution_movie(movie_info: dict):
    """
    sampleMovieURL 内のキーから最大解像度のURLを返す
    """
    if not isinstance(movie_info, dict):
        return None

    best_url = None
    best_area = 0  # 解像度の面積で比較 (width * height)

    for key, url in movie_info.items():
        if key.startswith("size_") and isinstance(url, str):
            try:
                # "size_560_360" -> width=560, height=360
                _, w, h = key.split("_")
                area = int(w) * int(h)
                if area > best_area:
                    best_area = area
                    best_url = url
            except Exception:
                continue

    return best_url


# ---------------------------------------------------------------------
# アイテム取得（サンプル画像枚数でフィルタリング）
# ---------------------------------------------------------------------
def fetch_items(site, service, floor, hits=1, offset=1, sort="rank", min_sample_count=10):
    params = {
        "api_id": DMM_API_ID,
        "affiliate_id": DMM_AFFILIATE_ID,
        "site": site,
        "service": service,
        "hits": hits,
        "offset": offset,
        "sort": sort,
        "output": "json"
    }
    # floor が None でなければ追加
    if floor is not None:
        params["floor"] = floor
    logging.info("DMM APIへリクエスト送信: %s", API_URL)
    logging.info("送信パラメータ: %s", params)

    try:
        response = requests.get(API_URL, params=params)
        response.raise_for_status()
    except requests.HTTPError as e:
        logging.error("HTTPエラー: %s", e)
        raise

    result = response.json()

    if result["result"]["status"] != 200:
        logging.error("APIエラー: %s", result["result"].get("message", "unknown error"))
        raise Exception("API error: " + result["result"].get("message", "unknown error"))

    items = result["result"]["items"]

    # logging.info(items)

    filtered_items = []
    for item in items:
        
        sample_images = item.get("sampleImageURL", {}).get("sample_l", {}).get("image", [])
        if isinstance(sample_images, list) :
            # 最大解像度の動画URLを付与
            item["sampleMovieURL_highest"] = get_highest_resolution_movie(item.get("sampleMovieURL", {}))
            item["campaign_data"] = item.get("campaign", None)  # ★ 追加

            filtered_items.append(item)

    logging.info("サンプル画像 %d 枚以上のアイテム件数: %d", min_sample_count, len(filtered_items))

    return filtered_items



# ---------------------------------------------------------------------
# キーワード検索でアイテム取得 メインでは未使用
# ---------------------------------------------------------------------
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
        "output": "json"
    }

    logging.info("DMM APIへリクエスト送信: %s", API_URL)
    logging.info("送信パラメータ: %s", params)

    try:
        response = requests.get(API_URL, params=params)
        response.raise_for_status()
    except requests.HTTPError as e:
        logging.error("HTTPエラー: %s", e)
        raise

    result = response.json()

    # レスポンス全体をログ出力
    formatted_response = json.dumps(result, ensure_ascii=False, indent=2)
    logging.info("APIレスポンス全文:\n%s", formatted_response)

    if result["result"]["status"] != 200:
        logging.error("APIエラー: %s", result["result"].get("message", "unknown error"))
        raise Exception("API error: " + result["result"].get("message", "unknown error"))

    logging.info("取得件数: %d", len(result["result"]["items"]))
    return result["result"]["items"]

# ---------------------------------------------------------------------
# テスト実行（例）
# ---------------------------------------------------------------------
if __name__ == "__main__":
    items = fetch_items(site="DMM.R18", service="digital", floor="doujin", hits=50, min_sample_count=10)
    for i, item in enumerate(items, 1):
        logging.info(
            "%d. タイトル: %s | サンプル枚数: %d | URL例: %s ...",
            i, item["title"], item["sample_count"], item["sample_urls"][:3]  # 最初の3枚だけ表示
        )
