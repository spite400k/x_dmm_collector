"""scripts.collect._filter の未登録抽出・アイテム隔離ロジックを検証する。"""

from unittest.mock import MagicMock, patch

import httpx

from scripts.collect._filter import (
    filter_unregistered_items,
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
