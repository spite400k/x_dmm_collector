import logging
import traceback
from datetime import datetime, timezone
from typing import Optional

from supabase import Client

from db.supabase_client import supabase
from utils.logger import setup_logger

setup_logger("mst_actress_repository.log")

UPDATABLE_FIELDS = (
    "name",
    "name_kana",
    "name_en",
    "image_url",
    "bust",
    "cup",
    "waist",
    "hip",
    "height",
    "birthday",
    "blood_type",
    "hobby",
    "prefectures",
    "x_account",
    "profile",
    "career_text",
    "fanza_activity",
    "awards",
    "favorite_count",
    "debut_date",
    "works_count",
    "alias",
)


def fetch_actresses_to_enrich(
    *,
    limit: int = 20,
    supabase_client: Client,
) -> list[dict]:
    response = (
        supabase_client.table("mst_actress")
        .select("id, actress_id, name, updated_at, profile, works_count")
        .order("updated_at", desc=False)
        .limit(limit)
        .execute()
    )
    return response.data or []


def update_actress(
    actress_id: int,
    data: dict,
    *,
    supabase_client: Client,
) -> bool:
    try:
        existing = (
            supabase_client.table("mst_actress")
            .select("id")
            .eq("actress_id", actress_id)
            .execute()
        )
        if not existing.data:
            logging.warning("[SKIP] mst_actress に存在しません actress_id=%s", actress_id)
            return False

        now = datetime.now(timezone.utc).isoformat()
        update_data = {"updated_at": now}
        for field in UPDATABLE_FIELDS:
            value = data.get(field)
            if value not in (None, ""):
                update_data[field] = value

        row_id = existing.data[0]["id"]
        supabase_client.table("mst_actress").update(update_data).eq("id", row_id).execute()
        logging.info("[UPDATE] 成功 actress_id=%s name=%s", actress_id, data.get("name"))
        return True
    except Exception as exc:
        logging.error("update_actress 失敗 actress_id=%s: %s", actress_id, exc)
        logging.error(traceback.format_exc())
        return False


def enrich_and_update_actress(
    actress_id: int,
    enriched_data: dict,
    *,
    supabase_client: Optional[Client] = None,
) -> bool:
    client = supabase if supabase_client is None else supabase_client
    return update_actress(actress_id, enriched_data, supabase_client=client)


def touch_actress_updated_at(
    actress_id: int,
    *,
    supabase_client: Client,
) -> bool:
    try:
        existing = (
            supabase_client.table("mst_actress")
            .select("id")
            .eq("actress_id", actress_id)
            .execute()
        )
        if not existing.data:
            logging.warning("[SKIP] mst_actress に存在しません actress_id=%s", actress_id)
            return False

        now = datetime.now(timezone.utc).isoformat()
        row_id = existing.data[0]["id"]
        supabase_client.table("mst_actress").update({"updated_at": now}).eq("id", row_id).execute()
        logging.info("[TOUCH] 更新対象なしのため updated_at のみ更新 actress_id=%s", actress_id)
        return True
    except Exception as exc:
        logging.error("touch_actress_updated_at 失敗 actress_id=%s: %s", actress_id, exc)
        logging.error(traceback.format_exc())
        return False
