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
