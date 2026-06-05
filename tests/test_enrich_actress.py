import importlib
import sys
from unittest.mock import MagicMock, patch

import pytest


class FakeResponse:
    def __init__(self, data):
        self.data = data


def load_enrich_actress_module():
    module_name = "scripts.process.enrich_actress"
    if module_name in sys.modules:
        return importlib.reload(sys.modules[module_name])
    return importlib.import_module(module_name)


@pytest.fixture
def enrich_module():
    return load_enrich_actress_module()


def _exit_raises(code):
    raise SystemExit(code)


def test_main_no_targets(enrich_module):
    with patch.object(enrich_module, "fetch_actresses_to_enrich", return_value=[]):
        with patch.object(enrich_module.sys, "exit", side_effect=_exit_raises) as exit_mock:
            with pytest.raises(SystemExit) as exc:
                enrich_module.main()
            assert exc.value.code == 0
            exit_mock.assert_called_once_with(0)


def test_main_success_flow(enrich_module):
    actresses = [{"actress_id": 1, "name": "山田"}]
    enriched = {"name": "山田", "profile": "p"}
    session = MagicMock()

    with patch.object(enrich_module, "fetch_actresses_to_enrich", return_value=actresses):
        with patch.object(enrich_module, "_create_session", return_value=session):
            with patch.object(enrich_module, "enrich_actress", return_value=enriched):
                with patch.object(enrich_module, "enrich_and_update_actress", return_value=True):
                    with patch.object(enrich_module.sys, "exit", side_effect=_exit_raises) as exit_mock:
                        with pytest.raises(SystemExit):
                            enrich_module.main()
                        session.close.assert_called_once()
                        exit_mock.assert_called_once_with(0)


def test_main_skip_unenrichable_name(enrich_module):
    actresses = [{"actress_id": 2, "name": "----"}]

    with patch.object(enrich_module, "fetch_actresses_to_enrich", return_value=actresses):
        with patch.object(enrich_module, "_create_session", return_value=MagicMock()):
            with patch.object(enrich_module, "touch_actress_updated_at", return_value=True):
                with patch.object(enrich_module, "enrich_actress") as enrich_mock:
                    with patch.object(enrich_module.sys, "exit", side_effect=_exit_raises) as exit_mock:
                        with pytest.raises(SystemExit):
                            enrich_module.main()
                        enrich_mock.assert_not_called()
                        exit_mock.assert_called_once_with(0)


def test_main_skip_unenrichable_touch_fail(enrich_module):
    actresses = [{"actress_id": 2, "name": "----"}]

    with patch.object(enrich_module, "fetch_actresses_to_enrich", return_value=actresses):
        with patch.object(enrich_module, "_create_session", return_value=MagicMock()):
            with patch.object(enrich_module, "touch_actress_updated_at", return_value=False):
                with patch.object(enrich_module.sys, "exit", side_effect=_exit_raises) as exit_mock:
                    with pytest.raises(SystemExit) as exc:
                        enrich_module.main()
                    assert exc.value.code == 1
                    exit_mock.assert_called_once_with(1)


def test_main_enrich_exception(enrich_module):
    actresses = [{"actress_id": 3, "name": "佐藤"}]

    with patch.object(enrich_module, "fetch_actresses_to_enrich", return_value=actresses):
        with patch.object(enrich_module, "_create_session", return_value=MagicMock()):
            with patch.object(enrich_module, "enrich_actress", side_effect=RuntimeError("api")):
                with patch.object(enrich_module.sys, "exit", side_effect=_exit_raises) as exit_mock:
                    with pytest.raises(SystemExit) as exc:
                        enrich_module.main()
                    assert exc.value.code == 1
                    exit_mock.assert_called_once_with(1)


def test_main_empty_enriched(enrich_module):
    actresses = [{"actress_id": 4, "name": "鈴木"}]

    with patch.object(enrich_module, "fetch_actresses_to_enrich", return_value=actresses):
        with patch.object(enrich_module, "_create_session", return_value=MagicMock()):
            with patch.object(enrich_module, "enrich_actress", return_value=None):
                with patch.object(enrich_module, "touch_actress_updated_at", return_value=True):
                    with patch.object(enrich_module.sys, "exit", side_effect=_exit_raises) as exit_mock:
                        with pytest.raises(SystemExit):
                            enrich_module.main()
                        exit_mock.assert_called_once_with(0)


def test_main_empty_enriched_touch_fail(enrich_module):
    actresses = [{"actress_id": 4, "name": "鈴木"}]

    with patch.object(enrich_module, "fetch_actresses_to_enrich", return_value=actresses):
        with patch.object(enrich_module, "_create_session", return_value=MagicMock()):
            with patch.object(enrich_module, "enrich_actress", return_value=None):
                with patch.object(enrich_module, "touch_actress_updated_at", return_value=False):
                    with patch.object(enrich_module.sys, "exit", side_effect=_exit_raises) as exit_mock:
                        with pytest.raises(SystemExit) as exc:
                            enrich_module.main()
                        assert exc.value.code == 1
                        exit_mock.assert_called_once_with(1)


def test_main_update_fail(enrich_module):
    actresses = [{"actress_id": 5, "name": "高橋"}]

    with patch.object(enrich_module, "fetch_actresses_to_enrich", return_value=actresses):
        with patch.object(enrich_module, "_create_session", return_value=MagicMock()):
            with patch.object(enrich_module, "enrich_actress", return_value={"name": "高橋"}):
                with patch.object(enrich_module, "enrich_and_update_actress", return_value=False):
                    with patch.object(enrich_module.sys, "exit", side_effect=_exit_raises) as exit_mock:
                        with pytest.raises(SystemExit) as exc:
                            enrich_module.main()
                        assert exc.value.code == 1
                        exit_mock.assert_called_once_with(1)


def test_main_fetch_failure(enrich_module):
    with patch.object(
        enrich_module,
        "fetch_actresses_to_enrich",
        side_effect=RuntimeError("db"),
    ):
        with patch.object(enrich_module.sys, "exit", side_effect=_exit_raises) as exit_mock:
            with pytest.raises(SystemExit) as exc:
                enrich_module.main()
            assert exc.value.code == 1
            exit_mock.assert_called_once_with(1)
