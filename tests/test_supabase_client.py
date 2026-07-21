import importlib
import sys
from unittest.mock import MagicMock, patch

import pytest


def _reload_supabase_client(env: dict):
    """dotenv を無効化し、指定 env で db.supabase_client を再ロードする。"""
    mod_name = "db.supabase_client"
    if mod_name in sys.modules:
        del sys.modules[mod_name]

    with patch.dict("os.environ", env, clear=False):
        with patch("dotenv.load_dotenv", return_value=False):
            return importlib.import_module(mod_name)


def test_create_optional_supabase_returns_none_when_missing():
    from db import supabase_client as sc

    assert sc._create_optional_supabase(None, "key") is None
    assert sc._create_optional_supabase("https://x.supabase.co", None) is None
    assert sc._create_optional_supabase("", "key") is None
    assert sc._create_optional_supabase("https://x.supabase.co", "") is None


def test_create_supabase_requires_url_and_key():
    from db import supabase_client as sc

    with pytest.raises(ValueError, match="required"):
        sc._create_supabase(None, "key")
    with pytest.raises(ValueError, match="required"):
        sc._create_supabase("https://x.supabase.co", None)


def test_module_loads_without_secondary_credentials():
    """GHA のように URL2/3 が無い環境でも主クライアントだけで import できる。"""
    fake_client = MagicMock(name="primary")

    with patch("db.supabase_http.create_supabase_httpx_client", return_value=MagicMock()):
        with patch("supabase.create_client", return_value=fake_client) as create_mock:
            with patch("supabase.lib.client_options.SyncClientOptions"):
                mod = _reload_supabase_client(
                    {
                        "SUPABASE_URL": "https://primary.supabase.co",
                        "SUPABASE_KEY": "primary-key",
                        "SUPABASE_SERVICE_ROLE_KEY": "",
                        "SUPABASE_URL2": "",
                        "SUPABASE_KEY2": "",
                        "SUPABASE_URL3": "",
                        "SUPABASE_KEY3": "",
                    }
                )
                assert mod.supabase is fake_client
                assert mod.supabase2 is None
                assert mod.supabase3 is None
                create_mock.assert_called_once()


def test_module_creates_secondary_when_configured():
    clients = [MagicMock(name="p"), MagicMock(name="s2"), MagicMock(name="s3")]

    with patch("db.supabase_http.create_supabase_httpx_client", return_value=MagicMock()):
        with patch("supabase.create_client", side_effect=clients) as create_mock:
            with patch("supabase.lib.client_options.SyncClientOptions"):
                mod = _reload_supabase_client(
                    {
                        "SUPABASE_URL": "https://primary.supabase.co",
                        "SUPABASE_KEY": "primary-key",
                        "SUPABASE_SERVICE_ROLE_KEY": "",
                        "SUPABASE_URL2": "https://second.supabase.co",
                        "SUPABASE_KEY2": "second-key",
                        "SUPABASE_URL3": "https://third.supabase.co",
                        "SUPABASE_KEY3": "third-key",
                    }
                )
                assert mod.supabase is clients[0]
                assert mod.supabase2 is clients[1]
                assert mod.supabase3 is clients[2]
                assert create_mock.call_count == 3
