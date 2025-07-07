import os
import requests
import logging
import json
from dotenv import load_dotenv

load_dotenv()

API_ID = os.getenv("DMM_API_ID")
AFFILIATE_ID = os.getenv("DMM_AFFILIATE_ID")

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("dmm_floorlist.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

def fetch_floorlist(site="DMM.R18"):
    url = "https://api.dmm.com/affiliate/v3/FloorList"
    params = {
        "api_id": API_ID,
        "affiliate_id": AFFILIATE_ID,
        "output": "json"
    }

    logging.info("DMM FloorList APIへリクエスト送信: %s", url)
    response = requests.get(url, params=params)

    try:
        response.raise_for_status()
    except requests.HTTPError as e:
        logging.error("HTTPエラー発生: %s", e)
        raise

    data = response.json()
    formatted_json = json.dumps(data, ensure_ascii=False, indent=2)
    logging.info("APIレスポンス内容:\n%s", formatted_json)

    return data

if __name__ == "__main__":
    logging.info("スクリプト開始")
    try:
        floors = fetch_floorlist()
        for floor in floors.get("result", []):
            logging.info("floor_id: %s, name: %s", floor.get("floor_id"), floor.get("name"))
    except Exception as e:
        logging.error("例外発生: %s", e)
    logging.info("スクリプト終了")
