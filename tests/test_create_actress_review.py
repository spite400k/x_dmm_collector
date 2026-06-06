import importlib
import json
import sys
from unittest.mock import MagicMock, patch

import pytest


class FakeResponse:
    def __init__(self, data):
        self.data = data


def load_create_actress_review_module():
    module_name = "scripts.process.create_actress_review"
    if "openai" not in sys.modules:
        openai_mock = MagicMock()
        openai_mock.OpenAI = MagicMock()
        sys.modules["openai"] = openai_mock
    if module_name in sys.modules:
        return importlib.reload(sys.modules[module_name])
    return importlib.import_module(module_name)


@pytest.fixture
def review_module():
    return load_create_actress_review_module()


def _mock_supabase(review_module):
    mock_supabase = MagicMock()
    review_module.supabase = mock_supabase
    return mock_supabase


def test_format_actress_info_skips_empty_fields(review_module):
    actress = {
        "name": "テスト",
        "height": None,
        "bust": "",
        "profile": "プロフィール本文",
        "career_text": "",
    }
    info = review_module._format_actress_info(actress)
    assert "名前: テスト" in info
    assert "身長" not in info
    assert "バスト" not in info
    assert "プロフィール:\nプロフィール本文" in info
    assert "経歴" not in info


def test_generate_actress_ai_profile_success(review_module):
    actress = {"name": "テスト", "height": 160}
    ai_payload = {"ai_summary": "s", "ai_career": "c", "ai_appeal": "a"}
    message = MagicMock()
    message.content = json.dumps(ai_payload)
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]

    with patch.object(review_module.client.chat.completions, "create", return_value=response) as create_mock:
        result = review_module.generate_actress_ai_profile(actress)
        assert result == ai_payload
        call_kwargs = create_mock.call_args.kwargs
        assert call_kwargs["response_format"] == {"type": "json_object"}
        messages = call_kwargs["messages"]
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == review_module.ACTRESS_SYSTEM_PROMPT
        assert "名前: テスト" in messages[1]["content"]
        assert "SEO" not in messages[1]["content"]


def test_generate_actress_ai_profile_failure(review_module):
    with patch.object(
        review_module.client.chat.completions,
        "create",
        side_effect=RuntimeError("openai"),
    ):
        assert review_module.generate_actress_ai_profile({"name": "x"}) is None


def test_save_actress_ai(review_module):
    mock_supabase = _mock_supabase(review_module)
    table = MagicMock()
    chain = table.update.return_value.eq.return_value
    chain.execute.return_value = FakeResponse([])
    mock_supabase.table.return_value = table

    review_module.save_actress_ai(10, {"ai_summary": "s", "ai_career": "c", "ai_appeal": "a"})

    update_data = table.update.call_args[0][0]
    assert update_data["ai_summary"] == "s"
    table.update.return_value.eq.assert_called_once_with("actress_id", 10)


def test_get_actresses_without_ai(review_module):
    mock_supabase = _mock_supabase(review_module)
    table = MagicMock()
    chain = table.select.return_value.is_.return_value.limit.return_value
    chain.execute.return_value = FakeResponse([{"actress_id": 1}])
    mock_supabase.table.return_value = table

    assert review_module.get_actresses_without_ai() == [{"actress_id": 1}]


def test_get_actresses_by_ids(review_module):
    mock_supabase = _mock_supabase(review_module)
    table = MagicMock()
    chain = table.select.return_value.in_.return_value
    chain.execute.return_value = FakeResponse([{"actress_id": 2}])
    mock_supabase.table.return_value = table

    assert review_module.get_actresses_by_ids([2]) == [{"actress_id": 2}]


def test_get_actress_by_name(review_module):
    mock_supabase = _mock_supabase(review_module)
    table = MagicMock()
    chain = table.select.return_value.eq.return_value.limit.return_value
    chain.execute.return_value = FakeResponse([{"actress_id": 3, "name": "A"}])
    mock_supabase.table.return_value = table

    assert review_module.get_actress_by_name("A") == {"actress_id": 3, "name": "A"}


