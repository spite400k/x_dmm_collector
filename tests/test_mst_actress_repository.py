from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from db import mst_actress_repository as repo


class FakeResponse:
    def __init__(self, data):
        self.data = data


@pytest.fixture
def mock_client():
    client = MagicMock()
    table = MagicMock()
    client.table.return_value = table
    return client, table


def test_fetch_actresses_to_enrich_returns_data(mock_client):
    client, table = mock_client
    table.select.return_value.order.return_value.limit.return_value.execute.return_value = (
        FakeResponse([{"actress_id": 1, "name": "テスト"}])
    )

    result = repo.fetch_actresses_to_enrich(limit=5, supabase_client=client)

    assert result == [{"actress_id": 1, "name": "テスト"}]
    client.table.assert_called_with("mst_actress")


def test_fetch_actresses_to_enrich_empty(mock_client):
    client, table = mock_client
    table.select.return_value.order.return_value.limit.return_value.execute.return_value = (
        FakeResponse(None)
    )

    assert repo.fetch_actresses_to_enrich(limit=5, supabase_client=client) == []


def test_update_actress_success(mock_client):
    client, table = mock_client
    select_chain = table.select.return_value.eq.return_value
    select_chain.execute.return_value = FakeResponse([{"id": 10}])
    update_chain = table.update.return_value.eq.return_value
    update_chain.execute.return_value = FakeResponse([])

    ok = repo.update_actress(
        123,
        {"name": "名前", "bust": 90, "cup": "", "hobby": None},
        supabase_client=client,
    )

    assert ok is True
    update_data = table.update.call_args[0][0]
    assert update_data["name"] == "名前"
    assert update_data["bust"] == 90
    assert "cup" not in update_data
    assert "hobby" not in update_data
    assert "updated_at" in update_data


def test_update_actress_not_found(mock_client):
    client, table = mock_client
    table.select.return_value.eq.return_value.execute.return_value = FakeResponse([])

    assert repo.update_actress(999, {"name": "x"}, supabase_client=client) is False


def test_update_actress_exception(mock_client):
    client, table = mock_client
    table.select.return_value.eq.return_value.execute.side_effect = RuntimeError("db down")

    assert repo.update_actress(1, {"name": "x"}, supabase_client=client) is False


def test_enrich_and_update_actress_uses_default_client(mock_client):
    client, table = mock_client
    with patch.object(repo, "update_actress", return_value=True) as update_mock:
        assert repo.enrich_and_update_actress(1, {"name": "a"}) is True
        update_mock.assert_called_once_with(1, {"name": "a"}, supabase_client=repo.supabase)


def test_enrich_and_update_actress_custom_client(mock_client):
    client, _ = mock_client
    with patch.object(repo, "update_actress", return_value=False) as update_mock:
        assert repo.enrich_and_update_actress(2, {"name": "b"}, supabase_client=client) is False
        update_mock.assert_called_once_with(2, {"name": "b"}, supabase_client=client)


def test_touch_actress_updated_at_success(mock_client):
    client, table = mock_client
    table.select.return_value.eq.return_value.execute.return_value = FakeResponse([{"id": 7}])
    table.update.return_value.eq.return_value.execute.return_value = FakeResponse([])

    assert repo.touch_actress_updated_at(55, supabase_client=client) is True
    table.update.assert_called_once()


def test_touch_actress_updated_at_not_found(mock_client):
    client, table = mock_client
    table.select.return_value.eq.return_value.execute.return_value = FakeResponse([])

    assert repo.touch_actress_updated_at(55, supabase_client=client) is False


def test_touch_actress_updated_at_exception(mock_client):
    client, table = mock_client
    table.select.return_value.eq.return_value.execute.side_effect = RuntimeError("fail")

    assert repo.touch_actress_updated_at(55, supabase_client=client) is False
