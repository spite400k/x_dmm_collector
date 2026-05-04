from db.storageS3 import (
    upload_local_image_to_s3 as upload_local_image_to_s3_default,
    upload_local_image_to_s3_bucket3,
)
from db.supabase_client import supabase, supabase2, supabase3
import logging
from openai_api.content_generator import generate_content
import re
import traceback
from typing import Callable, Optional

from supabase import Client

from utils.logger import setup_logger

# ZIP ローテート付きログ設定
setup_logger("trn_dmm_items_repository.log")

UploadFn = Callable[..., Optional[str]]


# ---------------------------------------------------------------------
# 価格を整数に変換する関数
# ---------------------------------------------------------------------
def parse_price(price_str):
    if not price_str:
        return None
    match = re.search(r"\d+", price_str.replace(",", ""))
    if match:
        return int(match.group())
    return None


# ----------------------------------------------------
# []→null
# ----------------------------------------------------
def normalize_field(v):
    return None if v in (None, [], "") else v


def _insert_dmm_item(
    item: dict,
    tachiyomi_image_paths,
    sample_movie_path,
    site,
    service,
    floor,
    *,
    supabase_client: Client,
    upload_local_image_to_s3_fn: UploadFn,
    coerce_empty_image_urls: bool,
):
    try:
        content_id = item.get("content_id")
        title = item.get("title")
        url = item.get("URL")

        if not content_id:
            logging.warning(f"[SKIP] content_id が存在しない: {title} : {url}")
            return

        # 重複チェック
        exists = (
            supabase_client.table("trn_dmm_items")
            .select("id")
            .eq("content_id", content_id)
            .execute()
        )
        if exists.data:
            logging.info(f"[SKIP] 既に登録済: {title} ({content_id}) : {url}")
            return

        logging.info(f"[START] 登録処理開始: {title} ({content_id})")

        uploaded_paths = []
        # 立ち読み画像を先にアップロード
        if tachiyomi_image_paths:
            logging.info(f" 立ち読み画像を取得: {title} : {url}")
            for idx, img_url in enumerate(tachiyomi_image_paths):
                storage_path = upload_local_image_to_s3_fn(
                    img_url, content_id=content_id, index=idx + 1, floor=floor
                )
                if storage_path:
                    uploaded_paths.append(storage_path)
                else:
                    logging.error(f"  [IMG-FAIL] Tachiyomi {idx+1}: {img_url}")

        sample_images = (
            item.get("sampleImageURL", {}).get("sample_l", {}).get("image")
        )
        sample_images_s = (
            item.get("sampleImageURL", {}).get("sample_s", {}).get("image")
        )

        # ジャンル情報を抽出
        iteminfo = item.get("iteminfo", {})
        genres_raw = iteminfo.get("genre", [])
        genre_names = [g["name"] for g in genres_raw]
        genre_ids = [g["id"] for g in genres_raw]

        # --- OpenAIで文章生成 ---
        ai_content = generate_content(item) or {}

        price = parse_price(item.get("prices", {}).get("price"))
        list_price = parse_price(item.get("prices", {}).get("list_price"))

        # メーカー名
        maker_list = iteminfo.get("maker") or iteminfo.get("manufacture") or [{}]
        maker = maker_list[0].get("name")

        if coerce_empty_image_urls:
            image_large_url = item.get("imageURL", {}).get("large") or None
            image_small_url = item.get("imageURL", {}).get("small") or None
        else:
            image_large_url = item.get("imageURL", {}).get("large")
            image_small_url = item.get("imageURL", {}).get("small")

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
            "image_large_url": image_large_url,
            "image_small_url": image_small_url,
            "sample_images": sample_images,
            "sample_images_s": sample_images_s,
            "sample_movie_url": item.get("sampleMovieURL_highest"),
            "price": price,
            "list_price": list_price,
            "release_date": item.get("date"),
            "genres": normalize_field(genre_names),
            "genre_ids": normalize_field(genre_ids),
            "series": iteminfo.get("series", [{}])[0].get("name"),
            "maker": maker,
            "campaign": item.get("campaign_data"),
            "actress": normalize_field(iteminfo.get("actress")),
            "director": normalize_field(iteminfo.get("director")),
            "author": item.get("author"),
            "category_name": item.get("category_name"),
            "tachiyomi_url": item.get("tachiyomi", {}).get("URL"),
            "tachiyomi_affiliate_url": item.get("tachiyomi", {}).get("affiliateURL"),
            "auto_comment": ai_content.get("auto_comment", ""),
            "auto_summary": ai_content.get("auto_summary", ""),
            "auto_point": ai_content.get("auto_point", ""),
            "raw_json": item,
        }

        supabase_client.table("trn_dmm_items").insert(data).execute()
        logging.info(f"[INSERT] 成功: {title} ({content_id}) : {url}")

    except Exception as e:
        logging.error(f" insert_dmm_item 失敗: {e}")
        logging.error(traceback.format_exc())


# ---------------------------------------------------------------------
# DMMアイテムをSupabaseのtrn_dmm_itemsテーブルに挿入（既定DB / 既定S3）
# ---------------------------------------------------------------------
def insert_dmm_item(item: dict, tachiyomi_image_paths, sample_movie_path, site, service, floor):
    _insert_dmm_item(
        item,
        tachiyomi_image_paths,
        sample_movie_path,
        site,
        service,
        floor,
        supabase_client=supabase,
        upload_local_image_to_s3_fn=upload_local_image_to_s3_default,
        coerce_empty_image_urls=True,
    )


def insert_dmm_item_supabase2(item: dict, tachiyomi_image_paths, sample_movie_path, site, service, floor):
    """SUPABASE_URL2 向け（立ち読み画像は storageS3 と同じバケット設定）。"""
    _insert_dmm_item(
        item,
        tachiyomi_image_paths,
        sample_movie_path,
        site,
        service,
        floor,
        supabase_client=supabase2,
        upload_local_image_to_s3_fn=upload_local_image_to_s3_default,
        coerce_empty_image_urls=False,
    )


def insert_dmm_item_supabase3(item: dict, tachiyomi_image_paths, sample_movie_path, site, service, floor):
    """SUPABASE_URL3 向け（立ち読み画像は S3_BUCKET_3）。"""
    _insert_dmm_item(
        item,
        tachiyomi_image_paths,
        sample_movie_path,
        site,
        service,
        floor,
        supabase_client=supabase3,
        upload_local_image_to_s3_fn=upload_local_image_to_s3_bucket3,
        coerce_empty_image_urls=False,
    )
