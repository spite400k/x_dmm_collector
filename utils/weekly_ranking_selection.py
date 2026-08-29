"""週次ランキングの作品選定ロジック。"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

RANKING_RELEASE_WINDOW_DAYS = 31
RANKING_TOTAL = 20
RANKING_MAX_RELEASED_BEFORE_FUTURE = 19
RANKING_MAX_FUTURE = 1

_RELEASED_BASE_SQL = """
    SELECT
        c.content_id,
        c.title,
        s.final_score,
        s.review_count,
        s.avg_rating
    FROM trn_dmm_items c
    JOIN LATERAL (
        SELECT *
        FROM trn_dmm_score_history s
        WHERE s.content_id = c.content_id
        ORDER BY s.snapshot_date DESC
        LIMIT 1
    ) s ON true
    WHERE c.service = %s
      AND c.floor = %s
      AND c.release_date::date >= %s::date
      AND c.release_date::date <= %s::date
      AND s.final_score > 0
      AND s.review_count > 0
"""

_FUTURE_BASE_SQL = """
    SELECT
        c.content_id,
        c.title,
        s.final_score,
        s.review_count,
        s.avg_rating
    FROM trn_dmm_items c
    JOIN LATERAL (
        SELECT *
        FROM trn_dmm_score_history s
        WHERE s.content_id = c.content_id
        ORDER BY s.snapshot_date DESC
        LIMIT 1
    ) s ON true
    WHERE c.service = %s
      AND c.floor = %s
      AND c.release_date::date > %s::date
"""


def merge_ranking_rows(
    released_rows: list[dict[str, Any]],
    future_row: dict[str, Any] | None,
    *,
    max_total: int = RANKING_TOTAL,
    max_released_before_future: int = RANKING_MAX_RELEASED_BEFORE_FUTURE,
    max_future: int = RANKING_MAX_FUTURE,
) -> list[dict[str, Any]]:
    """配信済み・未来作品をマージして最大 max_total 件にする。"""
    rows: list[dict[str, Any]] = list(released_rows[:max_released_before_future])
    selected_ids = {row["content_id"] for row in rows}

    if future_row and max_future > 0 and future_row["content_id"] not in selected_ids:
        rows.append(future_row)
        selected_ids.add(future_row["content_id"])

    return rows[:max_total]


def _fetch_released_rows(
    cur,
    service: str,
    floor: str,
    release_min: str,
    release_max: str,
    limit: int,
    exclude_ids: set[str],
) -> list[dict[str, Any]]:
    sql = _RELEASED_BASE_SQL
    params: list[Any] = [service, floor, release_min, release_max]
    if exclude_ids:
        sql += " AND NOT (c.content_id = ANY(%s))"
        params.append(list(exclude_ids))
    sql += """
      ORDER BY s.final_score DESC, s.review_count DESC, c.content_id
      LIMIT %s
    """
    params.append(limit)
    cur.execute(sql, params)
    return cur.fetchall()


def _fetch_future_row(
    cur,
    service: str,
    floor: str,
    today_iso: str,
    exclude_ids: set[str],
) -> dict[str, Any] | None:
    sql = _FUTURE_BASE_SQL
    params: list[Any] = [service, floor, today_iso]
    if exclude_ids:
        sql += " AND NOT (c.content_id = ANY(%s))"
        params.append(list(exclude_ids))
    sql += """
      ORDER BY c.release_date ASC, s.final_score DESC NULLS LAST, c.content_id
      LIMIT 1
    """
    cur.execute(sql, params)
    return cur.fetchone()


def fetch_weekly_ranking_rows(
    cur,
    service: str,
    floor: str,
    *,
    today: date | None = None,
) -> list[dict[str, Any]]:
    """配信済み（評価あり）を優先し、未来作品は最大1件だけ追加する。"""
    today = today or date.today()
    release_min = (today - timedelta(days=RANKING_RELEASE_WINDOW_DAYS)).isoformat()
    release_max = today.isoformat()

    released_primary = _fetch_released_rows(
        cur,
        service,
        floor,
        release_min,
        release_max,
        RANKING_MAX_RELEASED_BEFORE_FUTURE,
        exclude_ids=set(),
    )
    selected_ids = {row["content_id"] for row in released_primary}

    future_row = _fetch_future_row(cur, service, floor, release_max, selected_ids)
    rows = merge_ranking_rows(released_primary, future_row)
    selected_ids = {row["content_id"] for row in rows}

    remaining = RANKING_TOTAL - len(rows)
    if remaining > 0:
        backfill = _fetch_released_rows(
            cur,
            service,
            floor,
            release_min,
            release_max,
            remaining,
            exclude_ids=selected_ids,
        )
        rows.extend(backfill)

    return rows[:RANKING_TOTAL]
