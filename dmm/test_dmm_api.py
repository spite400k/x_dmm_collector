import os
import requests
import logging
import json
from dotenv import load_dotenv

load_dotenv()

API_ID = os.getenv("DMM_API_ID")
AFFILIATE_ID = os.getenv("DMM_AFFILIATE_ID")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("dmm_api.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

def fetch_items():
    url = "https://api.dmm.com/affiliate/v3/ItemList"
    params = {
        "api_id": API_ID,
        "affiliate_id": AFFILIATE_ID,
        "site": "FANZA",
        "service": "doujin",
        "floor": "digital_doujin",
        #"cid": "d_429381",
        "keyword": "立ち読み",
        "hits": 10,
        "sort": "rank",
        "output": "json"
    }

    logging.info("Sending request to DMM API: %s", url)
    response = requests.get(url, params=params)
    
    try:
        response.raise_for_status()
    except requests.HTTPError as e:
        logging.error("HTTP error occurred: %s", e)
        raise

    data = response.json()

    # レスポンスを整形してログ出力（最大5000文字に制限なども可）
    formatted_json = json.dumps(data, ensure_ascii=False, indent=2)
    logging.info("DMM API response:\n%s", formatted_json)

    if data["result"]["status"] != 200:
        logging.error("API error: %s", data["result"].get("message", "Unknown error"))
        raise Exception(f"API error: {data['result'].get('message')}")

    logging.info("API response received successfully. Item count: %d", len(data["result"]["items"]))
    return data

if __name__ == "__main__":
    logging.info("Script started")
    try:
        data = fetch_items()
        for item in data["result"]["items"]:
            logging.info("Title: %s | URL: %s", item["title"], item["URL"])
    except Exception as e:
        logging.error("Exception occurred: %s", e)
    logging.info("Script finished")
