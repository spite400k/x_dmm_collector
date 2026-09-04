"""scripts.process.update_mesugaki のモード分岐・API状態記録。"""

from __future__ import annotations

import importlib
import sys
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest


def load_update_mesugaki_module():
    module_name = "scripts.process.update_mesugaki"
    sys.modules["db.supabase_client_mesugaki"] = MagicMock(supabase=MagicMock())
    if "openai" not in sys.modules:
        openai_mock = MagicMock()
        openai_mock.OpenAI = MagicMock()
        sys.modules["openai"] = openai_mock
    env = {
        "OPENAI_API_KEY": "test-key",
        "MESUGAKI_SUPABASE_KEY": "test-key",
        "DMM_API_ID": "id",
        "DMM_AFFILIATE_ID": "aff",
    }
    with patch.dict("os.environ", env, clear=False):
        if module_name in sys.modules:
            return importlib.reload(sys.modules[module_name])
        return importlib.import_module(module_name)


@pytest.fixture
def update_mesugaki():
    return load_update_mesugaki_module()


class TestUpdateDmmItemProfile:
    def test_reviews_profile_updates_only_review_fields(self, update_mesugaki):
        update_mesugaki.upsert_actresses = MagicMock()
        table = MagicMock()
        update_mesugaki.supabase = MagicMock()
        update_mesugaki.supabase.table.return_value = table
        table.update.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"content_id": "m"}]
        )
        item = {
            "title": "t",
            "review": {"count": 3, "average": 4.5},
            "prices": {"price": "1000円"},
            "iteminfo": {"campaign": [{"id": 1}]},
        }
        update_mesugaki.update_dmm_item(
            "m",
            item,
            None,
            None,
            profile=update_mesugaki.UPDATE_PROFILE_REVIEWS,
        )
        update_mesugaki.upsert_actresses.assert_not_called()
        payload = table.update.call_args[0][0]
        assert set(payload.keys()) == {
            "review_count",
            "review_average",
            "updated_at",
        }

    def test_main_passes_reviews_profile_for_daily(self, update_mesugaki):
        update_mesugaki.fetch_paginated_rows = MagicMock(
            side_effect=[
                [{"content_id": "new", "release_date": "2026-08-01"}],
                [],
            ]
        )
        update_mesugaki.process_batch = MagicMock()
        today = date(2026, 8, 19)
        now = datetime(2026, 8, 19, 8, 0, tzinfo=timezone.utc)
        with patch.object(update_mesugaki.time, "sleep"):
            update_mesugaki.main([], today=today, now=now)
        assert (
            update_mesugaki.process_batch.call_args.kwargs["profile"]
            == update_mesugaki.UPDATE_PROFILE_REVIEWS
        )


class TestParseArgs:
    def test_defaults(self, update_mesugaki):
        args = update_mesugaki.parse_args([])
        assert args.mode == "daily"
        assert args.retry_skipped is False


class TestFetchAndRecord:
    def test_fetch_paginated_rows(self, update_mesugaki):
        page1 = MagicMock(data=[{"content_id": "a"}])
        page2 = MagicMock(data=None)
        table = MagicMock()
        table.select.return_value.order.return_value.range.return_value.execute.side_effect = [
            page1,
            page2,
        ]
        update_mesugaki.supabase = MagicMock()
        update_mesugaki.supabase.table.return_value = table
        assert update_mesugaki.fetch_paginated_rows("t", "c") == [{"content_id": "a"}]

    def test_record_ok_and_error(self, update_mesugaki, caplog):
        table = MagicMock()
        update_mesugaki.supabase = MagicMock()
        update_mesugaki.supabase.table.return_value = table
        table.upsert.return_value.execute.return_value = MagicMock()
        now = datetime(2026, 8, 19, 8, 0, tzinfo=timezone.utc)
        update_mesugaki.record_api_result("c1", ok=True, now=now)
        assert table.upsert.call_args[0][0]["miss_count"] == 0

        table.upsert.return_value.execute.side_effect = RuntimeError("db")
        with caplog.at_level("ERROR"):
            update_mesugaki.record_api_result("c2", ok=False, current_state={"miss_count": 0})
        assert any("API状態の保存失敗" in r.message for r in caplog.records)


