"""scripts.process.update_items の safe_generated_at スキップ判定。"""

from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock, patch

import pytest


def load_update_items_module():
    module_name = "scripts.process.update_items"
    if "openai" not in sys.modules:
        openai_mock = MagicMock()
        openai_mock.OpenAI = MagicMock()
        sys.modules["openai"] = openai_mock
    with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}, clear=False):
        if module_name in sys.modules:
            return importlib.reload(sys.modules[module_name])
        return importlib.import_module(module_name)


@pytest.fixture
def update_items():
    return load_update_items_module()


class TestGenerateSafeSummaryPoint:
    def test_empty_returns_not_ok(self, update_items):
        client = MagicMock()
        update_items.client = client
        assert update_items.generate_safe_summary_point("作品", "", "") == ("", "", False)
        client.chat.completions.create.assert_not_called()

    def test_success_sets_ai_ok(self, update_items):
        client = MagicMock()
        update_items.client = client
        msg = MagicMock()
        msg.content = "【あらすじ・概要】\nソフト文\n【おすすめポイント】\n・見どころ"
        client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=msg)]
        )

        out_s, out_p, ok = update_items.generate_safe_summary_point(
            "作品", "過激なセックス", "ポイント"
        )

        assert ok is True
        assert out_s == "ソフト文"
        assert "見どころ" in out_p
        client.chat.completions.create.assert_called_once()

    def test_failure_returns_not_ok(self, update_items):
        client = MagicMock()
        update_items.client = client
        client.chat.completions.create.side_effect = RuntimeError("api down")
        assert update_items.generate_safe_summary_point("作品", "セックス", "") == (
            "",
            "",
            False,
        )


class TestUpdateDmmItemSafeFlag:
    def _base_item(self):
        return {
            "title": "テスト作品",
            "review": {"count": 1, "average": 4.0},
            "prices": {"price": "1000円", "list_price": "2000円", "deliveries": {"delivery": []}},
            "iteminfo": {},
            "sampleImageURL": {},
        }

    def test_skips_ai_when_safe_generated_at_set(self, update_items):
        client = MagicMock()
        update_items.client = client
        update_items.upsert_actresses = MagicMock()
        table = MagicMock()
        update_items.supabase = MagicMock()
        update_items.supabase.table.return_value = table
        table.update.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"content_id": "x"}]
        )

        update_items.update_dmm_item(
            "x",
            self._base_item(),
            "既存あらすじ",
            "既存ポイント",
            safe_generated_at="2026-08-01T00:00:00+00:00",
        )

        client.chat.completions.create.assert_not_called()
        payload = table.update.call_args[0][0]
        assert "auto_summary" not in payload
        assert "safe_generated_at" not in payload
        assert "price" in payload

    def test_sets_safe_generated_at_on_ai_success(self, update_items):
        client = MagicMock()
        update_items.client = client
        msg = MagicMock()
        msg.content = "【あらすじ・概要】\n新あらすじ\n【おすすめポイント】\n・新ポイント"
        client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=msg)]
        )
        update_items.upsert_actresses = MagicMock()
        table = MagicMock()
        update_items.supabase = MagicMock()
        update_items.supabase.table.return_value = table
        table.update.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"content_id": "y"}]
        )

        update_items.update_dmm_item(
            "y",
            self._base_item(),
            "セックス描写あり",
            "ポイント",
            safe_generated_at=None,
        )

        payload = table.update.call_args[0][0]
        assert payload["auto_summary"] == "新あらすじ"
        assert payload["auto_point"] == "・新ポイント"
        assert payload["safe_generated_at"]

    def test_keeps_summary_on_ai_failure(self, update_items):
        client = MagicMock()
        update_items.client = client
        client.chat.completions.create.side_effect = RuntimeError("fail")
        update_items.upsert_actresses = MagicMock()
        table = MagicMock()
        update_items.supabase = MagicMock()
        update_items.supabase.table.return_value = table
        table.update.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"content_id": "z"}]
        )

        update_items.update_dmm_item(
            "z",
            self._base_item(),
            "元のあらすじ",
            "元のポイント",
            safe_generated_at=None,
        )

        payload = table.update.call_args[0][0]
        assert "auto_summary" not in payload
        assert "safe_generated_at" not in payload


class TestProcessBatchProgress:
    def test_logs_global_index_across_batches(self, update_items, caplog):
        update_items.fetch_item_by_content_id = MagicMock(return_value=None)
        batch_items = [{"content_id": "a"}, {"content_id": "b"}]
        with patch.object(update_items.time, "sleep"), caplog.at_level("INFO"):
            update_items.process_batch(batch_items, batch_index=2, total=3466, range_start=100)

        messages = [r.message for r in caplog.records]
        assert any("[101/3466] a 処理中..." in m for m in messages)
        assert any("[102/3466] b 処理中..." in m for m in messages)
        assert not any("[1/3466]" in m for m in messages)
        assert not any("[2/3466]" in m for m in messages)

    def test_passes_service_floor_to_fetch(self, update_items):
        update_items.fetch_item_by_content_id = MagicMock(return_value=None)
        batch_items = [
            {"content_id": "13dsvr01798", "service": "digital", "floor": "videoa"}
        ]
        with patch.object(update_items.time, "sleep"):
            update_items.process_batch(batch_items, batch_index=1, total=1, range_start=0)

        update_items.fetch_item_by_content_id.assert_called_once_with(
            "13dsvr01798", service="digital", floor="videoa"
        )


class TestFetchItemByContentId:
    def test_uses_service_floor_first(self, update_items):
        found = MagicMock()
        found.raise_for_status = MagicMock()
        found.json.return_value = {"result": {"items": [{"content_id": "13dsvr01798"}]}}

        with patch.object(update_items.requests, "get", return_value=found) as get_mock:
            item = update_items.fetch_item_by_content_id(
                "13dsvr01798", service="digital", floor="videoa"
            )

        assert item == {"content_id": "13dsvr01798"}
        assert get_mock.call_count == 1
        assert get_mock.call_args.kwargs["params"]["service"] == "digital"
        assert get_mock.call_args.kwargs["params"]["floor"] == "videoa"

    def test_falls_back_to_cid_only_when_service_floor_empty(self, update_items):
        empty = MagicMock()
        empty.raise_for_status = MagicMock()
        empty.json.return_value = {"result": {"items": []}}
        found = MagicMock()
        found.raise_for_status = MagicMock()
        found.json.return_value = {"result": {"items": [{"content_id": "x"}]}}

        with patch.object(
            update_items.requests, "get", side_effect=[empty, found]
        ) as get_mock:
            item = update_items.fetch_item_by_content_id(
                "x", service="digital", floor="videoa"
            )

        assert item == {"content_id": "x"}
        assert get_mock.call_count == 2
        assert "service" not in get_mock.call_args_list[1].kwargs["params"]

    def test_returns_none_and_logs_on_http_error(self, update_items, caplog):
        with patch.object(
            update_items.requests,
            "get",
            side_effect=RuntimeError("timeout"),
        ), caplog.at_level("ERROR"):
            assert update_items.fetch_item_by_content_id("bad") is None
        assert any("DMM API呼び出し失敗" in r.message for r in caplog.records)
