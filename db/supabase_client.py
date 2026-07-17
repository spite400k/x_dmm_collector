from supabase import create_client, Client
from supabase.lib.client_options import SyncClientOptions as ClientOptions
import os
from dotenv import load_dotenv

from db.supabase_http import create_supabase_httpx_client

load_dotenv()


def _create_supabase(url: str | None, key: str | None) -> Client:
    options = ClientOptions(httpx_client=create_supabase_httpx_client())
    return create_client(url, key, options=options)


SUPABASE_URL = os.getenv("SUPABASE_URL")
# service_role キーがあれば優先（RLS/GRANT の影響を受けないサーバー側実行のため）
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")

supabase: Client = _create_supabase(SUPABASE_URL, SUPABASE_KEY)


SUPABASE_URL2 = os.getenv("SUPABASE_URL2")
SUPABASE_KEY2 = os.getenv("SUPABASE_KEY2")

supabase2: Client = _create_supabase(SUPABASE_URL2, SUPABASE_KEY2)

SUPABASE_URL3 = os.getenv("SUPABASE_URL3")
SUPABASE_KEY3 = os.getenv("SUPABASE_KEY3")

supabase3: Client = _create_supabase(SUPABASE_URL3, SUPABASE_KEY3)
