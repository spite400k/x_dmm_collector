import importlib
import json
import sys
from unittest.mock import MagicMock, patch

import pytest


def load_content_generator_review_module():
    module_name = "utils.content_generator_review"
    if "openai" not in sys.modules:
        openai_mock = MagicMock()
        openai_mock.OpenAI = MagicMock()
        sys.modules["openai"] = openai_mock
    if module_name in sys.modules:
        return importlib.reload(sys.modules[module_name])
    return importlib.import_module(module_name)


@pytest.fixture
def review_module():
    return load_content_generator_review_module()


def test_generate_review_insights_uses_structured_prompt(review_module):
    ai_payload = {
        "review_digest": "要約",
        "content_score": 80,
        "emotion_score": 75,
        "attraction_score": 70,
        "genre_axis1_score": 85,
        "genre_axis2_score": 65,
        "reader_types": ["タイA", "タイB"],
        "warning_points": ["注意A"],
    }
    message = MagicMock()
    message.content = json.dumps(ai_payload)
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]

    reviews = [{"rating": 5, "text": "とても良い作品でした"}]

    with patch.object(review_module.client.chat.completions, "create", return_value=response) as create_mock:
        result = review_module.generate_review_insights(
            reviews=reviews,
            html_summary="あらすじテキスト",
            review_avg=4.5,
            review_count=10,
            genre_type="doujin_digital_doujin",
        )

        call_kwargs = create_mock.call_args.kwargs
        assert call_kwargs["response_format"] == {"type": "json_object"}
        messages = call_kwargs["messages"]
        assert messages[0]["content"] == review_module.REVIEW_INSIGHTS_SYSTEM_PROMPT
        user_content = messages[1]["content"]
        assert "あらすじテキスト" in user_content
        assert "とても良い作品でした" in user_content
        assert "刺さり度（フェチ）" in user_content
        assert "タイプ1" not in user_content
        assert "ワーニング1" not in user_content
        assert '"reader_types": ["...", "..."]' in user_content
        assert "review_digest" in result
        assert "total_score" in result
