import importlib
import os
import sys
from unittest.mock import patch


def _reload_openai_config():
    sys.modules.pop("openai_api.config", None)
    import openai_api.config as config

    return importlib.reload(config)


def test_openai_model_default():
    env = {k: v for k, v in os.environ.items() if k != "OPENAI_MODEL"}
    with patch.dict(os.environ, env, clear=True):
        with patch("dotenv.load_dotenv", lambda *a, **k: None):
            mod = _reload_openai_config()
            assert mod.OPENAI_MODEL == mod.DEFAULT_OPENAI_MODEL


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
