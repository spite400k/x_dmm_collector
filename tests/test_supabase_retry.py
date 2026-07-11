from unittest.mock import MagicMock, patch

import httpx
import pytest

from utils.supabase_retry import execute_with_retry


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
