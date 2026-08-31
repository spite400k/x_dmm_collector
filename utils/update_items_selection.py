"""update_items / update_mesugaki の更新対象抽出（DB・API 非依存）。"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Sequence

UPDATE_MODES = ("daily", "weekly", "all")
DEFAULT_RECENT_DAYS = 60
DEFAULT_MISS_LIMIT = 3
DEFAULT_SKIP_DAYS = 30


def parse_release_date(value: Any) -> date | None:
    """trn_dmm_items.release_date（text）を date にする。不正値は None。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    if "T" in text:
        text = text.split("T", 1)[0]
    elif " " in text:
        text = text.split(" ", 1)[0]
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def parse_aware_datetime(value: Any) -> datetime | None:
    """skip_until / last_ok_at を UTC 付き datetime にする。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        dt = datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)
    else:
        text = str(value).strip()
        if not text:
            return None
        text = text.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            parsed_date = parse_release_date(text)
            if parsed_date is None:
                return None
            parsed = datetime.combine(
                parsed_date, datetime.min.time(), tzinfo=timezone.utc
            )
        if isinstance(parsed, datetime):
            dt = parsed
        elif isinstance(parsed, date):  # pragma: no cover - 3.10 の fromisoformat は date を返さない
            dt = datetime.combine(parsed, datetime.min.time(), tzinfo=timezone.utc)
        else:  # pragma: no cover - fromisoformat は date/datetime 以外を返さない
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def has_active_campaign(campaign: Any) -> bool:
    """商品の campaign 列に中身があるか。空 list / 空 dict / 空文字はなし。"""
    if campaign is None:
        return False
    if isinstance(campaign, str):
        t = campaign.strip().lower()
        return bool(t) and t not in ("null", "none", "[]", "{}")
    if isinstance(campaign, (list, tuple, set)):
        return len(campaign) > 0
    if isinstance(campaign, dict):
        return len(campaign) > 0
    return True


def is_released(release_date: Any, *, today: date) -> bool:
    """配信開始日が today 以前。未来日・日付不明は False。"""
    parsed = parse_release_date(release_date)
    if parsed is None:
        return False
    return parsed <= today


def is_recent_release(
    release_date: Any,
    *,
    today: date,
    recent_days: int = DEFAULT_RECENT_DAYS,
) -> bool:
    """発売日が today から recent_days 以内の配信済み作品。未来日・日付不明は False。"""
    days = max(int(recent_days), 0)
    parsed = parse_release_date(release_date)
    if parsed is None:
        return False
    if parsed > today:
        return False
    delta = (today - parsed).days
    return delta <= days


def in_daily_window(
    row: dict,
    *,
    today: date,
    recent_days: int = DEFAULT_RECENT_DAYS,
) -> bool:
    """毎日更新対象: 直近発売（配信済み）または campaign あり。"""
    return is_recent_release(
        row.get("release_date"),
        today=today,
        recent_days=recent_days,
    ) or has_active_campaign(row.get("campaign"))


def is_api_skip_active(skip_until: Any, *, now: datetime) -> bool:
    """skip_until が now より後なら休止中。"""
    parsed = parse_aware_datetime(skip_until)
    if parsed is None:
        return False
    clock = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    return parsed > clock


def should_update_item(
    row: dict,
    *,
    mode: str,
    today: date,
    recent_days: int = DEFAULT_RECENT_DAYS,
    now: datetime | None = None,
    retry_skipped: bool = False,
    content_ids: Sequence[str] | None = None,
) -> bool:
    """mode=daily / weekly / all。content_id 指定時は他条件を無視する。"""
    if content_ids:
        return row.get("content_id") in set(content_ids)
    clock = now or datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)
    if not retry_skipped and is_api_skip_active(row.get("skip_until"), now=clock):
        return False
    normalized = (mode or "daily").strip().lower()
    if normalized == "all":
        return True
    daily = in_daily_window(row, today=today, recent_days=recent_days)
    if normalized == "weekly":
        return not daily
    return daily


def merge_api_state(items: Iterable[dict], states: Iterable[dict]) -> list[dict]:
    """ItemList 休止情報を作品行へ載せる。"""
    by_id = {
        str(state["content_id"]): state
        for state in states
        if state.get("content_id")
    }
    merged: list[dict] = []
    for row in items:
        out = dict(row)
        state = by_id.get(str(out.get("content_id") or ""), {})
        out["miss_count"] = state.get("miss_count", 0)
        out["last_ok_at"] = state.get("last_ok_at")
        out["skip_until"] = state.get("skip_until")
        merged.append(out)
    return merged


def filter_items_for_update(
    rows: Iterable[dict],
    *,
    mode: str,
    today: date | None = None,
    recent_days: int = DEFAULT_RECENT_DAYS,
    now: datetime | None = None,
    retry_skipped: bool = False,
    content_ids: Sequence[str] | None = None,
) -> list[dict]:
    """順序を保ったまま対象行だけ返す。"""
    day = today or date.today()
    return [
        row
        for row in rows
        if should_update_item(
            row,
            mode=mode,
            today=day,
            recent_days=recent_days,
            now=now,
            retry_skipped=retry_skipped,
            content_ids=content_ids,
        )
    ]


def _as_miss_count(value: Any) -> int:
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def next_api_state_on_success(*, now: datetime) -> dict:
    clock = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    return {
        "miss_count": 0,
        "last_ok_at": clock.isoformat(),
        "skip_until": None,
    }


def next_api_state_on_miss(
    current_state: dict | None,
    *,
    now: datetime,
    miss_limit: int = DEFAULT_MISS_LIMIT,
    skip_days: int = DEFAULT_SKIP_DAYS,
) -> dict:
    clock = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    current = current_state or {}
    miss = _as_miss_count(current.get("miss_count")) + 1
    skip_until = None
    if miss >= miss_limit:
        skip_until = (clock + timedelta(days=skip_days)).isoformat()
    return {
        "miss_count": miss,
        "last_ok_at": current.get("last_ok_at"),
        "skip_until": skip_until,
    }


def build_update_mode_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--mode",
        choices=UPDATE_MODES,
        default="daily",
        help="daily: 直近発売+キャンペーン / weekly: それ以外 / all: 全件",
    )
    parser.add_argument(
        "--recent-days",
        type=int,
        default=DEFAULT_RECENT_DAYS,
        help="毎日対象とする発売日の日数（デフォルト 60）",
    )
    parser.add_argument(
        "--content-id",
        action="append",
        dest="content_ids",
        default=None,
        help="指定 ID のみ更新（発売日・休止を無視）。複数可",
    )
    parser.add_argument(
        "--retry-skipped",
        action="store_true",
        help="api_skip 中の作品も対象に含める",
    )
    return parser


def parse_update_mode_args(
    argv: Sequence[str] | None = None,
    *,
    description: str = "trn_dmm_items の DMM API 更新",
) -> argparse.Namespace:
    return build_update_mode_parser(description).parse_args(argv)
