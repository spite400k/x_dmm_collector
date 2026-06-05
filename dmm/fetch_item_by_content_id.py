import os
import requests

def fetch_item_by_content_id(content_id: str):
    """content_idを使ってDMM APIから作品情報を取得"""
    API_ID = os.getenv("DMM_API_ID")
    AFFILIATE_ID = os.getenv("DMM_AFFILIATE_ID")

    url = "https://api.dmm.com/affiliate/v3/ItemList"
    params = {
        "api_id": API_ID,
        "affiliate_id": AFFILIATE_ID,
        "site": "DMM.R18",
        "cid": content_id,
        "output": "json"
    }

    res = requests.get(url, params=params)
    if res.status_code != 200:
        raise Exception(f"APIエラー: {res.status_code}")

    data = res.json()
    result = data.get("result", {}).get("items", [])

    if not result:
        return None

    return result[0]
