"""get_tachiyomi のタイムアウト短縮・最終ページ即時判定のテスト。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import utils.get_tachiyomi as tachiyomi


def test_capture_skips_long_endofbook_wait(tmp_path, monkeypatch):
    """endOfBook は WebDriverWait(30) せず find_elements で即判定する。"""
    monkeypatch.setattr(tachiyomi, "chromedriver_path", lambda: "fake")

    driver = MagicMock()
    driver.find_elements.return_value = []
    driver.page_source = "<html></html>"
    from selenium.common.exceptions import TimeoutException

    wait_calls = []

    class FakeWait:
        def __init__(self, drv, timeout):
            wait_calls.append(timeout)
            self.timeout = timeout

        def until(self, method):
            if self.timeout == 12:
                return MagicMock()  # viewer / loading
            if self.timeout == 5:
                raise TimeoutException("canvas")
            return MagicMock()

        def until_not(self, method):
            return True

    with patch.object(tachiyomi.webdriver, "Chrome", return_value=driver):
        with patch.object(tachiyomi, "WebDriverWait", FakeWait):
            with patch.object(tachiyomi, "ActionChains"):
                with patch.object(tachiyomi.os, "makedirs"):
                    with patch.object(tachiyomi, "save_page_source"):
                        with patch.object(
                            tachiyomi,
                            "get_page_counter",
                            return_value=(1, 2),
                        ):
                            result = tachiyomi.capture_all_tachiyomi_pages("https://example.com/t")

    assert result == []
    # 旧実装の endOfBook 用 30 秒待ちが残っていないこと
    assert 30 not in wait_calls
    driver.find_elements.assert_any_call(tachiyomi.By.ID, "endOfBook")
    driver.quit.assert_called()
    driver.set_page_load_timeout.assert_called_with(60)


def test_capture_quits_even_on_get_failure(monkeypatch):
    monkeypatch.setattr(tachiyomi, "chromedriver_path", lambda: "fake")
    driver = MagicMock()
    driver.get.side_effect = [None, RuntimeError("boom")]  # top ok, tachiyomi fail

    class FakeWait:
        def __init__(self, *a, **k):
            pass

        def until(self, method):
            raise tachiyomi.TimeoutException("age")

    with patch.object(tachiyomi.webdriver, "Chrome", return_value=driver):
        with patch.object(tachiyomi, "WebDriverWait", FakeWait):
            with patch.object(tachiyomi.os, "makedirs"):
                result = tachiyomi.capture_all_tachiyomi_pages("https://example.com/t")

    assert result == []
    driver.quit.assert_called()
