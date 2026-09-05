"""get_tachiyomi のタイムアウト短縮・最終ページ即時判定・Publus 対応のテスト。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import utils.get_tachiyomi as tachiyomi


def test_driver_get_with_retry_succeeds_after_transient_failure():
    driver = MagicMock()
    driver.get.side_effect = [RuntimeError("net"), None]
    with patch.object(tachiyomi.time, "sleep"):
        tachiyomi._driver_get_with_retry(driver, "https://example.com/t")
    assert driver.get.call_count == 2


def test_driver_get_with_retry_raises_after_exhausted():
    driver = MagicMock()
    driver.get.side_effect = RuntimeError("net")
    with patch.object(tachiyomi.time, "sleep"):
        with pytest.raises(RuntimeError, match="net"):
            tachiyomi._driver_get_with_retry(driver, "https://example.com/t")
    assert driver.get.call_count == tachiyomi._NAVIGATION_RETRIES


def test_wait_for_viewer_with_retry_legacy_waits_loading():
    driver = MagicMock()
    with patch.object(tachiyomi, "_handle_age_check", return_value=False):
        with patch.object(tachiyomi, "wait_for_viewer_ready", return_value="legacy") as ready_mock:
            with patch.object(tachiyomi, "WebDriverWait") as wait_cls:
                wait_inst = wait_cls.return_value
                tachiyomi._wait_for_viewer_with_retry(driver, timeout=5)
                wait_inst.until_not.assert_called_once()
    assert ready_mock.call_count == 1


def test_wait_for_viewer_with_retry_retries_on_timeout():
    driver = MagicMock()
    with patch.object(tachiyomi, "_handle_age_check", return_value=False):
        with patch.object(
            tachiyomi,
            "wait_for_viewer_ready",
            side_effect=[tachiyomi.TimeoutException(), "publus"],
        ) as ready_mock:
            with patch.object(tachiyomi, "WebDriverWait"):
                with patch.object(tachiyomi.time, "sleep"):
                    kind = tachiyomi._wait_for_viewer_with_retry(driver, timeout=5)
    assert kind == "publus"
    assert ready_mock.call_count == 2


def test_wait_for_viewer_with_retry_reloads_url_on_retry():
    driver = MagicMock()
    with patch.object(tachiyomi, "_handle_age_check", return_value=False):
        with patch.object(
            tachiyomi,
            "wait_for_viewer_ready",
            side_effect=[tachiyomi.TimeoutException(), "publus"],
        ):
            with patch.object(tachiyomi, "_driver_get_with_retry") as get_mock:
                with patch.object(tachiyomi.time, "sleep"):
                    kind = tachiyomi._wait_for_viewer_with_retry(
                        driver, timeout=5, url="https://example.com/t"
                    )
    assert kind == "publus"
    get_mock.assert_called_once_with(driver, "https://example.com/t")


def test_wait_for_viewer_with_retry_raises_when_retries_zero(monkeypatch):
    driver = MagicMock()
    monkeypatch.setattr(tachiyomi, "_NAVIGATION_RETRIES", 0)
    with pytest.raises(tachiyomi.TimeoutException, match="viewer wait failed"):
        tachiyomi._wait_for_viewer_with_retry(driver, timeout=5)


def test_is_age_check_url():
    assert tachiyomi._is_age_check_url("https://www.dmm.co.jp/age_check/") is True
    assert tachiyomi._is_age_check_url("https://age_check.dmm.co.jp/") is True
    assert tachiyomi._is_age_check_url("https://book.dmm.co.jp/product/1/x/tachiyomi/") is False
    assert tachiyomi._is_age_check_url(None) is False


def test_handle_age_check_skips_when_not_gate():
    driver = MagicMock()
    driver.current_url = "https://book.dmm.co.jp/product/1/x/tachiyomi/"
    driver.find_elements.return_value = []
    assert tachiyomi._handle_age_check(driver) is False


def test_handle_age_check_clicks_declared_yes():
    driver = MagicMock()
    driver.current_url = "https://www.dmm.co.jp/age_check/"
    driver.title = "年齢認証 - FANZA"
    button = MagicMock()
    calls = {"n": 0}

    class FakeWait:
        def __init__(self, *a, **k):
            pass

        def until(self, method):
            calls["n"] += 1
            if calls["n"] == 1:
                return button
            driver.current_url = "https://book.dmm.co.jp/product/1/x/tachiyomi/"
            return True

    with patch.object(tachiyomi, "WebDriverWait", FakeWait):
        with patch.object(tachiyomi, "_apply_age_check_cookie") as cookie_mock:
            assert tachiyomi._handle_age_check(driver) is True
    driver.execute_script.assert_called_once()
    cookie_mock.assert_called_once_with(driver)


def test_handle_age_check_returns_false_when_button_missing():
    driver = MagicMock()
    driver.current_url = "https://www.dmm.co.jp/age_check/"
    driver.title = "年齢認証 - FANZA"

    class FakeWait:
        def __init__(self, *a, **k):
            pass

        def until(self, method):
            raise tachiyomi.TimeoutException("no button")

    with patch.object(tachiyomi, "WebDriverWait", FakeWait):
        assert tachiyomi._handle_age_check(driver) is False


def test_handle_age_check_modal_via_elements():
    driver = MagicMock()
    driver.current_url = "https://book.dmm.co.jp/product/1/x/tachiyomi/"
    driver.find_elements.return_value = [MagicMock()]
    button = MagicMock()
    calls = {"n": 0}

    class FakeWait:
        def __init__(self, *a, **k):
            pass

        def until(self, method):
            calls["n"] += 1
            if calls["n"] == 1:
                return button
            return True

    with patch.object(tachiyomi, "WebDriverWait", FakeWait):
        with patch.object(tachiyomi, "_apply_age_check_cookie"):
            assert tachiyomi._handle_age_check(driver) is True


def test_age_gate_elements_present_swallows_errors():
    driver = MagicMock()
    driver.find_elements.side_effect = RuntimeError("dom")
    assert tachiyomi._age_gate_elements_present(driver) is False


def test_handle_age_check_leave_timeout_still_returns_true():
    driver = MagicMock()
    driver.current_url = "https://www.dmm.co.jp/age_check/"
    button = MagicMock()

    class FakeWait:
        def __init__(self, *a, **k):
            pass

        def until(self, method):
            if getattr(method, "__name__", "") == "<lambda>":
                raise tachiyomi.TimeoutException("still on age check")
            return button

    with patch.object(tachiyomi, "WebDriverWait", FakeWait):
        with patch.object(tachiyomi, "_apply_age_check_cookie") as cookie_mock:
            assert tachiyomi._handle_age_check(driver) is True
    cookie_mock.assert_called_once_with(driver)


def test_wait_for_viewer_reload_failure_is_logged():
    driver = MagicMock()
    with patch.object(tachiyomi, "_handle_age_check", return_value=False):
        with patch.object(
            tachiyomi,
            "wait_for_viewer_ready",
            side_effect=[tachiyomi.TimeoutException(), "publus"],
        ):
            with patch.object(
                tachiyomi,
                "_driver_get_with_retry",
                side_effect=RuntimeError("reload boom"),
            ):
                with patch.object(tachiyomi.time, "sleep"):
                    kind = tachiyomi._wait_for_viewer_with_retry(
                        driver, timeout=5, url="https://example.com/t"
                    )
    assert kind == "publus"


def test_apply_age_check_cookie_swallows_errors():
    driver = MagicMock()
    driver.add_cookie.side_effect = RuntimeError("cookie")
    tachiyomi._apply_age_check_cookie(driver)


def test_ensure_driver_reuses_unready_existing_driver():
    """driver はあるが _ready=False のとき create せず年齢確認だけ行う。"""
    session = tachiyomi.TachiyomiCaptureSession()
    driver = MagicMock()
    session._driver = driver
    session._ready = False
    with patch.object(tachiyomi, "create_chrome_driver") as create_mock:
        with patch.object(session, "_verify_age") as verify:
            assert session._ensure_driver() is driver
    create_mock.assert_not_called()
    verify.assert_called_once_with(driver)
    assert session._ready is True


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


def test_session_reuses_driver_across_captures():
    driver = MagicMock()
    driver.page_source = "<html></html>"
    from selenium.common.exceptions import TimeoutException

    class FakeWait:
        def __init__(self, drv, timeout):
            self.timeout = timeout

        def until(self, method):
            if self.timeout == 20:
                return "publus"
            if self.timeout == 5:
                raise TimeoutException("canvas")
            return [1, 2]

        def until_not(self, method):
            return True

    with patch.object(tachiyomi, "create_chrome_driver", return_value=driver) as create:
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
                                ):
                                    with patch.object(
                                        tachiyomi,
                                        "get_page_counter",
                                        return_value=(1, 2),
                                    ):
                                        with patch.object(tachiyomi.time, "sleep"):
                                            with tachiyomi.TachiyomiCaptureSession() as session:
                                                session.capture("https://example.com/a")
                                                session.capture("https://example.com/b")

    assert create.call_count == 1
    assert quit_mock.call_count == 1
    urls = [c.args[0] for c in driver.get.call_args_list]
    assert urls.count(tachiyomi._DMM_TOP_URL) == 1
    assert urls.count("https://example.com/a") == 1
    assert urls.count("https://example.com/b") == 1


def test_driver_get_timeout_logs_warning_and_recycles():
    driver = MagicMock()
    driver.get.side_effect = [None] + [tachiyomi.TimeoutException()] * tachiyomi._NAVIGATION_RETRIES

    class FakeWait:
        def __init__(self, *a, **k):
            pass

        def until(self, method):
            raise tachiyomi.TimeoutException("age")

    with patch.object(tachiyomi, "create_chrome_driver", return_value=driver):
        with patch.object(tachiyomi, "quit_chrome_driver") as quit_mock:
            with patch.object(tachiyomi, "WebDriverWait", FakeWait):
                with patch.object(tachiyomi.os, "makedirs"):
                    with patch.object(tachiyomi.time, "sleep"):
                        with patch.object(tachiyomi.logging, "warning") as warn:
                            result = tachiyomi.capture_all_tachiyomi_pages(
                                "https://example.com/t"
                            )

    assert result == []
    assert any("driver.get 失敗" in str(c) for c in warn.call_args_list)
    assert quit_mock.called


def test_should_recycle_driver_detects_hangs():
    from selenium.common.exceptions import InvalidSessionIdException

    assert tachiyomi._should_recycle_driver(InvalidSessionIdException()) is True
    assert tachiyomi._should_recycle_driver(tachiyomi.TimeoutException()) is True
    assert tachiyomi._should_recycle_driver(RuntimeError("HTTPConnectionPool localhost")) is True
    assert tachiyomi._should_recycle_driver(RuntimeError("boom")) is False


def test_capture_outer_exception_recycles_and_returns_empty():
    session = tachiyomi.TachiyomiCaptureSession()
    session._driver = MagicMock()
    with patch.object(session, "_capture_once", side_effect=RuntimeError("chrome not reachable")):
        with patch.object(session, "_recycle") as recycle:
            assert session.capture("https://example.com/t") == []
            recycle.assert_called_once()


def test_capture_outer_exception_keeps_driver_when_not_hang():
    session = tachiyomi.TachiyomiCaptureSession()
    with patch.object(session, "_capture_once", side_effect=RuntimeError("boom")):
        with patch.object(session, "_recycle") as recycle:
            assert session.capture("https://example.com/t") == []
            recycle.assert_not_called()


def test_capture_all_uses_provided_session():
    session = MagicMock()
    session.capture.return_value = ["x.webp"]
    assert tachiyomi.capture_all_tachiyomi_pages("u", session=session) == ["x.webp"]
    session.capture.assert_called_once_with("u")


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
