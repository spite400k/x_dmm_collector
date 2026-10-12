from datetime import date

from utils.weekly_ranking_selection import (
    RANKING_MAX_FUTURE,
    RANKING_MAX_RELEASED_BEFORE_FUTURE,
    RANKING_RELEASE_WINDOW_DAYS,
    RANKING_TOTAL,
    completed_iso_year_week,
    merge_ranking_rows,
    previous_completed_iso_year_week,
)


def _row(content_id: str, score: float = 10.0) -> dict:
    return {
        "content_id": content_id,
        "title": content_id,
        "final_score": score,
        "review_count": 5,
        "avg_rating": 4.0,
    }


def test_merge_ranking_rows_keeps_released_and_one_future():
    released = [_row(f"released-{i}", 100 - i) for i in range(19)]
    future = _row("future-1", 0)

    rows = merge_ranking_rows(released, future)

    assert len(rows) == 20
    assert rows[-1]["content_id"] == "future-1"
    assert sum(1 for row in rows if row["content_id"].startswith("future-")) == 1


def test_merge_ranking_rows_skips_duplicate_future():
    released = [_row(f"released-{i}") for i in range(19)]
    future = _row("released-0", 0)

    rows = merge_ranking_rows(released, future)

    assert len(rows) == 19
    assert rows.count(future) == 0


def test_merge_ranking_rows_limits_released_before_future():
    released = [_row(f"released-{i}") for i in range(25)]
    future = _row("future-1", 0)

    rows = merge_ranking_rows(released, future)

    assert len(rows) == 20
    assert rows[-1]["content_id"] == "future-1"
    assert len([row for row in rows if row["content_id"].startswith("released-")]) == 19


def test_merge_ranking_rows_without_future():
    released = [_row(f"released-{i}") for i in range(10)]

    rows = merge_ranking_rows(released, None)

    assert len(rows) == 10


def test_ranking_constants():
    assert RANKING_MAX_RELEASED_BEFORE_FUTURE + RANKING_MAX_FUTURE == RANKING_TOTAL
    assert RANKING_RELEASE_WINDOW_DAYS == 90


def test_completed_iso_year_week_uses_finished_week_not_the_week_just_started():
    # 2026-10-12 は月曜。10月3週（ISO 42週）に入った直後なので、終わった 41週を返す。
    assert completed_iso_year_week(date(2026, 10, 12)) == (2026, 41)
    assert previous_completed_iso_year_week(date(2026, 10, 12)) == (2026, 40)
    # 週の途中と、その週が終わる日曜も、まだ当週は確定しない。
    assert completed_iso_year_week(date(2026, 10, 14)) == (2026, 41)
    assert completed_iso_year_week(date(2026, 10, 18)) == (2026, 41)
    # 翌月曜になってから、終わった 10月3週（ISO 42週）になる。
    assert completed_iso_year_week(date(2026, 10, 19)) == (2026, 42)
    assert previous_completed_iso_year_week(date(2026, 10, 19)) == (2026, 41)


def test_completed_iso_year_week_crosses_year_boundary():
    # 2026-01-01 は ISO 2026-W01 の途中。確定するのは 2025-W52。
    assert completed_iso_year_week(date(2026, 1, 1)) == (2025, 52)
    assert previous_completed_iso_year_week(date(2026, 1, 1)) == (2025, 51)
    assert completed_iso_year_week(date(2026, 1, 5)) == (2026, 1)


def test_completed_iso_year_week_defaults_to_today(monkeypatch):
    class _Date(date):
        @classmethod
        def today(cls):
            return date(2026, 10, 12)

    monkeypatch.setattr("utils.weekly_ranking_selection.date", _Date)
    assert completed_iso_year_week() == (2026, 41)
    assert previous_completed_iso_year_week() == (2026, 40)
