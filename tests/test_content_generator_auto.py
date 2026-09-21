"""openai_api.content_generator の購入者コメント抜粋・再生成。"""

from __future__ import annotations

import importlib
import sys
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
        with patch.object(content_generator, "client", mock_client):
            result = content_generator.generate_content_from_reviews(
                title="テスト",
                html_summary="あらすじです",
                reviews=[{"text": "演技が良かった", "rating": 5}],
            )
        assert result["auto_comment"] == "余韻が残る。"
        assert result["auto_summary"] == "感想本文"
        mock_client.chat.completions.create.assert_called_once()
        prompt = mock_client.chat.completions.create.call_args.kwargs["messages"][0][
            "content"
        ]
        assert "演技が良かった" in prompt
        assert "購入者コメント" in prompt
