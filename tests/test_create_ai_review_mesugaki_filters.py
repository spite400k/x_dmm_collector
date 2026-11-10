"""create_ai_review_mesugaki の対象絞り込み（service/floor/unscored）。"""

from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mesugaki_review(monkeypatch):
    sys.modules["db.supabase_client_mesugaki"] = MagicMock(supabase=MagicMock())
    module_name = "scripts.process.create_ai_review_mesugaki"
    if module_name in sys.modules:
        del sys.modules[module_name]
    return importlib.import_module(module_name)


def test_resolve_targets_filters_service_and_floor(mesugaki_review):
    selected = mesugaki_review.resolve_targets(service="doujin", floor="digital_doujin")
    assert selected == [{"site": "FANZA", "service": "doujin", "floor": "digital_doujin"}]


def test_resolve_targets_raises_when_empty(mesugaki_review):
    with pytest.raises(ValueError, match="一致する対象がありません"):
        mesugaki_review.resolve_targets(service="digital", floor="videoa")


def test_latest_score_is_valid(mesugaki_review):
    assert mesugaki_review.latest_score_is_valid({"final_score": 48.8, "review_count": 1})
    assert not mesugaki_review.latest_score_is_valid(None)
    assert not mesugaki_review.latest_score_is_valid({"final_score": 0, "review_count": 1})
    assert not mesugaki_review.latest_score_is_valid({"final_score": 10, "review_count": 0})


def test_filter_unscored_items_keeps_missing_and_invalid(mesugaki_review, monkeypatch):
    items = [
        {"content_id": "a"},
        {"content_id": "b"},
        {"content_id": "c"},
    ]
    hist_rows = [
        {"content_id": "a", "final_score": 50, "review_count": 2, "snapshot_date": "2026-11-10"},
        {"content_id": "b", "final_score": 0, "review_count": 0, "snapshot_date": "2026-11-10"},
        {"content_id": "b", "final_score": 10, "review_count": 1, "snapshot_date": "2026-01-01"},
    ]

    class _Resp:
        data = hist_rows

    monkeypatch.setattr(
        mesugaki_review,
        "execute_with_retry",
        lambda fn: _Resp(),
    )
    filtered = mesugaki_review.filter_unscored_items(items)
    assert [row["content_id"] for row in filtered] == ["b", "c"]
