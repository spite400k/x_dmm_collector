import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# GHA 等で .env / secrets 未設定でも db.supabase_client を import できるようにする
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-key-for-pytest")

# import 時の create_client / httpx 生成を抑える（テスト方針: 実接続しない）
_supabase_create_patcher = patch(
    "supabase.create_client",
    return_value=MagicMock(name="supabase"),
)
_supabase_create_patcher.start()

from utils.logger import configure_utf8_environment

configure_utf8_environment()
