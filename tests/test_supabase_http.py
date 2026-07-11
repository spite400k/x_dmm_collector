import httpx

from db.supabase_http import (
    SUPABASE_CONNECT_TIMEOUT,
    SUPABASE_HTTP_RETRIES,
    create_supabase_httpx_client,
)


def test_create_supabase_httpx_client_configured():
    client = create_supabase_httpx_client()
    try:
        assert isinstance(client, httpx.Client)
        assert client.timeout.connect == SUPABASE_CONNECT_TIMEOUT
        assert SUPABASE_HTTP_RETRIES >= 1
    finally:
        client.close()
