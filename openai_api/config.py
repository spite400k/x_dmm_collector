"""LLM API 共通設定（OpenAI / Anthropic）。"""
import os

from dotenv import load_dotenv

load_dotenv()

DEFAULT_OPENAI_MODEL = "gpt-6-luna"
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-5"


def _normalize_provider(value: str | None) -> str:
    raw = (value or "openai").strip().lower()
    if raw in ("anthropic", "claude"):
        return "anthropic"
    return "openai"


AI_PROVIDER = _normalize_provider(os.getenv("AI_PROVIDER"))


def _resolve_model() -> str:
    for key in ("AI_MODEL", "OPENAI_MODEL"):
        val = os.getenv(key)
        if val and val.strip():
            return val.strip()
    if AI_PROVIDER == "anthropic":
        return DEFAULT_ANTHROPIC_MODEL
    return DEFAULT_OPENAI_MODEL


# 後方互換のため OPENAI_MODEL 名を維持（Anthropic 利用時も実モデル名が入る）
OPENAI_MODEL = _resolve_model()
AI_MODEL = OPENAI_MODEL


def llm_api_key_env_name() -> str:
    """現在のプロバイダに対応する API キー環境変数名。"""
    if AI_PROVIDER == "anthropic":
        return "ANTHROPIC_API_KEY"
    return "OPENAI_API_KEY"


def get_llm_api_key() -> str | None:
    """現在のプロバイダ向け API キー（未設定なら None）。"""
    return os.getenv(llm_api_key_env_name())
