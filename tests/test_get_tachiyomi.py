"""get_tachiyomi のタイムアウト短縮・最終ページ即時判定・Publus 対応のテスト。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import utils.get_tachiyomi as tachiyomi


def test_capture_skips_long_endofbook_wait(tmp_path, monkeypatch):
    """endOfBook は WebDriverWait(30) せず is_end_of_book で即判定する。"""
    driver = MagicMock()
    driver.page_source = "<html></html>"
    from selenium.common.exceptions import TimeoutException

    wait_calls = []

    class FakeWait:
        def __init__(self, drv, timeout):
            wait_calls.append(timeout)
            self.timeout = timeout

        def until(self, method):
            # age check / viewer ready / canvas
            if self.timeout == 20:
                return "publus"
            if self.timeout == 5:
                raise TimeoutException("canvas")
            if self.timeout == 10:
                return [1, 2]
            return MagicMock()

        def until_not(self, method):
            return True

    with patch.object(tachiyomi, "create_chrome_driver", return_value=driver):
        with patch.object(tachiyomi, "quit_chrome_driver") as quit_mock:
            with patch.object(tachiyomi, "WebDriverWait", FakeWait):
                with patch.object(tachiyomi, "ActionChains"):
                    with patch.object(tachiyomi.os, "makedirs"):
                        with patch.object(tachiyomi, "save_page_source"):
                            with patch.object(
                                tachiyomi, "detect_viewer_kind", return_value="publus"
                            ):
                                with patch.object(
                                    tachiyomi, "is_end_of_book", return_value=False
                                ) as end_mock:
                                    with patch.object(
                                        tachiyomi,
                                        "get_page_counter",
                                        return_value=(1, 2),
                                    ):
                                        result = tachiyomi.capture_all_tachiyomi_pages(
                                            "https://example.com/t"
                                        )

    assert result == []
    # 旧実装の endOfBook 用 30 秒待ちが残っていないこと
    assert 30 not in wait_calls
    end_mock.assert_called()
    quit_mock.assert_called_once_with(driver)


def test_capture_quits_even_on_get_failure(monkeypatch):
    driver = MagicMock()
    driver.get.side_effect = [None, RuntimeError("boom")]  # top ok, tachiyomi fail

    class FakeWait:
        def __init__(self, *a, **k):
            pass

        def until(self, method):
            raise tachiyomi.TimeoutException("age")

    with patch.object(tachiyomi, "create_chrome_driver", return_value=driver):
        with patch.object(tachiyomi, "quit_chrome_driver") as quit_mock:
            with patch.object(tachiyomi, "WebDriverWait", FakeWait):
                with patch.object(tachiyomi.os, "makedirs"):
                    result = tachiyomi.capture_all_tachiyomi_pages("https://example.com/t")

    assert result == []
    quit_mock.assert_called_once_with(driver)


def test_capture_returns_empty_when_chrome_launch_fails():
    with patch.object(
        tachiyomi,
        "create_chrome_driver",
        side_effect=RuntimeError("session not created"),
    ):
        with patch.object(tachiyomi.os, "makedirs"):
            result = tachiyomi.capture_all_tachiyomi_pages("https://example.com/t")

    assert result == []


def test_get_visible_canvas_publus_uses_shadow_js():
    driver = MagicMock()
    canvas = MagicMock(name="canvas")
    with patch.object(tachiyomi, "detect_viewer_kind", return_value="publus"):
        driver.execute_script.return_value = canvas
        assert tachiyomi.get_visible_canvas(driver) is canvas
    driver.execute_script.assert_called_once_with(tachiyomi._PUBLUS_CURRENT_CANVAS_JS)


def test_get_visible_canvas_legacy_scans_light_dom():
    driver = MagicMock()
    visible = MagicMock()
    visible.is_displayed.return_value = True
    hidden = MagicMock()
    hidden.is_displayed.return_value = False
    driver.find_elements.return_value = [hidden, visible]
    with patch.object(tachiyomi, "detect_viewer_kind", return_value="legacy"):
        assert tachiyomi.get_visible_canvas(driver) is visible


def test_get_page_counter_publus():
    driver = MagicMock()

    class FakeWait:
        def __init__(self, *a, **k):
            pass

        def until(self, method):
            return method(driver)

    with patch.object(tachiyomi, "detect_viewer_kind", return_value="publus"):
        with patch.object(tachiyomi, "WebDriverWait", FakeWait):
            driver.execute_script.return_value = [3, 16]
            assert tachiyomi.get_page_counter(driver, timeout=1) == (3, 16)


def test_is_end_of_book_publus():
    driver = MagicMock()
    with patch.object(tachiyomi, "detect_viewer_kind", return_value="publus"):
        driver.execute_script.return_value = True
        assert tachiyomi.is_end_of_book(driver) is True
        driver.execute_script.assert_called_once_with(tachiyomi._PUBLUS_END_OF_BOOK_JS)


def test_is_end_of_book_legacy():
    driver = MagicMock()
    el = MagicMock()
    el.is_displayed.return_value = True
    driver.find_elements.return_value = [el]
    with patch.object(tachiyomi, "detect_viewer_kind", return_value="legacy"):
        assert tachiyomi.is_end_of_book(driver) is True
