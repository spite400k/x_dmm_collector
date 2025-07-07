from db.storage import upload_image_to_storage
from db.supabase_client import supabase
import logging

# ログ設定（ファイル + コンソール出力）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/dmm_itemlist.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

def insert_dmm_item(item: dict):
    content_id = item.get("content_id")
    if not content_id:
        logging.warning("content_id が存在しないためスキップ")
        return

    # 重複チェック
    exists = supabase.table("trn_dmm_items").select("id").eq("content_id", content_id).execute()
    if exists.data:
        logging.info(f"[SKIP] 既に登録済: {item.get('title')} : {item.get('URL')}")
        return

    review = item.get("review", {})
    image_url = item.get("imageURL", {})
    sample_images = item.get("sampleImageURL", {}).get("sample_l", {}).get("image", [])
    uploaded_paths = []

    for idx, img_url in enumerate(sample_images):
        storage_path = upload_image_to_storage(img_url, content_id=content_id, index=idx + 1)
        if storage_path:
            uploaded_paths.append(storage_path)

    prices = item.get("prices", {})
    iteminfo = item.get("iteminfo", {})

    genres_raw = iteminfo.get("genre", [])
    genre_names = [g["name"] for g in genres_raw]
    genre_ids = [g["id"] for g in genres_raw]

    data = {
        "content_id": content_id,
        "product_id": item.get("product_id"),
        "title": item.get("title"),
        "volume": item.get("volume"),
        "review_count": review.get("count"),
        "review_average": float(review.get("average", 0)),
        "item_url": item.get("URL"),
        "affiliate_url": item.get("affiliateURL"),
        "image_list_url": image_url.get("list"),
        "image_large_url": image_url.get("large"),
        "sample_images": uploaded_paths,
        "price": int(prices.get("price", "0").replace(",", "")),
        "list_price": int(prices.get("list_price", "0").replace(",", "")),
        "release_date": item.get("date"),
        "genres": genre_names,
        "genre_ids": genre_ids,
        "series": iteminfo.get("series", [{}])[0].get("name"),
        "maker": iteminfo.get("maker", [{}])[0].get("name"),
        "raw_json": item
    }

    supabase.table("trn_dmm_items").insert(data).execute()
    logging.info(f"[INSERT] {item.get('title')} : {item.get('URL')}")