class TestProcessBatch:
    def test_skips_row_without_content_id(self, update_mesugaki, caplog):
        update_mesugaki.fetch_item_by_content_id = MagicMock()
        with patch.object(update_mesugaki.time, "sleep"), caplog.at_level("WARNING"):
            update_mesugaki.process_batch(
                [{}], batch_index=1, total_batches=1, range_start=0, total=1
            )
        update_mesugaki.fetch_item_by_content_id.assert_not_called()
        assert any("content_id が無い" in r.message for r in caplog.records)

    def test_records_ok_and_miss(self, update_mesugaki):
        update_mesugaki.fetch_item_by_content_id = MagicMock(
            side_effect=[{"title": "x"}, None]
        )
        update_mesugaki.update_dmm_item = MagicMock()
        update_mesugaki.record_api_result = MagicMock()
        rows = [{"content_id": "ok"}, {"content_id": "miss"}]
        with patch.object(update_mesugaki.time, "sleep"):
            update_mesugaki.process_batch(
                rows, batch_index=1, total_batches=1, range_start=0, total=2
            )
        assert update_mesugaki.record_api_result.call_args_list[0].kwargs["ok"] is True
        assert update_mesugaki.record_api_result.call_args_list[1].kwargs["ok"] is False


class TestMain:
    def test_exits_when_env_missing(self, update_mesugaki):
        update_mesugaki.DMM_API_ID = None
        with pytest.raises(SystemExit) as exc:
            update_mesugaki.main([])
        assert exc.value.code == 1

    def test_filters_daily(self, update_mesugaki):
        update_mesugaki.fetch_paginated_rows = MagicMock(
            side_effect=[
                [
                    {"content_id": "old", "release_date": "2020-01-01", "campaign": None},
                    {"content_id": "new", "release_date": "2026-08-01", "campaign": None},
                ],
                [],
            ]
        )
        update_mesugaki.process_batch = MagicMock()
        today = date(2026, 8, 19)
        now = datetime(2026, 8, 19, 8, 0, tzinfo=timezone.utc)
        with patch.object(update_mesugaki.time, "sleep"):
            update_mesugaki.main([], today=today, now=now)
        processed = update_mesugaki.process_batch.call_args[0][0]
        assert [r["content_id"] for r in processed] == ["new"]

    def test_continues_if_api_state_missing(self, update_mesugaki, caplog):
        def fetch(table, columns):
            if table == update_mesugaki.API_STATE_TABLE:
                raise RuntimeError("relation does not exist")
            return [
                {"content_id": "new", "release_date": "2026-08-01", "campaign": None}
            ]

        update_mesugaki.fetch_paginated_rows = MagicMock(side_effect=fetch)
        update_mesugaki.process_batch = MagicMock()
        today = date(2026, 8, 19)
        now = datetime(2026, 8, 19, 8, 0, tzinfo=timezone.utc)
        with patch.object(update_mesugaki.time, "sleep"), caplog.at_level("WARNING"):
            update_mesugaki.main([], today=today, now=now)
        update_mesugaki.process_batch.assert_called_once()
        assert any("API状態を取得できませんでした" in r.message for r in caplog.records)

    def test_exits_when_no_targets(self, update_mesugaki):
        update_mesugaki.fetch_paginated_rows = MagicMock(side_effect=[[], []])
        update_mesugaki.process_batch = MagicMock()
        today = date(2026, 8, 19)
        now = datetime(2026, 8, 19, 8, 0, tzinfo=timezone.utc)
        with pytest.raises(SystemExit) as exc:
            update_mesugaki.main(["--mode", "all"], today=today, now=now)
        assert exc.value.code == 0
        update_mesugaki.process_batch.assert_not_called()

    def test_content_id_and_batch_sleep(self, update_mesugaki, caplog):
        update_mesugaki.BATCH_SIZE = 1
        update_mesugaki.fetch_paginated_rows = MagicMock(
            side_effect=[
                [
                    {"content_id": "a", "release_date": "2020-01-01", "campaign": None},
                    {"content_id": "b", "release_date": "2020-01-01", "campaign": None},
                ],
                [],
            ]
        )
        update_mesugaki.process_batch = MagicMock()
        today = date(2026, 8, 19)
        now = datetime(2026, 8, 19, 8, 0, tzinfo=timezone.utc)
        with patch.object(update_mesugaki.time, "sleep") as sleep_mock, caplog.at_level("INFO"):
            update_mesugaki.main(
                ["--content-id", "a", "--content-id", "b"],
                today=today,
                now=now,
            )
        assert update_mesugaki.process_batch.call_count == 2
        sleep_mock.assert_called()
        assert any("content_id 指定" in r.message for r in caplog.records)
