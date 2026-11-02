"""openai_api.content_generator の購入者コメント抜粋・再生成。"""

from __future__ import annotations

import importlib
import json
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


def load_content_generator_module():
    module_name = "openai_api.content_generator"
    if "openai" not in sys.modules:
        openai_mock = MagicMock()
        openai_mock.OpenAI = MagicMock()
        sys.modules["openai"] = openai_mock
    with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}, clear=False):
        if module_name in sys.modules:
            return importlib.reload(sys.modules[module_name])
        return importlib.import_module(module_name)


@pytest.fixture
def content_generator():
    return load_content_generator_module()


class TestSelectReviewExcerpts:
    def test_empty_and_blank_text(self, content_generator):
        assert content_generator.select_review_excerpts(None) == []
        assert content_generator.select_review_excerpts([]) == []
        assert content_generator.select_review_excerpts([{"text": "  ", "rating": 5}]) == []

    def test_prefers_high_rating_then_longer_text(self, content_generator):
        reviews = [
            {"text": "短い", "rating": 5},
            {"text": "とても長いコメントですよ", "rating": 5},
            {"text": "低評価でも長い文章あああ", "rating": 2},
            {"text": "中くらい", "rating": 4},
        ]
        excerpts = content_generator.select_review_excerpts(reviews, max_count=3)
        assert len(excerpts) == 3
        assert excerpts[0]["text"] == "とても長いコメントですよ"
        assert excerpts[0]["rating"] == 5.0
        assert excerpts[1]["text"] == "短い"
        assert excerpts[2]["rating"] == 4.0

    def test_truncates_text(self, content_generator):
        long_text = "あ" * 400
        excerpts = content_generator.select_review_excerpts(
            [{"text": long_text, "rating": 5}],
            truncate=250,
        )
        assert len(excerpts) == 1
        assert len(excerpts[0]["text"]) == 250


class TestGenerateContentFromReviews:
    def test_returns_empty_without_excerpts(self, content_generator):
        result = content_generator.generate_content_from_reviews(reviews=[])
        assert result == {
            "auto_comment": "",
            "auto_summary": "",
            "auto_point": "",
        }

    def test_calls_openai_when_reviews_exist(self, content_generator):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value.choices[
            0
        ].message.content = (
            '{"auto_comment":"余韻が残る。","auto_summary":"感想本文",'
            '"auto_point":"・ポイント"}'
        )
        with (
            patch.object(content_generator, "client", mock_client),
            patch.object(content_generator, "log_openai_usage") as usage_mock,
        ):
            result = content_generator.generate_content_from_reviews(
                title="テスト",
                html_summary="あらすじです",
                reviews=[{"text": "演技が良かった", "rating": 5}],
                content_id="cid-1",
            )
        assert result["auto_comment"] == "余韻が残る。"
        assert result["auto_summary"] == "感想本文"
        mock_client.chat.completions.create.assert_called_once()
        prompt = mock_client.chat.completions.create.call_args.kwargs["messages"][0][
            "content"
        ]
        assert "演技が良かった" in prompt
        assert "購入者コメント" in prompt
        usage_mock.assert_called_once()
        assert usage_mock.call_args.kwargs["purpose"] == "auto_content_from_reviews"
        assert usage_mock.call_args.kwargs["content_id"] == "cid-1"
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["max_completion_tokens"] == 8192
        assert call_kwargs["response_format"] == {"type": "json_object"}


def _chat_response(content, *, stop_reason=None, finish_reason=None):
    return SimpleNamespace(
        stop_reason=stop_reason,
        choices=[
            SimpleNamespace(
                finish_reason=finish_reason,
                message=SimpleNamespace(content=content),
            )
        ],
    )


_VALID_JSON = (
    '{"auto_comment":"余韻が残る。","auto_summary":"感想本文","auto_point":"・ポイント"}'
)


