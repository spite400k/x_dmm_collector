from db.storage import upload_image_to_storage
from db.supabase_client import supabase
import logging
from openai_api.content_generator import generate_content
import re

# ログ設定（ファイル + コンソール出力）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/dmm_itemlist.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

def insert_dmm_item(item: dict, site, service, floor):
    content_id = item.get("content_id")
    if not content_id:
        logging.warning("content_id が存在しないためスキップ")
        return

    # 重複チェック
    exists = supabase.table("trn_dmm_items").select("id").eq("content_id", content_id).execute()
    if exists.data:
        logging.info(f"[SKIP] 既に登録済: {item.get('title')} : {item.get('URL')}")
        return

    sample_images = item.get("sampleImageURL", {}).get("sample_l", {}).get("image", [])
    uploaded_paths = []

    for idx, img_url in enumerate(sample_images):
        storage_path = upload_image_to_storage(img_url, content_id=content_id, index=idx + 1)
        if storage_path:
            uploaded_paths.append(storage_path)

    iteminfo = item.get("iteminfo", {})

    genres_raw = iteminfo.get("genre", [])
    genre_names = [g["name"] for g in genres_raw]
    genre_ids = [g["id"] for g in genres_raw]

    # --- OpenAIで文章生成 ---
    ai_content = generate_content(item)


    def parse_price(price_str):
        if not price_str:
            return None
        match = re.search(r'\d+', price_str.replace(',', ''))
        if match:
            return int(match.group())
        return None

    price = parse_price(item.get("prices", {}).get("price"))  # → 4200
    list_price = parse_price(item.get("prices", {}).get("list_price"))  # → 5000


    data = {
        "content_id": content_id,
        "product_id": item.get("product_id"),
        "site": site,
        "service": service,
        "floor": floor,
        "title": item.get("title"),
        "volume": item.get("volume"),
        "review_count": item.get("review", {}).get("count"),
        "review_average": item.get("review", {}).get("average"),
        "item_url": item.get("URL"),
        "affiliate_url": item.get("affiliateURL"),
        "image_list_url": item.get("imageURL", {}).get("list"),
        "image_large_url": item.get("imageURL", {}).get("large"),
        "sample_images": item.get("sampleImageURL", {}).get("sample_l", {}).get("image", []),
        "price": price,
        "list_price": list_price,
        "release_date": item.get("date"),
        "genres": genre_names,
        "genre_ids": genre_ids,
        "series": item.get("iteminfo", {}).get("series", [{}])[0].get("name"),
        "maker": item.get("iteminfo", {}).get("maker", [{}])[0].get("name"),
        "tachiyomi_url": item.get("tachiyomi", {}).get("URL"),
        "tachiyomi_affiliate_url": item.get("tachiyomi", {}).get("affiliateURL"),
        "auto_comment": ai_content["auto_comment"],
        "auto_summary": ai_content["auto_summary"],
        "auto_point": ai_content["auto_point"],
        "raw_json": item,
    }

    supabase.table("trn_dmm_items").insert(data).execute()
    logging.info(f"[INSERT] {item.get('title')} : {item.get('URL')}")
