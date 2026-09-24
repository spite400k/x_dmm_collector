"""openai_api.usage のトークンログ。"""

import logging
from types import SimpleNamespace

from openai_api.usage import (
    _as_int,
    _as_text,
    _fmt,
    _get,
    log_configured_model,
    log_openai_usage,
)


class TestUsageHelpers:
    def test_get_none_dict_and_attr(self):
        assert _get(None, "usage", "fallback") == "fallback"
        assert _get({"usage": 1}, "usage") == 1
        assert _get({}, "usage", "missing") == "missing"

        class Row:
            usage = 2

        assert _get(Row(), "usage") == 2
        assert _get(Row(), "model", "missing") == "missing"

    def test_as_int_rejects_and_parses(self):
        assert _as_int(None) is None
        assert _as_int(True) is None
        assert _as_int(object()) is None
        assert _as_int("") is None
        assert _as_int("  ") is None
        assert _as_int("abc") is None
        assert _as_int(12) == 12
        assert _as_int(12.9) == 12
        assert _as_int("15") == 15

    def test_as_text_and_fmt(self):
        assert _as_text(None) is None
        assert _as_text(1) is None
        assert _as_text("") is None
        assert _as_text("  ") is None
        assert _as_text(" gpt-5.6-luna ") == "gpt-5.6-luna"
        assert _fmt(None) == "-"
        assert _fmt(3) == 3


class TestLogOpenaiUsage:
    def test_logs_dict_usage(self, caplog):
        caplog.set_level(logging.INFO)
        log_openai_usage(
            {
                "model": "gpt-5.6-luna",
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 8.2,
                    "total_tokens": "18",
                    "prompt_tokens_details": {"cached_tokens": 4},
                },
            },
            purpose="review_insights",
            content_id="cid-1",
        )
        assert (
            "OpenAI usage purpose=review_insights content_id=cid-1 "
            "model=gpt-5.6-luna prompt_tokens=10 completion_tokens=8 "
            "total_tokens=18 cached_tokens=4"
        ) in caplog.text

    def test_logs_object_usage_and_blank_ids(self, caplog):
        caplog.set_level(logging.INFO)
        response = SimpleNamespace(
            model="  ",
            usage=SimpleNamespace(
                prompt_tokens="abc",
                completion_tokens=True,
                total_tokens=None,
                prompt_tokens_details=SimpleNamespace(cached_tokens=""),
            ),
        )
        log_openai_usage(response, purpose="auto_content", content_id="  ")
        assert (
            "OpenAI usage purpose=auto_content content_id=- model=- "
            "prompt_tokens=- completion_tokens=- total_tokens=- cached_tokens=-"
        ) in caplog.text

    def test_logs_when_response_missing(self, caplog):
        caplog.set_level(logging.INFO)
        log_openai_usage(None, purpose="auto_content", content_id=None)
        assert "purpose=auto_content content_id=- model=-" in caplog.text
        assert "prompt_tokens=-" in caplog.text


def test_log_configured_model(caplog):
    caplog.set_level(logging.INFO)
    log_configured_model()
    assert "OpenAI configured model=" in caplog.text
    assert "default=" in caplog.text
