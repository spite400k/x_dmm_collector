"""scripts/collect/{default,mesugaki,bltl}.py の C1 カバレッジ用テスト。"""

from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock, patch

import pytest

SAMPLE_ITEM = {
    "content_id": "cid-1",
    "title": "t",
    "URL": "https://example.com/i",
    "tachiyomi": {"URL": "https://example.com/t"},
}


def load_collect_module(name: str):
    module_name = f"scripts.collect.{name}"
    if module_name in sys.modules:
        return importlib.reload(sys.modules[module_name])
    return importlib.import_module(module_name)


@pytest.fixture(params=["default", "mesugaki", "bltl"])
def collect_mod(request):
    return load_collect_module(request.param)


class TestCollectMain:
    def _run_main(self, mod, *, fetch_side_effect=None, fetch_return=None, run_error=False):
        exits: list[int] = []

        def fake_exit(code: int) -> None:
            exits.append(code)
            raise SystemExit(code)

        fetch_patch = (
            patch.object(mod, "fetch_items_merged_sorts")
            if mod.__name__.endswith("default") or mod.__name__.endswith("mesugaki")
            else patch.object(mod, "fetch_items")
        )

        with patch.object(mod.sys, "exit", side_effect=fake_exit):
            with patch.object(mod, "setup_logger"):
                with patch.object(mod.os, "makedirs"):
                    with fetch_patch as fetch_mock:
                        if fetch_side_effect is not None:
                            fetch_mock.side_effect = fetch_side_effect
                        else:
                            fetch_mock.return_value = fetch_return or [SAMPLE_ITEM]
                        released_patch = (
                            patch.object(mod, "filter_released_items", return_value=[SAMPLE_ITEM])
                            if hasattr(mod, "filter_released_items")
                            else patch.object(mod, "filter_unregistered_items", return_value=[SAMPLE_ITEM])
                        )
                        with released_patch:
                            with patch.object(
                                mod,
                                "filter_unregistered_items",
                                return_value=[SAMPLE_ITEM],
                            ):
                                with patch.object(
                                    mod,
                                    "run_items_isolated",
                                    return_value=run_error,
                                ) as run_iso:
                                    with pytest.raises(SystemExit):
                                        mod.main()
        expected_code = 0 if not run_error and fetch_side_effect is None else 1
        assert exits == [expected_code]
        if fetch_side_effect is None:
            assert run_iso.call_count >= 1
        return exits

    def test_main_success_default(self):
        mod = load_collect_module("default")
        assert self._run_main(mod) == [0]

    def test_main_success_mesugaki(self):
        mod = load_collect_module("mesugaki")
        assert self._run_main(mod) == [0]

    def test_main_success_bltl(self):
        mod = load_collect_module("bltl")
        assert self._run_main(mod) == [0]

    def test_main_exits_1_on_fetch_error(self, collect_mod):
        assert self._run_main(collect_mod, fetch_side_effect=RuntimeError("api down")) == [1]

    def test_main_exits_1_on_item_errors(self, collect_mod):
        assert self._run_main(collect_mod, run_error=True) == [1]

    def test_main_process_one_registers_item(self):
        mod = load_collect_module("default")

        def fake_run(items, process_one):
            process_one(items[0])
            return False

        with patch.object(mod.sys, "exit", side_effect=lambda c: (_ for _ in ()).throw(SystemExit(c))):
            with patch.object(mod, "setup_logger"):
                with patch.object(mod.os, "makedirs"):
                    with patch.object(mod, "fetch_items_merged_sorts", return_value=[SAMPLE_ITEM]):
                        with patch.object(mod, "filter_released_items", return_value=[SAMPLE_ITEM]):
                            with patch.object(mod, "filter_unregistered_items", return_value=[SAMPLE_ITEM]):
                                with patch.object(mod, "run_items_isolated", side_effect=fake_run):
                                    with patch.object(mod, "register_collected_item") as register:
                                        with pytest.raises(SystemExit):
                                            mod.main()

        assert register.call_count >= 1
        first_call = register.call_args_list[0]
        assert first_call.kwargs["site"] == "DMM.R18"
        assert first_call.kwargs["floor"] == "comic"

    @pytest.mark.parametrize("name,fetch_attr,site,floor", [
        ("mesugaki", "fetch_items_merged_sorts", "DMM.R18", "comic"),
        ("bltl", "fetch_items", "FANZA", "digital_doujin_bl"),
    ])
    def test_main_process_one_registers_item_other_collectors(
        self, name, fetch_attr, site, floor
    ):
        mod = load_collect_module(name)

        def fake_run(items, process_one):
            process_one(items[0])
            return False

        with patch.object(mod.sys, "exit", side_effect=lambda c: (_ for _ in ()).throw(SystemExit(c))):
            with patch.object(mod, "setup_logger"):
                with patch.object(mod.os, "makedirs"):
                    with patch.object(mod, fetch_attr, return_value=[SAMPLE_ITEM]):
                        with patch.object(mod, "filter_unregistered_items", return_value=[SAMPLE_ITEM]):
                            with patch.object(mod, "run_items_isolated", side_effect=fake_run):
                                with patch.object(mod, "register_collected_item") as register:
                                    with pytest.raises(SystemExit):
                                        mod.main()

        register.assert_called()
        first_call = register.call_args_list[0]
        assert first_call.kwargs["site"] == site
        assert first_call.kwargs["floor"] == floor

    def test_mesugaki_fetch_uses_keyword(self):
        mod = load_collect_module("mesugaki")
        with patch.object(mod.sys, "exit", side_effect=lambda c: (_ for _ in ()).throw(SystemExit(c))):
            with patch.object(mod, "setup_logger"):
                with patch.object(mod.os, "makedirs"):
                    with patch.object(mod, "fetch_items_merged_sorts", return_value=[]) as fetch_mock:
                        with patch.object(mod, "filter_unregistered_items", return_value=[]):
                            with patch.object(mod, "run_items_isolated", return_value=False):
                                with pytest.raises(SystemExit):
                                    mod.main()
        assert fetch_mock.call_args.kwargs["keyword"] == "メスガキ"
        assert fetch_mock.call_args.kwargs["supabase_client"] is mod.supabase3

    def test_bltl_uses_fetch_items(self):
        mod = load_collect_module("bltl")
        with patch.object(mod.sys, "exit", side_effect=lambda c: (_ for _ in ()).throw(SystemExit(c))):
            with patch.object(mod, "setup_logger"):
                with patch.object(mod.os, "makedirs"):
                    with patch.object(mod, "fetch_items", return_value=[]) as fetch_mock:
                        with patch.object(mod, "filter_unregistered_items", return_value=[]):
                            with patch.object(mod, "run_items_isolated", return_value=False):
                                with pytest.raises(SystemExit):
                                    mod.main()
        fetch_mock.assert_called()
        assert fetch_mock.call_count == 4
        assert fetch_mock.call_args.kwargs["supabase_client"] is mod.supabase2
