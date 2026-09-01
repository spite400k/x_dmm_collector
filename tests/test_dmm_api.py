"""dmm_api の API リトライ・フィルタリングのテスト。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from dmm import dmm_api as api


class FakeResponse:
    def __init__(self, *, json_data=None, status_code=200, raise_http=False):
        self._json = json_data or {}
        self.status_code = status_code
        self._raise_http = raise_http

    def raise_for_status(self):
        if self._raise_http or self.status_code >= 400:
            response = MagicMock()
            response.status_code = self.status_code
            raise requests.HTTPError(response=response)

    def json(self):
        return self._json


def _ok_payload(items=None):
    return {
        "result": {
            "status": 200,
            "items": items or [],
        }
    }


def test_get_highest_resolution_movie():
    assert api.get_highest_resolution_movie(None) is None
    assert api.get_highest_resolution_movie("bad") is None
    assert api.get_highest_resolution_movie({"size_bad": "x"}) is None
    movie = {
        "size_100_200": "https://a",
        "size_300_400": "https://b",
        "other": "skip",
    }
    assert api.get_highest_resolution_movie(movie) == "https://b"


def test_get_highest_resolution_movie_skips_malformed_size_key():
    movie = {"size_abc": "https://a", "size_100_200": "https://b"}
    assert api.get_highest_resolution_movie(movie) == "https://b"


def test_get_highest_resolution_movie_keeps_larger_area():
    movie = {"size_300_400": "https://big", "size_100_200": "https://small"}
    assert api.get_highest_resolution_movie(movie) == "https://big"


def test_request_item_list_retries_on_connection_error():
    responses = [
        requests.ConnectionError("reset"),
        FakeResponse(json_data=_ok_payload()),
    ]
    with patch.object(api.requests, "get", side_effect=responses) as get_mock:
        with patch("utils.supabase_retry.time.sleep"):
            result = api._request_item_list({"api_id": "x"})
    assert result["result"]["status"] == 200
    assert get_mock.call_count == 2


def test_request_item_list_retries_on_5xx():
    bad = FakeResponse(status_code=503)
    good = FakeResponse(json_data=_ok_payload())
    with patch.object(api.requests, "get", side_effect=[bad, good]):
        with patch("utils.supabase_retry.time.sleep"):
            result = api._request_item_list({"api_id": "x"})
    assert result["result"]["status"] == 200


def test_request_item_list_raises_on_api_status_error():
    payload = {"result": {"status": 400, "message": "bad params"}}
    with patch.object(api.requests, "get", return_value=FakeResponse(json_data=payload)):
        with pytest.raises(RuntimeError, match="API error"):
            api._request_item_list({"api_id": "x"})


def test_fetch_items_skips_existing_and_enriches():
    item = {
        "content_id": "cid1",
        "sampleImageURL": {"sample_l": {"image": ["https://img"]}},
        "sampleMovieURL": {"size_100_200": "https://mv"},
        "campaign": {"x": 1},
    }
    client = MagicMock()
    client.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": 1}]
    )
    with patch.object(api, "_request_item_list", return_value=_ok_payload([item])):
        assert api.fetch_items("s", "sv", "f", supabase_client=client) == []

    client.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[]
    )
    with patch.object(api, "_request_item_list", return_value=_ok_payload([item])):
        result = api.fetch_items("s", "sv", "f", supabase_client=client)
    assert len(result) == 1
    assert result[0]["sampleMovieURL_highest"] == "https://mv"
    assert result[0]["campaign_data"] == {"x": 1}


def test_fetch_items_skips_on_supabase_error():
    item = {
        "content_id": "cid2",
        "sampleImageURL": {"sample_l": {"image": ["https://img"] * 10}},
    }
    client = MagicMock()
    client.table.return_value.select.return_value.eq.return_value.execute.side_effect = RuntimeError(
        "db down"
    )
    with patch.object(api, "_request_item_list", return_value=_ok_payload([item])):
        assert api.fetch_items("s", "sv", "f", supabase_client=client) == []


def test_fetch_items_skips_non_list_sample_images():
    items = [
        {"content_id": "cid3", "sampleImageURL": {"sample_l": {"image": "not-a-list"}}},
        {
            "content_id": "cid4",
            "sampleImageURL": {"sample_l": {"image": ["https://img"] * 10}},
        },
    ]
    client = MagicMock()
    client.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[]
    )
    with patch.object(api, "_request_item_list", return_value=_ok_payload(items)):
        result = api.fetch_items("s", "sv", "f", supabase_client=client)
    assert len(result) == 1
    assert result[0]["content_id"] == "cid4"


def test_fetch_items_skips_missing_content_id():
    items = [{"sampleImageURL": {"sample_l": {"image": []}}}]
    client = MagicMock()
    with patch.object(api, "_request_item_list", return_value=_ok_payload(items)):
        assert api.fetch_items("s", "sv", None, keyword="kw", supabase_client=client) == []


def test_fetch_items_merged_sorts_dedupes():
    a = {
        "content_id": "same",
        "sampleImageURL": {"sample_l": {"image": ["https://img"]}},
    }
    b = {
        "content_id": "other",
        "sampleImageURL": {"sample_l": {"image": ["https://img2"]}},
    }
    client = MagicMock()
    client.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[]
    )
    with patch.object(
        api,
        "fetch_items",
        side_effect=[
            [a],
            [a, b],
            [],
        ],
    ):
        merged = api.fetch_items_merged_sorts("s", "sv", "f", supabase_client=client)
    assert [x["content_id"] for x in merged] == ["same", "other"]


def test_fetch_items_search_keyword_logs_and_returns_items():
    items = [{"content_id": "x"}]
    with patch.object(api, "_request_item_list", return_value=_ok_payload(items)):
        result = api.fetch_items_search_keyword("s", "sv", "f", "kw", hits=5)
    assert result == items
