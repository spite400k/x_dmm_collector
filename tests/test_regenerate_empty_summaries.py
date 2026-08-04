"""scripts.manual.regenerate_empty_summaries のペイロード組み立てテスト。"""

from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock, patch

import pytest


def load_module():
    module_name = "scripts.manual.regenerate_empty_summaries"
    if "openai" not in sys.modules:
        openai_mock = MagicMock()
        openai_mock.OpenAI = MagicMock()
        sys.modules["openai"] = openai_mock
    with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}, clear=False):
        if module_name in sys.modules:
            return importlib.reload(sys.modules[module_name])
        return importlib.import_module(module_name)


@pytest.fixture
def mod():
    return load_module()


class TestBuildUpdatePayload:
    def test_fills_empty_summary_point_and_sets_safe_flag(self, mod):
        row = {
            "auto_comment": "既存コメント",
            "auto_summary": "",
            "auto_point": "",
        }
        ai = {
            "auto_comment": "新コメント",
            "auto_summary": "生あらすじ",
            "auto_point": "生ポイント",
        }
        payload = mod.build_update_payload(
            row,
            ai,
            safe_summary="Safeあらすじ",
            safe_point="Safeポイント",
            safe_ok=True,
        )
        assert payload is not None
        assert payload["auto_summary"] == "Safeあらすじ"
        assert payload["auto_point"] == "Safeポイント"
        assert "auto_comment" not in payload  # 既存コメントは保持
        assert payload["safe_generated_at"]

    def test_uses_raw_ai_when_safe_fails(self, mod):
        row = {"auto_comment": "c", "auto_summary": "", "auto_point": ""}
        ai = {"auto_summary": "生あらすじ", "auto_point": "生ポイント"}
        payload = mod.build_update_payload(
            row, ai, safe_summary="", safe_point="", safe_ok=False
        )
        assert payload["auto_summary"] == "生あらすじ"
        assert payload["auto_point"] == "生ポイント"
        assert "safe_generated_at" not in payload

    def test_fills_comment_only_when_blank(self, mod):
        row = {"auto_comment": "", "auto_summary": "", "auto_point": ""}
        ai = {
            "auto_comment": "一言",
            "auto_summary": "あらすじ",
            "auto_point": "ポイント",
        }
        payload = mod.build_update_payload(
            row, ai, safe_summary="S", safe_point="P", safe_ok=True
        )
        assert payload["auto_comment"] == "一言"

    def test_returns_none_when_nothing_to_fill(self, mod):
        row = {"auto_comment": "c", "auto_summary": "", "auto_point": ""}
        ai = {"auto_summary": "", "auto_point": "", "auto_comment": ""}
        assert (
            mod.build_update_payload(
                row, ai, safe_summary="", safe_point="", safe_ok=False
            )
            is None
        )


class TestIsBlank:
    def test_blank(self, mod):
        assert mod.is_blank(None) is True
        assert mod.is_blank("") is True
        assert mod.is_blank("  ") is True
        assert mod.is_blank("x") is False
