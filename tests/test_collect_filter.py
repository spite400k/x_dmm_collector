"""scripts.collect._filter の未登録抽出ロジックを検証する。"""

from unittest.mock import MagicMock

from scripts.collect._filter import filter_unregistered_items, supabase_exists_checker


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
