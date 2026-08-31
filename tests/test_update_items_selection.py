"""update_items 対象抽出の純粋関数テスト。"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from utils.update_items_selection import (
    DEFAULT_RECENT_DAYS,
    filter_items_for_update,
    has_active_campaign,
    in_daily_window,
    is_api_skip_active,
    is_recent_release,
    is_released,
    merge_api_state,
    next_api_state_on_miss,
    next_api_state_on_success,
    parse_aware_datetime,
    parse_release_date,
    parse_update_mode_args,
    should_update_item,
)

TODAY = date(2026, 8, 19)
NOW = datetime(2026, 8, 19, 8, 0, tzinfo=timezone.utc)
NAIVE_NOW = datetime(2026, 8, 19, 8, 0)


class TestParseReleaseDate:
    def test_none_and_empty(self):
        assert parse_release_date(None) is None
        assert parse_release_date("") is None
        assert parse_release_date("  ") is None

    def test_iso_variants(self):
        assert parse_release_date("2026-08-01") == date(2026, 8, 1)
        assert parse_release_date("2026-08-01 10:00:00") == date(2026, 8, 1)
        assert parse_release_date("2026-08-01T10:00:00+09:00") == date(2026, 8, 1)
        assert parse_release_date("2026-08-01T10:00:00Z") == date(2026, 8, 1)
        assert parse_release_date(date(2026, 8, 1)) == date(2026, 8, 1)
        assert parse_release_date(datetime(2026, 8, 1, 12, 0)) == date(2026, 8, 1)

    def test_invalid(self):
        assert parse_release_date("not-a-date") is None
        assert parse_release_date("2026/08/01") is None


class TestParseAwareDatetime:
    def test_none_and_empty(self):
        assert parse_aware_datetime(None) is None
        assert parse_aware_datetime("") is None
        assert parse_aware_datetime("  ") is None
        assert parse_aware_datetime("not-a-date") is None

    def test_datetime_and_date(self):
        aware = datetime(2026, 8, 19, 8, 0, tzinfo=timezone.utc)
        assert parse_aware_datetime(aware) == aware
        naive = parse_aware_datetime(datetime(2026, 8, 19, 8, 0))
        assert naive.tzinfo == timezone.utc
        as_date = parse_aware_datetime(date(2026, 8, 20))
        assert as_date == datetime(2026, 8, 20, 0, 0, tzinfo=timezone.utc)

    def test_iso_strings(self):
        parsed = parse_aware_datetime("2026-09-18T00:00:00Z")
        assert parsed == datetime(2026, 9, 18, tzinfo=timezone.utc)
        date_only = parse_aware_datetime("2026-09-18")
        assert date_only == datetime(2026, 9, 18, tzinfo=timezone.utc)
        fallback = parse_aware_datetime("2026-08-01xxx")
        assert fallback == datetime(2026, 8, 1, tzinfo=timezone.utc)
        assert parse_aware_datetime(123) is None


class TestHasActiveCampaign:
    def test_empty_values(self):
        assert has_active_campaign(None) is False
        assert has_active_campaign("") is False
        assert has_active_campaign("  ") is False
        assert has_active_campaign("null") is False
        assert has_active_campaign("[]") is False
        assert has_active_campaign("{}") is False
        assert has_active_campaign([]) is False
        assert has_active_campaign({}) is False
        assert has_active_campaign(()) is False
        assert has_active_campaign(set()) is False

    def test_present_values(self):
        assert has_active_campaign([{"id": 1}]) is True
        assert has_active_campaign({"title": "sale"}) is True
        assert has_active_campaign("ポイント2倍") is True
        assert has_active_campaign(1) is True
        assert has_active_campaign(({"id": 1},)) is True


class TestIsReleased:
    def test_released_and_future(self):
        assert is_released("2026-08-19", today=TODAY) is True
        assert is_released("2026-08-20", today=TODAY) is False
        assert is_released(None, today=TODAY) is False


class TestIsRecentRelease:
    def test_boundaries(self):
        assert is_recent_release("2026-08-19", today=TODAY, recent_days=60) is True
        assert is_recent_release("2026-06-20", today=TODAY, recent_days=60) is True
        assert is_recent_release("2026-06-19", today=TODAY, recent_days=60) is False
        assert is_recent_release("2026-08-20", today=TODAY, recent_days=60) is False

    def test_unknown_and_zero_days(self):
        assert is_recent_release(None, today=TODAY, recent_days=60) is False
        assert is_recent_release("bad", today=TODAY, recent_days=60) is False
        assert is_recent_release("2026-08-19", today=TODAY, recent_days=0) is True
        assert is_recent_release("2026-08-18", today=TODAY, recent_days=0) is False
        assert is_recent_release("2026-08-19", today=TODAY, recent_days=-3) is True
        assert is_recent_release("2026-08-20", today=TODAY, recent_days=0) is False


class TestApiSkip:
    def test_inactive_when_missing(self):
        assert is_api_skip_active(None, now=NOW) is False
        assert is_api_skip_active("", now=NOW) is False
        assert is_api_skip_active("bad", now=NOW) is False

    def test_active_when_future(self):
        assert is_api_skip_active("2026-08-19T08:00:01+00:00", now=NOW) is True
        assert is_api_skip_active("2026-08-19T08:00:00+00:00", now=NOW) is False
        assert is_api_skip_active("2026-08-18T00:00:00+00:00", now=NOW) is False
        assert is_api_skip_active("2026-08-20T00:00:00+00:00", now=NAIVE_NOW) is True


class TestShouldUpdateItem:
    def test_daily_recent_or_campaign(self):
        recent = {"release_date": "2026-08-01", "campaign": None}
        old_sale = {"release_date": "2025-01-01", "campaign": [{"id": 1}]}
        old = {"release_date": "2025-01-01", "campaign": None}
        undated = {"release_date": None, "campaign": None}
        future = {"release_date": "2026-09-01", "campaign": None}
        assert should_update_item(recent, mode="daily", today=TODAY) is True
        assert should_update_item(old_sale, mode="daily", today=TODAY) is True
        assert should_update_item(old, mode="daily", today=TODAY) is False
        assert should_update_item(undated, mode="daily", today=TODAY) is False
        assert should_update_item(future, mode="daily", today=TODAY) is False

    def test_weekly_is_complement_of_daily(self):
        old = {"release_date": "2025-01-01", "campaign": []}
        recent = {"release_date": "2026-08-01", "campaign": None}
        old_sale = {"release_date": "2025-01-01", "campaign": {"x": 1}}
        undated = {"release_date": "", "campaign": None}
        assert should_update_item(old, mode="weekly", today=TODAY) is True
        assert should_update_item(undated, mode="weekly", today=TODAY) is True
        assert should_update_item(recent, mode="weekly", today=TODAY) is False
        assert should_update_item(old_sale, mode="weekly", today=TODAY) is False

    def test_all_and_unknown_mode(self):
        old = {"release_date": "2020-01-01", "campaign": None}
        assert should_update_item(old, mode="all", today=TODAY) is True
        assert should_update_item(old, mode="DAILY", today=TODAY) is False
        assert should_update_item(old, mode="", today=TODAY) is False
        assert in_daily_window(old, today=TODAY) is False

    def test_skip_until_and_retry(self):
        skipped = {
            "content_id": "x",
            "release_date": "2026-08-01",
            "campaign": None,
            "skip_until": "2026-09-18T00:00:00+00:00",
        }
        assert should_update_item(skipped, mode="daily", today=TODAY, now=NOW) is False
        assert (
            should_update_item(
                skipped, mode="daily", today=TODAY, now=NOW, retry_skipped=True
            )
            is True
        )
        assert should_update_item(skipped, mode="all", today=TODAY, now=NOW) is False

    def test_content_id_overrides_mode_and_skip(self):
        skipped_old = {
            "content_id": "target",
            "release_date": "2020-01-01",
            "campaign": None,
            "skip_until": "2026-09-18T00:00:00+00:00",
        }
        other = {"content_id": "other", "release_date": "2026-08-01", "campaign": None}
        assert (
            should_update_item(
                skipped_old,
                mode="daily",
                today=TODAY,
                now=NOW,
                content_ids=["target"],
            )
            is True
        )
        assert (
            should_update_item(
                other, mode="daily", today=TODAY, content_ids=["target"]
            )
            is False
        )


class TestMergeAndFilter:
    def test_merge_api_state(self):
        items = [
            {"content_id": "a", "release_date": "2026-08-01"},
            {"content_id": "b", "release_date": "2020-01-01"},
            {"content_id": None},
        ]
        states = [
            {"content_id": "a", "miss_count": 2, "skip_until": "2026-09-01"},
            {"miss_count": 9},
        ]
        merged = merge_api_state(items, states)
        assert merged[0]["miss_count"] == 2
        assert merged[0]["skip_until"] == "2026-09-01"
        assert merged[1]["miss_count"] == 0
        assert merged[1]["skip_until"] is None
        assert merged[2]["miss_count"] == 0

    def test_preserves_order_and_defaults_today(self):
        rows = [
            {"content_id": "old", "release_date": "2020-01-01", "campaign": None},
            {"content_id": "new", "release_date": date.today().isoformat(), "campaign": None},
        ]
        daily = filter_items_for_update(rows, mode="daily")
        assert [r["content_id"] for r in daily] == ["new"]
        weekly = filter_items_for_update(rows, mode="weekly")
        assert [r["content_id"] for r in weekly] == ["old"]
        assert filter_items_for_update([], mode="daily") == []

    def test_custom_recent_days_and_skip_filter(self):
        rows = [
            {
                "content_id": "a",
                "release_date": "2026-07-01",
                "campaign": None,
                "skip_until": None,
            },
            {
                "content_id": "skipped",
                "release_date": "2026-08-01",
                "campaign": None,
                "skip_until": "2026-09-18T00:00:00+00:00",
            },
        ]
        assert filter_items_for_update(
            rows, mode="daily", today=TODAY, recent_days=10
        ) == []
        daily = filter_items_for_update(
            rows, mode="daily", today=TODAY, recent_days=60, now=NOW
        )
        assert [r["content_id"] for r in daily] == ["a"]
        retried = filter_items_for_update(
            rows,
            mode="daily",
            today=TODAY,
            recent_days=60,
            now=NOW,
            retry_skipped=True,
        )
        assert [r["content_id"] for r in retried] == ["a", "skipped"]


class TestNextApiState:
    def test_success_resets(self):
        payload = next_api_state_on_success(now=NOW)
        assert payload["miss_count"] == 0
        assert payload["skip_until"] is None
        assert payload["last_ok_at"].startswith("2026-08-19")
        naive = next_api_state_on_success(now=NAIVE_NOW)
        assert naive["miss_count"] == 0

    def test_miss_increments_and_trips_skip(self):
        first = next_api_state_on_miss({"miss_count": 0, "last_ok_at": "ok"}, now=NOW)
        assert first["miss_count"] == 1
        assert first["skip_until"] is None
        assert first["last_ok_at"] == "ok"
        second = next_api_state_on_miss(first, now=NOW)
        assert second["miss_count"] == 2
        assert second["skip_until"] is None
        third = next_api_state_on_miss(second, now=NAIVE_NOW)
        assert third["miss_count"] == 3
        assert third["skip_until"] is not None
        assert third["skip_until"].startswith("2026-09-18")

    def test_miss_handles_empty_and_invalid_count(self):
        from_none = next_api_state_on_miss(None, now=NOW)
        assert from_none["miss_count"] == 1
        bad = next_api_state_on_miss({"miss_count": "x"}, now=NOW)
        assert bad["miss_count"] == 1


class TestParseUpdateModeArgs:
    def test_defaults(self):
        args = parse_update_mode_args([])
        assert args.mode == "daily"
        assert args.recent_days == DEFAULT_RECENT_DAYS
        assert args.content_ids is None
        assert args.retry_skipped is False

    def test_weekly_days_content_id_and_retry(self):
        args = parse_update_mode_args(
            [
                "--mode",
                "weekly",
                "--recent-days",
                "31",
                "--content-id",
                "aaa",
                "--content-id",
                "bbb",
                "--retry-skipped",
            ]
        )
        assert args.mode == "weekly"
        assert args.recent_days == 31
        assert args.content_ids == ["aaa", "bbb"]
        assert args.retry_skipped is True

    def test_invalid_mode(self):
        with pytest.raises(SystemExit):
            parse_update_mode_args(["--mode", "monthly"])
