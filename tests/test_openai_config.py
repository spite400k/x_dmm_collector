import importlib
import os
from unittest.mock import patch


def test_openai_model_default():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("OPENAI_MODEL", None)
        import openai_api.config as config

        mod = importlib.reload(config)
        assert mod.OPENAI_MODEL == mod.DEFAULT_OPENAI_MODEL


def test_openai_model_from_env():
    with patch.dict(os.environ, {"OPENAI_MODEL": "gpt-4.1-mini"}, clear=False):
        import openai_api.config as config

        mod = importlib.reload(config)
        assert mod.OPENAI_MODEL == "gpt-4.1-mini"


def test_openai_model_empty_falls_back_to_default():
    with patch.dict(os.environ, {"OPENAI_MODEL": ""}, clear=False):
        import openai_api.config as config

        mod = importlib.reload(config)
        assert mod.OPENAI_MODEL == mod.DEFAULT_OPENAI_MODEL
