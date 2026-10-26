import importlib
import os
import sys
from unittest.mock import patch


def _reload_openai_config():
    sys.modules.pop("openai_api.config", None)
    import openai_api.config as config

    return importlib.reload(config)


def test_openai_model_default():
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("OPENAI_MODEL", "AI_MODEL", "AI_PROVIDER")
    }
    with patch.dict(os.environ, env, clear=True):
        with patch("dotenv.load_dotenv", lambda *a, **k: None):
            mod = _reload_openai_config()
            assert mod.DEFAULT_OPENAI_MODEL == "gpt-6-luna"
            assert mod.AI_PROVIDER == "openai"
            assert mod.OPENAI_MODEL == mod.DEFAULT_OPENAI_MODEL
            assert mod.AI_MODEL == mod.OPENAI_MODEL


def test_openai_model_from_env():
    with patch("dotenv.load_dotenv", lambda *a, **k: None):
        with patch.dict(os.environ, {"OPENAI_MODEL": "gpt-4.1-mini"}, clear=True):
            mod = _reload_openai_config()
            assert mod.OPENAI_MODEL == "gpt-4.1-mini"


def test_openai_model_empty_falls_back_to_default():
    with patch("dotenv.load_dotenv", lambda *a, **k: None):
        with patch.dict(os.environ, {"OPENAI_MODEL": ""}, clear=True):
            mod = _reload_openai_config()
            assert mod.OPENAI_MODEL == mod.DEFAULT_OPENAI_MODEL


def test_ai_model_takes_precedence_over_openai_model():
    with patch("dotenv.load_dotenv", lambda *a, **k: None):
        with patch.dict(
            os.environ,
            {"AI_MODEL": "claude-sonnet-4-5", "OPENAI_MODEL": "gpt-4.1-mini"},
            clear=True,
        ):
            mod = _reload_openai_config()
            assert mod.OPENAI_MODEL == "claude-sonnet-4-5"


def test_anthropic_provider_default_model():
    with patch("dotenv.load_dotenv", lambda *a, **k: None):
        with patch.dict(os.environ, {"AI_PROVIDER": "anthropic"}, clear=True):
            mod = _reload_openai_config()
            assert mod.AI_PROVIDER == "anthropic"
            assert mod.OPENAI_MODEL == mod.DEFAULT_ANTHROPIC_MODEL


def test_claude_alias_maps_to_anthropic():
    with patch("dotenv.load_dotenv", lambda *a, **k: None):
        with patch.dict(os.environ, {"AI_PROVIDER": "Claude"}, clear=True):
            mod = _reload_openai_config()
            assert mod.AI_PROVIDER == "anthropic"


def test_llm_api_key_helpers_openai():
    with patch("dotenv.load_dotenv", lambda *a, **k: None):
        with patch.dict(
            os.environ,
            {"AI_PROVIDER": "openai", "OPENAI_API_KEY": "sk-o"},
            clear=True,
        ):
            mod = _reload_openai_config()
            assert mod.llm_api_key_env_name() == "OPENAI_API_KEY"
            assert mod.get_llm_api_key() == "sk-o"


def test_llm_api_key_helpers_anthropic():
    with patch("dotenv.load_dotenv", lambda *a, **k: None):
        with patch.dict(
            os.environ,
            {"AI_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "sk-a"},
            clear=True,
        ):
            mod = _reload_openai_config()
            assert mod.llm_api_key_env_name() == "ANTHROPIC_API_KEY"
            assert mod.get_llm_api_key() == "sk-a"
