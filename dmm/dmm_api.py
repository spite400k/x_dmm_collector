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

# ログ設定（ファイル + コンソール出力）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/dmm_itemlist.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

def fetch_items(site, service, floor, hits=10, offset=1, sort="rank"):
    params = {
        "api_id": DMM_API_ID,
        "affiliate_id": DMM_AFFILIATE_ID,
        "site": site,
        "service": service,
        "floor": floor,
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

# テスト実行（例）
if __name__ == "__main__":
    items = fetch_items(site="DMM.R18", service="digital", floor="doujin")
    for item in items:
        logging.info("タイトル: %s", item["title"])
