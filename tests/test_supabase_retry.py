from unittest.mock import MagicMock, patch

import httpx
import pytest
import requests

from utils.supabase_retry import call_with_retry, execute_with_retry


def test_execute_with_retry_success():
    builder = MagicMock()
    builder.execute.return_value = {"ok": True}

    result = execute_with_retry(lambda: builder)

    assert result == {"ok": True}
    builder.execute.assert_called_once()


def test_execute_with_retry_recovers_after_connect_error():
    builder = MagicMock()
    builder.execute.side_effect = [
        httpx.ConnectError("dns"),
        {"ok": True},
    ]

    with patch("utils.supabase_retry.time.sleep"):
        result = execute_with_retry(lambda: builder, retries=2, base_delay=0.01)

    assert result == {"ok": True}
    assert builder.execute.call_count == 2


def test_execute_with_retry_raises_after_exhausted_retries():
    builder = MagicMock()
    builder.execute.side_effect = httpx.ConnectError("dns")

    with patch("utils.supabase_retry.time.sleep"):
        with pytest.raises(httpx.ConnectError):
            execute_with_retry(lambda: builder, retries=2, base_delay=0.01)

    assert builder.execute.call_count == 2


def test_execute_with_retry_recovers_after_remote_protocol_error():
    builder = MagicMock()
    builder.execute.side_effect = [
        httpx.RemoteProtocolError("Server disconnected without sending a response."),
        {"ok": True},
    ]

    with patch("utils.supabase_retry.time.sleep"):
        result = execute_with_retry(lambda: builder, retries=3, base_delay=0.01)

    assert result == {"ok": True}
    assert builder.execute.call_count == 2


def test_call_with_retry_recovers_oserror():
    fn = MagicMock(side_effect=[OSError(10053, "aborted"), "ok"])
    with patch("utils.supabase_retry.time.sleep"):
        assert call_with_retry(fn, retries=3, base_delay=0.01, log_label="S3 アップロード") == "ok"
    assert fn.call_count == 2


def test_call_with_retry_recovers_s3_connection_closed():
    from botocore.exceptions import ConnectionClosedError

    fn = MagicMock(side_effect=[ConnectionClosedError(endpoint_url="https://s3"), "ok"])
    with patch("utils.supabase_retry.time.sleep"):
        assert call_with_retry(fn, retries=2, base_delay=0.01) == "ok"


def test_call_with_retry_recovers_requests_timeout():
    fn = MagicMock(side_effect=[requests.Timeout("read"), "ok"])
    with patch("utils.supabase_retry.time.sleep"):
        assert call_with_retry(fn, retries=2, base_delay=0.01) == "ok"
    assert fn.call_count == 2


def test_call_with_retry_unreachable_when_retries_zero():
    with pytest.raises(RuntimeError, match="unreachable"):
        call_with_retry(MagicMock(), retries=0)