class TestParseAutoContentResponse:
    def test_extracts_object_from_preamble_and_fence(self, content_generator):
        fenced = (
            '前置きです\n```json\n'
            '{"auto_comment":"a","auto_summary":"b\\\\nc","auto_point":"d"}\n```'
        )
        data = content_generator._parse_auto_content_response(fenced)
        assert data["auto_comment"] == "a"
        assert data["auto_summary"] == "b\nc"
        assert data["auto_point"] == "d"

        plain_fence = f"```\n{_VALID_JSON}\n```"
        parsed = content_generator._parse_auto_content_response(plain_fence)
        assert parsed["auto_summary"] == "感想本文"

        trailing_fence = _VALID_JSON + "```"
        assert content_generator._parse_auto_content_response(trailing_fence)["auto_comment"]

    def test_rejects_non_object_and_non_json(self, content_generator):
        with pytest.raises(ValueError):
            content_generator._parse_auto_content_response("[1]")
        with pytest.raises(json.JSONDecodeError):
            content_generator._parse_auto_content_response("拒否しました")
        with pytest.raises(json.JSONDecodeError):
            content_generator._parse_auto_content_response(None)
        with pytest.raises(json.JSONDecodeError):
            content_generator._parse_auto_content_response("{unterminated")
        with pytest.raises(json.JSONDecodeError):
            content_generator._parse_auto_content_response("}{")

    def test_leaves_non_string_fields(self, content_generator):
        raw = '{"auto_comment":1,"auto_summary":"b","auto_point":"d"}'
        data = content_generator._parse_auto_content_response(raw)
        assert data["auto_comment"] == 1


class TestCallAutoContentOpenAI:
    def test_retries_once_then_parses(self, content_generator):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            _chat_response("生成できません", stop_reason="refusal"),
            _chat_response(_VALID_JSON, stop_reason="end_turn"),
        ]
        with (
            patch.object(content_generator, "client", mock_client),
            patch.object(content_generator, "log_openai_usage"),
        ):
            result = content_generator._call_auto_content_openai(
                "prompt",
                purpose="auto_content_from_reviews",
                content_id="cid-1",
            )
        assert result["auto_comment"] == "余韻が残る。"
        assert mock_client.chat.completions.create.call_count == 2

    def test_retries_after_api_error_then_succeeds(self, content_generator):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            TimeoutError("timeout"),
            _chat_response(_VALID_JSON, finish_reason="stop"),
        ]
        with (
            patch.object(content_generator, "client", mock_client),
            patch.object(content_generator, "log_openai_usage"),
        ):
            result = content_generator._call_auto_content_openai(
                "prompt",
                purpose="auto_content",
                content_id=None,
            )
        assert result["auto_summary"] == "感想本文"
        assert mock_client.chat.completions.create.call_count == 2

    def test_gives_up_after_two_failures(self, content_generator):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            _chat_response(None, finish_reason="length"),
            _chat_response("まだ JSON ではない", stop_reason="  ", finish_reason="length"),
        ]
        with (
            patch.object(content_generator, "client", mock_client),
            patch.object(content_generator, "log_openai_usage"),
        ):
            result = content_generator._call_auto_content_openai(
                "prompt",
                purpose="auto_content",
                content_id="cid-2",
            )
        assert result == {
            "auto_comment": "",
            "auto_summary": "",
            "auto_point": "",
        }
        assert mock_client.chat.completions.create.call_count == 2

    def test_stop_reason_helpers(self, content_generator):
        assert content_generator._response_stop_reason(None) == "-"
        assert (
            content_generator._response_stop_reason(
                SimpleNamespace(stop_reason="refusal", choices=[])
            )
            == "refusal"
        )
        assert (
            content_generator._response_stop_reason(
                SimpleNamespace(
                    stop_reason="  ",
                    choices=[SimpleNamespace(finish_reason="length")],
                )
            )
            == "length"
        )
        assert (
            content_generator._response_stop_reason(
                SimpleNamespace(stop_reason=None, choices=[])
            )
            == "-"
        )
        assert (
            content_generator._response_stop_reason(
                SimpleNamespace(
                    stop_reason=None,
                    choices=[SimpleNamespace(finish_reason="  ")],
                )
            )
            == "-"
        )
        assert (
            content_generator._response_stop_reason(
                SimpleNamespace(
                    stop_reason=None,
                    choices=[SimpleNamespace(finish_reason=1)],
                )
            )
            == "-"
        )
        assert content_generator._response_stop_reason(SimpleNamespace()) == "-"
        assert content_generator._content_snippet("a\nb") == "a\\nb"
        assert content_generator._content_snippet(None) == ""
        assert len(content_generator._content_snippet("x" * 250)) == 200
