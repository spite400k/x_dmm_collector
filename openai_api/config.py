"""OpenAI API 共通設定。"""
import os

from dotenv import load_dotenv

load_dotenv()

# 未設定時は既存スクリプトで最も多く使われているモデルを既定にする
DEFAULT_OPENAI_MODEL = "gpt-5.4-nano"
OPENAI_MODEL = os.getenv("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL
