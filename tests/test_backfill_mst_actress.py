"""backfill_mst_actress の対象抽出ロジックを検証する。"""

from unittest.mock import MagicMock

from scripts.manual.backfill_mst_actress import fetch_missing_actresses


def test_fetch_missing_actresses_without_limit():
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    cur.fetchall.return_value = [{"actress_id": 1, "name": "A", "ruby": "あ"}]

    rows = fetch_missing_actresses(conn, limit=None)

    assert rows == [{"actress_id": 1, "name": "A", "ruby": "あ"}]
    sql = cur.execute.call_args.args[0]
    assert "LEFT JOIN mst_actress" in sql
    assert "LIMIT" not in sql
    assert cur.execute.call_args.args[1] == ()


def test_fetch_missing_actresses_with_limit():
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    cur.fetchall.return_value = [{"actress_id": 9, "name": None, "ruby": None}]

    rows = fetch_missing_actresses(conn, limit=5)

    assert rows == [{"actress_id": 9, "name": None, "ruby": None}]
    sql = cur.execute.call_args.args[0]
    assert "LIMIT %s" in sql
    assert cur.execute.call_args.args[1] == (5,)
