"""openai_api.client の OpenAI / Anthropic 振り分け。"""
from __future__ import annotations

import importlib
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


def _reload_client_with_provider(provider: str, model: str = "test-model"):
    env = {
        "AI_PROVIDER": provider,
        "AI_MODEL": model,
        "OPENAI_API_KEY": "sk-test",
        "ANTHROPIC_API_KEY": "sk-ant-test",
    }
    with patch.dict("os.environ", env, clear=False):
        sys.modules.pop("openai_api.config", None)
        sys.modules.pop("openai_api.client", None)
        import openai_api.config  # noqa: F401

        importlib.reload(sys.modules["openai_api.config"])
        import openai_api.client as client_mod

        return importlib.reload(client_mod)


@pytest.fixture
def openai_client_mod():
    mod = _reload_client_with_provider("openai", "gpt-test")
    mod.reset_clients()
    yield mod
    mod.reset_clients()


@pytest.fixture
def anthropic_client_mod():
    mod = _reload_client_with_provider("anthropic", "claude-test")
    mod.reset_clients()
    yield mod
    mod.reset_clients()


class TestAnthropicTextExtraction:
    def test_string_content(self, openai_client_mod):
        response = SimpleNamespace(content='{"ok":true}')
        assert openai_client_mod._anthropic_text(response) == '{"ok":true}'

    def test_string_blocks_in_list(self, openai_client_mod):
        response = SimpleNamespace(content=["hello", "", " ", "world"])
        assert openai_client_mod._anthropic_text(response) == "hello world"

    def test_typeless_block_with_text(self, openai_client_mod):
        response = SimpleNamespace(
            content=[SimpleNamespace(type=None, text="plain")]
        )
        assert openai_client_mod._anthropic_text(response) == "plain"


class TestStripJsonFence:
    def test_plain_json(self, openai_client_mod):
        assert openai_client_mod._strip_json_fence('{"a":1}') == '{"a":1}'

    def test_fenced_json(self, openai_client_mod):
        raw = '```json\n{"a": 1}\n```'
        assert openai_client_mod._strip_json_fence(raw) == '{"a": 1}'

    def test_fenced_without_lang(self, openai_client_mod):
        raw = '```\n{"b":2}\n```'
        assert openai_client_mod._strip_json_fence(raw) == '{"b":2}'


class TestSplitSystemMessages:
    def test_extracts_system_and_keeps_user(self, openai_client_mod):
        system, converted = openai_client_mod._split_system_messages(
            [
                {"role": "system", "content": "sys1"},
                {"role": "system", "content": "sys2"},
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "yo"},
                {"role": "tool", "content": "x"},
            ]
        )
        assert system == "sys1\n\nsys2"
        assert converted == [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "yo"},
            {"role": "user", "content": "x"},
        ]

    def test_no_system(self, openai_client_mod):
        system, converted = openai_client_mod._split_system_messages(
            [{"role": "user", "content": "only"}]
        )
        assert system is None
        assert converted == [{"role": "user", "content": "only"}]


class TestWantJson:
    def test_true_and_false(self, openai_client_mod):
        assert openai_client_mod._want_json({"type": "json_object"}) is True
        assert openai_client_mod._want_json({"type": "text"}) is False
        assert openai_client_mod._want_json(None) is False
        assert openai_client_mod._want_json("json") is False


class TestOpenAICreate:
    def test_forwards_kwargs(self, openai_client_mod):
        mock_sdk = MagicMock()
        mock_sdk.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
        )
        with patch.object(openai_client_mod, "_get_openai_client", return_value=mock_sdk):
            client = openai_client_mod.get_client()
            result = client.chat.completions.create(
                model="gpt-test",
                messages=[{"role": "user", "content": "hi"}],
                temperature=0.5,
                max_completion_tokens=100,
                response_format={"type": "json_object"},
                ignored_kw="x",
            )
        kwargs = mock_sdk.chat.completions.create.call_args.kwargs
        assert kwargs["model"] == "gpt-test"
        assert kwargs["temperature"] == 0.5
        assert kwargs["max_completion_tokens"] == 100
        assert kwargs["response_format"] == {"type": "json_object"}
        assert result.choices[0].message.content == "ok"

    def test_omits_optional_none(self, openai_client_mod):
        mock_sdk = MagicMock()
        mock_sdk.chat.completions.create.return_value = MagicMock()
        with patch.object(openai_client_mod, "_get_openai_client", return_value=mock_sdk):
            openai_client_mod.get_client().chat.completions.create(
                messages=[{"role": "user", "content": "hi"}],
            )
        kwargs = mock_sdk.chat.completions.create.call_args.kwargs
        assert "temperature" not in kwargs
        assert "max_completion_tokens" not in kwargs
        assert "response_format" not in kwargs
        assert kwargs["model"] == "gpt-test"


