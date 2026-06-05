"""プロジェクトルートを sys.path に追加する（scripts 配下からの直接実行用）。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
