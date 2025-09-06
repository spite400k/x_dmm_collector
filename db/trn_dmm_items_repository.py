from db.storage import upload_image_to_storage, upload_local_image_to_storage
from db.supabase_client import supabase
import logging
from openai_api.content_generator import generate_content
import re
import traceback

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
# 価格を整数に変換する関数
# ---------------------------------------------------------------------
def parse_price(price_str):
    if not price_str:
        return None
    match = re.search(r'\d+', price_str.replace(',', ''))
    if match:
        return int(match.group())
    return None

# ---------------------------------------------------------------------
# DMMアイテムをSupabaseのtrn_dmm_itemsテーブルに挿入
# ---------------------------------------------------------------------
def insert_dmm_item(item: dict, tachiyomi_image_paths, site, service, floor):
    try:
        content_id = item.get("content_id")
        title = item.get("title")
        url = item.get("URL")

        if not content_id:
            logging.warning(f"[SKIP] content_id が存在しない: {title} : {url}")
            return

        # 重複チェック
        exists = supabase.table("trn_dmm_items").select("id").eq("content_id", content_id).execute()
        if exists.data:
            logging.info(f"[SKIP] 既に登録済: {title} ({content_id}) : {url}")
            return

        logging.info(f"[START] 登録処理開始: {title} ({content_id})")

        uploaded_paths = []
        # 立ち読み画像を先にアップロード
        if not tachiyomi_image_paths:
            logging.warning(f"[WARN] 立ち読み画像パスが空: {title} : {url}")

        for idx, img_url in enumerate(tachiyomi_image_paths):
            storage_path = upload_local_image_to_storage(img_url, content_id=content_id, index=idx + 1)
            if storage_path:
                logging.info(f"  [IMG-UPLOAD] Tachiyomi {idx+1}: {storage_path}")
                uploaded_paths.append(storage_path)
            else:
                logging.error(f"  [IMG-FAIL] Tachiyomi {idx+1}: {img_url}")

        # サンプル画像をアップロード
        sample_urls = item.get("sampleImageURL", {}).get("list", [])
        for idx, img_url in enumerate(sample_urls):
            storage_path = upload_image_to_storage(img_url, content_id=content_id, index=idx + 1 + len(tachiyomi_image_paths))
            if storage_path:
                logging.info(f"  [IMG-UPLOAD] Sample {idx+1}: {storage_path}")
                uploaded_paths.append(storage_path)
            else:
                logging.error(f"  [IMG-FAIL] Sample {idx+1}: {img_url}")

        # ジャンル情報を抽出
        iteminfo = item.get("iteminfo", {})
        genres_raw = iteminfo.get("genre", [])
        genre_names = [g["name"] for g in genres_raw]
        genre_ids = [g["id"] for g in genres_raw]
        logging.info(f"  [GENRES] {genre_names}")

        # --- OpenAIで文章生成 ---
        ai_content = generate_content(item) or {}
        logging.info("  [AI] 自動生成テキスト取得成功")

        price = parse_price(item.get("prices", {}).get("price"))
        list_price = parse_price(item.get("prices", {}).get("list_price"))
        logging.info(f"  [PRICE] price={price}, list_price={list_price}")

        data = {
            "content_id": content_id,
            "product_id": item.get("product_id"),
            "site": site,
            "service": service,
            "floor": floor,
            "title": title,
            "volume": item.get("volume"),
            "review_count": item.get("review", {}).get("count"),
            "review_average": item.get("review", {}).get("average"),
            "item_url": url,
            "affiliate_url": item.get("affiliateURL"),
            "image_list_url": item.get("imageURL", {}).get("list"),
            "image_large_url": item.get("imageURL", {}).get("large"),
            "sample_images": uploaded_paths,
            "sample_movie_url": item.get("sampleMovieURL_highest"),
            "price": price,
            "list_price": list_price,
            "release_date": item.get("date"),
            "genres": genre_names,
            "genre_ids": genre_ids,
            "series": iteminfo.get("series", [{}])[0].get("name"),
            "maker": iteminfo.get("maker", [{}])[0].get("name"),
            "tachiyomi_url": item.get("tachiyomi", {}).get("URL"),
            "tachiyomi_affiliate_url": item.get("tachiyomi", {}).get("affiliateURL"),
            "auto_comment": ai_content.get("auto_comment", ""),
            "auto_summary": ai_content.get("auto_summary", ""),
            "auto_point": ai_content.get("auto_point", ""),
            "raw_json": item,
            "campaign": item.get("campaign_data"),
        }

        supabase.table("trn_dmm_items").insert(data).execute()
        logging.info(f"[INSERT] 成功: {title} ({content_id}) : {url}")

    except Exception as e:
        logging.error(f"[ERROR] insert_dmm_item 失敗: {e}")
        logging.error(traceback.format_exc())
