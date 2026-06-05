"""メスガキサイト用 Supabase クライアント（プロジェクト URL がデフォルトと異なる）"""

from supabase import create_client, Client
import os
from dotenv import load_dotenv

load_dotenv()

# メスガキ production の Supabase（必要なら MESUGAKI_SUPABASE_URL で上書き）
DEFAULT_MESUGAKI_SUPABASE_URL = "https://xootrpeprhlgzajbcnus.supabase.co"

MESUGAKI_SUPABASE_URL = os.getenv("MESUGAKI_SUPABASE_URL", DEFAULT_MESUGAKI_SUPABASE_URL)
# バッチ書き込みは RLS をバイパスする service_role を優先（anon だと INSERT が拒否される）
MESUGAKI_SUPABASE_KEY = os.getenv("MESUGAKI_SUPABASE_SERVICE_ROLE_KEY") or os.getenv(
    "MESUGAKI_SUPABASE_KEY"
)

if not MESUGAKI_SUPABASE_KEY:
    raise RuntimeError(
        "MESUGAKI_SUPABASE_SERVICE_ROLE_KEY または MESUGAKI_SUPABASE_KEY が未設定です。"
        "バッチ（AIレビュー・週次ランキング等）では service_role キーを .env に設定してください。"
    )

supabase: Client = create_client(MESUGAKI_SUPABASE_URL, MESUGAKI_SUPABASE_KEY)