class TestAnthropicCreate:
    def test_maps_system_json_and_usage(self, anthropic_client_mod):
        mock_sdk = MagicMock()
        mock_sdk.messages.create.return_value = SimpleNamespace(
            model="claude-test",
            content=[SimpleNamespace(type="text", text='```json\n{"ok":true}\n```')],
            usage=SimpleNamespace(
                input_tokens=10,
                output_tokens=5,
                cache_read_input_tokens=2,
            ),
        )
        with patch.object(
            anthropic_client_mod, "_get_anthropic_client", return_value=mock_sdk
        ):
            result = anthropic_client_mod.get_client().chat.completions.create(
                messages=[
                    {"role": "system", "content": "Be brief"},
                    {"role": "user", "content": "go"},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
                max_completion_tokens=500,
            )

        kwargs = mock_sdk.messages.create.call_args.kwargs
        assert kwargs["model"] == "claude-test"
        assert kwargs["max_tokens"] == 500
        assert kwargs["temperature"] == 0.2
        assert "Be brief" in kwargs["system"]
        assert "JSON object" in kwargs["system"]
        assert kwargs["messages"] == [{"role": "user", "content": "go"}]
        assert result.choices[0].message.content == '{"ok":true}'
        assert result.usage.prompt_tokens == 10
        assert result.usage.completion_tokens == 5
        assert result.usage.total_tokens == 15
        assert result.usage.prompt_tokens_details.cached_tokens == 2

    def test_empty_messages_gets_placeholder_and_default_max_tokens(
        self, anthropic_client_mod
    ):
        mock_sdk = MagicMock()
        mock_sdk.messages.create.return_value = SimpleNamespace(
            model="claude-test",
            content=[{"type": "text", "text": "hello"}],
            usage=SimpleNamespace(input_tokens=1, output_tokens=1),
        )
        with patch.object(
            anthropic_client_mod, "_get_anthropic_client", return_value=mock_sdk
        ):
            result = anthropic_client_mod.get_client().chat.completions.create(
                messages=[{"role": "system", "content": "only-system"}],
            )
        kwargs = mock_sdk.messages.create.call_args.kwargs
        assert kwargs["max_tokens"] == anthropic_client_mod._DEFAULT_ANTHROPIC_MAX_TOKENS
        assert kwargs["messages"] == [{"role": "user", "content": "(empty)"}]
        assert result.choices[0].message.content == "hello"

    def test_usage_none_total_stays_none(self, anthropic_client_mod):
        mock_sdk = MagicMock()
        mock_sdk.messages.create.return_value = SimpleNamespace(
            model=None,
            content=[],
            usage=None,
        )
        with patch.object(
            anthropic_client_mod, "_get_anthropic_client", return_value=mock_sdk
        ):
            result = anthropic_client_mod.get_client().chat.completions.create(
                model="explicit-model",
                messages=[{"role": "user", "content": "x"}],
            )
        assert result.model == "explicit-model"
        assert result.usage.total_tokens is None
        assert result.choices[0].message.content == ""

    def test_skips_non_text_and_empty_blocks(self, anthropic_client_mod):
        mock_sdk = MagicMock()
        mock_sdk.messages.create.return_value = SimpleNamespace(
            model="claude-test",
            content=[
                SimpleNamespace(type="tool_use", text=""),
                SimpleNamespace(type="text", text=""),
                {"type": "text", "text": "kept"},
            ],
            usage=SimpleNamespace(input_tokens=1, output_tokens=1),
        )
        with patch.object(
            anthropic_client_mod, "_get_anthropic_client", return_value=mock_sdk
        ):
            result = anthropic_client_mod.get_client().chat.completions.create(
                messages=[{"role": "user", "content": "x"}],
            )
        assert result.choices[0].message.content == "kept"


class TestLazyClients:
    def test_get_openai_client_caches(self, openai_client_mod):
        openai_client_mod.reset_clients()
        fake = MagicMock()
        with patch.dict("sys.modules", {"openai": MagicMock(OpenAI=MagicMock(return_value=fake))}):
            # Force re-import path inside _get_openai_client
            c1 = openai_client_mod._get_openai_client()
            c2 = openai_client_mod._get_openai_client()
        assert c1 is c2

    def test_get_anthropic_client_caches(self, anthropic_client_mod):
        anthropic_client_mod.reset_clients()
        fake = MagicMock()
        with patch.dict(
            "sys.modules", {"anthropic": MagicMock(Anthropic=MagicMock(return_value=fake))}
        ):
            c1 = anthropic_client_mod._get_anthropic_client()
            c2 = anthropic_client_mod._get_anthropic_client()
        assert c1 is c2
