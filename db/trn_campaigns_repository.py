import logging
import traceback
from datetime import datetime, timedelta, timezone
from typing import Optional

from supabase import Client

from db.supabase_client import supabase
from dmm.dmm_campaign_api import resolve_feature_url, to_affiliate_feature_url
from utils.logger import setup_logger

setup_logger("trn_campaigns_repository.log")

JST = timezone(timedelta(hours=9))


def _campaign_period() -> tuple[str, str]:
    """開始: 当日0時(JST)、終了: 翌日0時(JST)"""
    today_jst = datetime.now(JST).replace(hour=0, minute=0, second=0, microsecond=0)
    start_at = today_jst.isoformat()
    end_at = (today_jst + timedelta(days=1)).isoformat()
    return start_at, end_at


def _normalize_text(value: Optional[str]) -> Optional[str]:
    if value in (None, ""):
        return None
    return value.strip()


def _upsert_campaign(campaign: dict, *, supabase_client: Client) -> bool:
    try:
        title = _normalize_text(campaign.get("title"))
        raw_url = _normalize_text(campaign.get("feature_url") or "")
        direct_url = resolve_feature_url(raw_url)
        feature_url = to_affiliate_feature_url(direct_url)

        if not title:
            logging.warning("[SKIP] title なし: %s", feature_url)
            return False
        if not feature_url:
            logging.warning("[SKIP] feature_url なし: %s", title)
            return False

        existing = (
            supabase_client.table("trn_campaigns")
            .select("id")
            .in_("feature_url", [feature_url, direct_url, raw_url])
            .execute()
        )

        now = datetime.now(timezone.utc).isoformat()
        start_at, end_at = _campaign_period()
        data = {
            "title": title,
            "description": _normalize_text(campaign.get("description")),
            "feature_url": feature_url,
            "picture_url": _normalize_text(campaign.get("picture_url")),
            "type": campaign.get("type") or "all",
            "service": campaign.get("service") or "all",
            "floor": campaign.get("floor") or "all",
            "priority": campaign.get("priority", 100),
            "is_active": campaign.get("is_active", True),
            "start_at": campaign.get("start_at") or start_at,
            "end_at": campaign.get("end_at") or end_at,
            "updated_at": now,
        }

        if existing.data:
            campaign_id = existing.data[0]["id"]
            supabase_client.table("trn_campaigns").update(data).eq("id", campaign_id).execute()
            logging.info("[UPDATE] 成功: %s (%s)", title, feature_url)
        else:
            data["created_at"] = now
            supabase_client.table("trn_campaigns").insert(data).execute()
            logging.info("[INSERT] 成功: %s (%s)", title, feature_url)

        return True
    except Exception as exc:
        logging.error("upsert_campaign 失敗: %s", exc)
        logging.error(traceback.format_exc())
        return False


def upsert_campaign(campaign: dict) -> bool:
    return _upsert_campaign(campaign, supabase_client=supabase)