def test_get_actress_by_name_not_found(review_module):
    mock_supabase = _mock_supabase(review_module)
    table = MagicMock()
    chain = table.select.return_value.eq.return_value.limit.return_value
    chain.execute.return_value = FakeResponse([])
    mock_supabase.table.return_value = table

    assert review_module.get_actress_by_name("missing") is None


def test_get_target_actresses_default(review_module):
    with patch.object(review_module, "get_actresses_without_ai", return_value=[{"actress_id": 1}]):
        assert review_module.get_target_actresses() == [{"actress_id": 1}]


def test_get_target_actresses_by_ids(review_module):
    with patch.object(review_module, "get_actresses_by_ids", return_value=[{"actress_id": 2}]):
        assert review_module.get_target_actresses(actress_ids=[2]) == [{"actress_id": 2}]


def test_get_target_actresses_by_name(review_module):
    with patch.object(review_module, "get_actress_by_name", return_value={"actress_id": 3}):
        assert review_module.get_target_actresses(name="A") == [{"actress_id": 3}]

    with patch.object(review_module, "get_actress_by_name", return_value=None):
        assert review_module.get_target_actresses(name="missing") == []


def test_process_actresses_empty(review_module):
    review_module.process_actresses([])


def test_process_actresses_success(review_module):
    actresses = [{"actress_id": 1, "name": "A"}]
    ai = {"ai_summary": "s", "ai_career": "c", "ai_appeal": "a"}

    with patch.object(review_module, "generate_actress_ai_profile", return_value=ai):
        with patch.object(review_module, "save_actress_ai") as save_mock:
            with patch.object(review_module.time, "sleep") as sleep_mock:
                review_module.process_actresses(actresses, regenerate=True)
                save_mock.assert_called_once_with(1, ai)
                sleep_mock.assert_called_once()


def test_process_actresses_ai_failure(review_module):
    actresses = [{"actress_id": 2, "name": "B"}]

    with patch.object(review_module, "generate_actress_ai_profile", return_value=None):
        with patch.object(review_module, "save_actress_ai") as save_mock:
            review_module.process_actresses(actresses)
            save_mock.assert_not_called()


def test_parse_args(review_module):
    args = review_module.parse_args(["--actress-id", "1", "--actress-id", "2", "--name", "A"])
    assert args.actress_ids == [1, 2]
    assert args.name == "A"


def test_main_batch_mode(review_module):
    actresses = [{"actress_id": 1, "name": "A"}]

    with patch.object(review_module, "get_target_actresses", return_value=actresses):
        with patch.object(review_module, "process_actresses") as process_mock:
            review_module.main([])
            process_mock.assert_called_once_with(actresses, regenerate=False)


def test_main_regenerate_by_id(review_module):
    actresses = [{"actress_id": 1, "name": "A"}]

    with patch.object(review_module, "get_target_actresses", return_value=actresses):
        with patch.object(review_module, "process_actresses") as process_mock:
            review_module.main(["--actress-id", "1", "--actress-id", "99"])
            process_mock.assert_called_once_with(actresses, regenerate=True)


def test_main_regenerate_missing_ids(review_module):
    actresses = [{"actress_id": 1, "name": "A"}]

    with patch.object(review_module, "get_target_actresses", return_value=actresses):
        with patch.object(review_module, "process_actresses"):
            review_module.main(["--actress-id", "1", "--actress-id", "99"])


def test_main_regenerate_by_name_not_found(review_module):
    with patch.object(review_module, "get_target_actresses", return_value=[]):
        with patch.object(review_module, "process_actresses") as process_mock:
            review_module.main(["--name", "missing"])
            process_mock.assert_called_once_with([], regenerate=True)


def test_main_conflicting_args(review_module):
    with patch.object(review_module.sys, "exit", side_effect=lambda code: (_ for _ in ()).throw(SystemExit(code))):
        with pytest.raises(SystemExit) as exc:
            review_module.main(["--actress-id", "1", "--name", "A"])
        assert exc.value.code == 1
