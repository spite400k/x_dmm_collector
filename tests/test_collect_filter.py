"""scripts.collect._filter の未登録抽出・アイテム隔離ロジックを検証する。"""

from unittest.mock import MagicMock, patch

from datetime import date

import httpx
import pytest

from scripts.collect._filter import (
    filter_released_items,
    filter_unregistered_items,
    register_collected_item,
    run_items_isolated,
    supabase_exists_checker,
)


def test_filter_skips_missing_content_id_and_existing():
    top = [
        {"title": "no-id", "URL": "u0"},
        {"content_id": "a", "title": "存在", "URL": "u1"},
        {"content_id": "b", "title": "新規", "URL": "u2"},
        {"content_id": "c", "title": "新規2", "URL": "u3"},
    ]

    def exists(cid: str) -> bool:
        return cid == "a"

    items = filter_unregistered_items(top, exists_by_content_id=exists)
    assert [i["content_id"] for i in items] == ["b", "c"]


def test_filter_empty_input():
    assert filter_unregistered_items([], exists_by_content_id=lambda _: False) == []


def test_filter_released_items_skips_future():
    today = date(2026, 8, 19)
    items = [
        {"content_id": "past", "date": "2026-08-01"},
        {"content_id": "today", "release_date": "2026-08-19 00:00:00"},
        {"content_id": "future", "date": "2026-09-01"},
        {"content_id": "bad", "date": "invalid"},
    ]
    released = filter_released_items(items, today=today)
    assert [item["content_id"] for item in released] == ["past", "today"]


def test_supabase_exists_checker():
    table = MagicMock()
    table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": 1}])
    assert supabase_exists_checker(table)("x") is True

    table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
    assert supabase_exists_checker(table)("y") is False


def test_supabase_exists_checker_retries_remote_protocol_error():
    table = MagicMock()
    table.select.return_value.eq.return_value.execute.side_effect = [
        httpx.RemoteProtocolError("disconnect"),
        MagicMock(data=[{"id": 1}]),
    ]
    with patch("utils.supabase_retry.time.sleep"):
        assert supabase_exists_checker(table)("x") is True
    assert table.select.return_value.eq.return_value.execute.call_count == 2


def test_run_items_isolated_continues_after_failure():
    processed: list[str] = []

    def process_one(item: dict) -> None:
        cid = item["content_id"]
        if cid == "bad":
            raise RuntimeError("boom")
        processed.append(cid)

    has_error = run_items_isolated(
        [
            {"content_id": "ok1"},
            {"content_id": "bad"},
            {"content_id": "ok2"},
        ],
        process_one,
    )

    assert has_error is True
    assert processed == ["ok1", "ok2"]


def test_run_items_isolated_all_success():
    processed: list[str] = []
    has_error = run_items_isolated(
        [{"content_id": "a"}, {"content_id": "b"}],
        lambda item: processed.append(item["content_id"]),
    )
    assert has_error is False
    assert processed == ["a", "b"]


def test_run_items_isolated_empty():
    assert run_items_isolated([], lambda _: None) is False


def test_register_collected_item_raises_when_insert_fails():
    session = MagicMock()
    session.capture.return_value = ["a.webp"]
    cleaned: list[str] = []
    item = {
        "content_id": "x",
        "tachiyomi": {"URL": "https://example.com/t"},
        "sampleMovieURL_highest": None,
    }

    with pytest.raises(RuntimeError, match="insert_dmm_item 失敗"):
        register_collected_item(
            item,
            site="FANZA",
            service="ebook",
            floor="comic",
            insert_fn=lambda *a, **k: False,
            tachiyomi_session=session,
            cleanup_file=cleaned.append,
        )

    assert cleaned == ["a.webp"]
    session.capture.assert_called_once_with("https://example.com/t")


def test_register_collected_item_success_without_tachiyomi():
    session = MagicMock()
    calls: list[str] = []
    item = {"content_id": "x", "tachiyomi": {}}

    register_collected_item(
        item,
        site="FANZA",
        service="ebook",
        floor="comic",
        insert_fn=lambda *a, **k: True,
        tachiyomi_session=session,
        cleanup_file=lambda p: calls.append(p),
    )

    session.capture.assert_not_called()
    assert calls == []
