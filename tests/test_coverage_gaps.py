"""C1 100% 向け: 変更モジュールの未実行分岐を埋める。"""

from __future__ import annotations

import io
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from selenium.common.exceptions import NoSuchElementException, TimeoutException

import run as run_mod
import utils.get_tachiyomi as tachiyomi
from db.trn_dmm_items_repository import (
    insert_dmm_item,
    insert_dmm_item_supabase2,
    insert_dmm_item_supabase3,
    parse_price,
)
from scripts.process import backfill_tachiyomi as bf
from utils.run_lock import RunLock, clear_stale_lock, pid_alive


class TestGetTachiyomiGaps:
    def test_save_page_source(self, tmp_path: Path):
        driver = MagicMock()
        driver.page_source = "<html>hi</html>"
        log_dir = str(tmp_path)
        with patch.object(tachiyomi, "print"):
            tachiyomi.save_page_source(driver, 3, log_dir=log_dir)
        assert (tmp_path / "page_source_3.html").read_text(encoding="utf-8") == "<html>hi</html>"

    def test_detect_viewer_kind(self):
        driver = MagicMock()
        driver.execute_script.return_value = "legacy"
        assert tachiyomi.detect_viewer_kind(driver) == "legacy"

    def test_get_visible_canvas_publus_missing_raises(self):
        driver = MagicMock()
        driver.execute_script.return_value = None
        with patch.object(tachiyomi, "detect_viewer_kind", return_value="publus"):
            with pytest.raises(Exception, match="Publus"):
                tachiyomi.get_visible_canvas(driver)

    def test_get_visible_canvas_legacy_stale_element(self):
        driver = MagicMock()
        bad = MagicMock()
        bad.is_displayed.side_effect = RuntimeError("stale")
        driver.find_elements.return_value = [bad]
        with patch.object(tachiyomi, "detect_viewer_kind", return_value="legacy"):
            with pytest.raises(Exception, match="表示中"):
                tachiyomi.get_visible_canvas(driver)

    def test_get_page_counter_legacy_no_element(self):
        driver = MagicMock()

        class FakeWait:
            def __init__(self, *a, **k):
                pass

            def until(self, method):
                return method(driver)

        with patch.object(tachiyomi, "detect_viewer_kind", return_value="legacy"):
            driver.find_elements.return_value = []
            with patch.object(tachiyomi, "WebDriverWait", FakeWait):
                with patch("builtins.open", create=True):
                    assert tachiyomi.get_page_counter(driver, timeout=1) == (1, 50)

    def test_get_page_counter_legacy_bad_text(self):
        driver = MagicMock()
        elem = MagicMock()
        elem.text = "bad"

        class FakeWait:
            def __init__(self, *a, **k):
                pass

            def until(self, method):
                return method(driver)

        with patch.object(tachiyomi, "detect_viewer_kind", return_value="legacy"):
            driver.find_elements.return_value = [elem]
            with patch.object(tachiyomi, "WebDriverWait", FakeWait):
                with patch("builtins.open", create=True):
                    assert tachiyomi.get_page_counter(driver, timeout=1) == (1, 50)

    def test_capture_once_end_of_book_before_canvas(self):
        driver = MagicMock()
        session = tachiyomi.TachiyomiCaptureSession()
        session._driver = driver
        session._ready = True

        class FakeWait:
            def __init__(self, drv, timeout):
                self.timeout = timeout

            def until(self, method):
                if self.timeout == 20:
                    return "publus"
                return [1, 2]

            def until_not(self, method):
                return True

        with patch.object(tachiyomi, "WebDriverWait", FakeWait):
            with patch.object(tachiyomi, "ActionChains"):
                with patch.object(tachiyomi.os, "makedirs"):
                    with patch.object(tachiyomi, "is_end_of_book", return_value=True):
                        with patch.object(tachiyomi, "get_page_counter", return_value=(1, 5)):
                            with patch.object(tachiyomi.time, "sleep"):
                                assert session._capture_once("https://example.com/t") == []

    def test_capture_once_multi_page_navigation(self, tmp_path: Path):
        driver = MagicMock()
        canvas = MagicMock()
        session = tachiyomi.TachiyomiCaptureSession()
        session._driver = driver
        session._ready = True
        actions = MagicMock()

        class FakeWait:
            def __init__(self, drv, timeout):
                self.timeout = timeout

            def until(self, method):
                if self.timeout == 20:
                    return "publus"
                if self.timeout == 5:
                    return canvas
                return [1, 3]

            def until_not(self, method):
                return True

        fake_image = MagicMock()
        fake_image.__enter__ = MagicMock(return_value=fake_image)
        fake_image.__exit__ = MagicMock(return_value=False)
        page_counter_calls = iter([(0, 3), (1, 3)])

        with patch.object(tachiyomi, "WebDriverWait", FakeWait):
            with patch.object(tachiyomi, "ActionChains", return_value=actions):
                with patch.object(tachiyomi, "is_end_of_book", return_value=False):
                    with patch.object(
                        tachiyomi,
                        "get_page_counter",
                        side_effect=lambda *a, **k: next(page_counter_calls),
                    ):
                        with patch.object(tachiyomi.time, "sleep"):
                            with patch.object(tachiyomi.os, "makedirs"):
                                with patch.object(tachiyomi.os.path, "dirname", return_value=str(tmp_path)):
                                    with patch.object(tachiyomi.os.path, "abspath", return_value=str(tmp_path)):
                                        with patch.object(tachiyomi.Image, "open", return_value=fake_image):
                                            with patch.object(tachiyomi.os, "remove"):
                                                paths = session._capture_once("https://example.com/t")
        assert len(paths) >= 1
        assert actions.send_keys.call_count >= 1

    def test_get_page_counter_legacy(self):
        driver = MagicMock()
        elem = MagicMock()
        elem.text = "4/12"

        class FakeWait:
            def __init__(self, *a, **k):
                pass

            def until(self, method):
                return method(driver)

        with patch.object(tachiyomi, "detect_viewer_kind", return_value="legacy"):
            driver.find_elements.return_value = [elem]
            with patch.object(tachiyomi, "WebDriverWait", FakeWait):
                assert tachiyomi.get_page_counter(driver, timeout=1) == (4, 12)

    def test_get_page_counter_failure_fallback(self, tmp_path: Path):
        driver = MagicMock()
        driver.page_source = "<html>fail</html>"

        class FakeWait:
            def __init__(self, *a, **k):
                pass

            def until(self, method):
                raise TimeoutException("counter")

        with patch.object(tachiyomi, "WebDriverWait", FakeWait):
            with patch.object(tachiyomi, "open", create=True) as mock_open:
                mock_open.return_value.__enter__.return_value = MagicMock()
                assert tachiyomi.get_page_counter(driver) == (1, 50)
        driver.save_screenshot.assert_called_once_with("debug_get_page_counter.png")

    def test_verify_age_clicks_button(self):
        session = tachiyomi.TachiyomiCaptureSession()
        driver = MagicMock()
        button = MagicMock()

        class FakeWait:
            def __init__(self, *a, **k):
                pass

            def until(self, method):
                return button

        with patch.object(tachiyomi, "WebDriverWait", FakeWait):
            with patch.object(tachiyomi.time, "sleep"):
                session._verify_age(driver)
        driver.execute_script.assert_called_once()

    def test_capture_once_legacy_viewer_and_page_save(self, tmp_path: Path):
        driver = MagicMock()
        driver.page_source = "<html></html>"
        canvas = MagicMock()
        canvas.screenshot = MagicMock()

        class FakeWait:
            def __init__(self, drv, timeout):
                self.timeout = timeout

            def until(self, method):
                if self.timeout == 20:
                    return "legacy"
                if self.timeout == 5:
                    return canvas
                if self.timeout == 10:
                    return [1, 1]
                return MagicMock()

            def until_not(self, method):
                return True

        session = tachiyomi.TachiyomiCaptureSession()
        session._driver = driver
        session._ready = True

        fake_image = MagicMock()
        fake_image.__enter__ = MagicMock(return_value=fake_image)
        fake_image.__exit__ = MagicMock(return_value=False)

        with patch.object(tachiyomi, "WebDriverWait", FakeWait):
            with patch.object(tachiyomi, "ActionChains"):
                with patch.object(tachiyomi, "is_end_of_book", side_effect=[False, True]):
                    with patch.object(tachiyomi, "get_page_counter", return_value=(1, 1)):
                        with patch.object(tachiyomi.time, "sleep"):
                            with patch.object(tachiyomi.os, "makedirs"):
                                with patch.object(tachiyomi.os.path, "dirname", return_value=str(tmp_path)):
                                    with patch.object(tachiyomi.os.path, "abspath", return_value=str(tmp_path)):
                                        with patch.object(tachiyomi.Image, "open", return_value=fake_image):
                                            with patch.object(tachiyomi.os, "remove"):
                                                paths = session._capture_once("https://example.com/t")
        assert len(paths) == 1
        assert paths[0].endswith(".webp")

    def test_capture_once_viewer_wait_fails_saves_source(self):
        driver = MagicMock()
        session = tachiyomi.TachiyomiCaptureSession()
        session._driver = driver
        session._ready = True

        class FakeWait:
            def __init__(self, *a, **k):
                pass

            def until(self, method):
                raise TimeoutException("viewer")

            def until_not(self, method):
                return True

        with patch.object(tachiyomi, "WebDriverWait", FakeWait):
            with patch.object(tachiyomi.os, "makedirs"):
                with patch.object(tachiyomi, "save_page_source") as save:
                    assert session._capture_once("https://example.com/t") == []
        save.assert_called_once()

    def test_capture_once_canvas_timeout_in_loop(self):
        driver = MagicMock()
        session = tachiyomi.TachiyomiCaptureSession()
        session._driver = driver
        session._ready = True

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

        with patch.object(tachiyomi, "WebDriverWait", FakeWait):
            with patch.object(tachiyomi, "ActionChains"):
                with patch.object(tachiyomi.os, "makedirs"):
                    with patch.object(tachiyomi, "is_end_of_book", return_value=False):
                        with patch.object(tachiyomi, "get_page_counter", return_value=(1, 5)):
                            with patch.object(tachiyomi.time, "sleep"):
                                with patch.object(tachiyomi, "save_page_source") as save:
                                    assert session._capture_once("https://example.com/t") == []
        save.assert_called_once()

    def test_capture_once_unexpected_error_recycles(self):
        driver = MagicMock()
        session = tachiyomi.TachiyomiCaptureSession()
        session._driver = driver
        session._ready = True

        class FakeWait:
            def __init__(self, drv, timeout):
                self.timeout = timeout

            def until(self, method):
                if self.timeout == 20:
                    return "publus"
                if self.timeout == 5:
                    raise RuntimeError("invalid session id")
                return [1, 2]

            def until_not(self, method):
                return True

        with patch.object(tachiyomi, "WebDriverWait", FakeWait):
            with patch.object(tachiyomi, "ActionChains"):
                with patch.object(tachiyomi.os, "makedirs"):
                    with patch.object(tachiyomi, "is_end_of_book", return_value=False):
                        with patch.object(tachiyomi, "get_page_counter", return_value=(1, 5)):
                            with patch.object(tachiyomi.time, "sleep"):
                                with patch.object(tachiyomi, "save_page_source"):
                                    with patch.object(session, "_recycle") as recycle:
                                        assert session._capture_once("https://example.com/t") == []
        recycle.assert_called_once()

    def test_ensure_driver_failure_recycles(self):
        session = tachiyomi.TachiyomiCaptureSession()
        with patch.object(
            tachiyomi,
            "create_chrome_driver",
            side_effect=RuntimeError("session not created"),
        ):
            with patch.object(tachiyomi.os, "makedirs"):
                with patch.object(session, "_recycle") as recycle:
                    assert session._capture_once("https://example.com/t") == []
        recycle.assert_called_once()


class TestRunLockGaps:
    def test_pid_alive_windows_getexitcode_fails(self, monkeypatch):
        import ctypes

        monkeypatch.setattr("utils.run_lock.sys.platform", "win32")
        handle = MagicMock()

        class FakeKernel32:
            def OpenProcess(self, *a, **k):
                return handle

            def GetExitCodeProcess(self, h, ref):
                return 0

            def CloseHandle(self, h):
                pass

        monkeypatch.setattr(ctypes.windll, "kernel32", FakeKernel32())
        assert pid_alive(12345) is False

    def test_pid_alive_non_windows_dead(self, monkeypatch):
        monkeypatch.setattr("utils.run_lock.sys.platform", "linux")

        def kill(pid, sig):
            raise ProcessLookupError(pid)

        monkeypatch.setattr("utils.run_lock.os.kill", kill)
        assert pid_alive(99999) is False

    def test_pid_alive_non_windows_permission(self, monkeypatch):
        monkeypatch.setattr("utils.run_lock.sys.platform", "linux")

        def kill(pid, sig):
            raise PermissionError()

        monkeypatch.setattr("utils.run_lock.os.kill", kill)
        assert pid_alive(99999) is True

    def test_pid_alive_non_windows_alive(self, monkeypatch):
        monkeypatch.setattr("utils.run_lock.sys.platform", "linux")
        monkeypatch.setattr("utils.run_lock.os.kill", lambda pid, sig: None)
        assert pid_alive(99999) is True

    def test_clear_stale_lock_unlink_oserror(self, tmp_path: Path):
        p = tmp_path / "stuck.lock"
        p.write_text("999999999 stale\n", encoding="utf-8")
        with patch.object(Path, "unlink", side_effect=OSError("busy")):
            assert clear_stale_lock(p) is False

    def test_run_lock_release_unlink_oserror(self, tmp_path: Path):
        lock_path = tmp_path / "rel.lock"
        lock = RunLock(lock_path)
        lock.acquire()
        with patch.object(Path, "unlink", side_effect=OSError("busy")):
            lock.release()
        assert lock._held is False


class TestTrnDmmItemsRepositoryGaps:
    def test_parse_price(self):
        assert parse_price(None) is None
        assert parse_price("") is None
        assert parse_price("abc") is None
        assert parse_price("1,980円") == 1980

    def test_insert_logs_img_fail(self):
        client = MagicMock()
        client.table.return_value.select.return_value.eq.return_value.execute.return_value = (
            MagicMock(data=[])
        )
        client.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{"id": 1}]
        )
        upload = MagicMock(side_effect=[None, "u2"])
        item = {
            "content_id": "cid1",
            "title": "t",
            "URL": "https://example.com/i",
            "tachiyomi": {"URL": "https://example.com/t"},
            "iteminfo": {},
            "prices": {},
            "imageURL": {},
            "sampleImageURL": {},
        }
        with patch(
            "db.trn_dmm_items_repository.generate_content",
            return_value={"auto_comment": "", "auto_summary": "", "auto_point": ""},
        ):
            with patch(
                "db.trn_dmm_items_repository.execute_with_retry",
                side_effect=lambda builder: builder().execute(),
            ):
                from db.trn_dmm_items_repository import _insert_dmm_item

                ok = _insert_dmm_item(
                    item,
                    ["a.webp", "b.webp"],
                    None,
                    "FANZA",
                    "ebook",
                    "comic",
                    supabase_client=client,
                    upload_local_image_to_s3_fn=upload,
                    coerce_empty_image_urls=False,
                )
        assert ok is True
        payload = client.table.return_value.insert.call_args[0][0]
        assert payload["image_large_url"] is None or "large" not in str(payload)

    def test_public_insert_wrappers(self):
        item = {"content_id": "x"}
        with patch(
            "db.trn_dmm_items_repository._insert_dmm_item", return_value=True
        ) as inner:
            assert insert_dmm_item(item, [], None, "s", "sv", "f") is True
            assert insert_dmm_item_supabase2(item, [], None, "s", "sv", "f") is True
            assert insert_dmm_item_supabase3(item, [], None, "s", "sv", "f") is True
        assert inner.call_count == 3
        assert inner.call_args_list[0].kwargs["coerce_empty_image_urls"] is True
        assert inner.call_args_list[1].kwargs["coerce_empty_image_urls"] is False
        assert inner.call_args_list[2].kwargs["coerce_empty_image_urls"] is False


class TestBackfillTachiyomiGaps:
    def test_resolve_db_target_default(self):
        client, upload, bucket = bf.resolve_db_target("default")
        assert client is bf.supabase
        assert upload is bf.upload_local_image_to_s3
        assert bucket == bf.S3_BUCKET

    def test_resolve_db_target_supabase2_missing(self):
        with patch.object(bf, "supabase2", None):
            with pytest.raises(RuntimeError, match="SUPABASE_URL2"):
                bf.resolve_db_target("supabase2")

    def test_resolve_db_target_supabase3_missing(self):
        with patch.object(bf, "supabase3", None):
            with pytest.raises(RuntimeError, match="SUPABASE_URL3"):
                bf.resolve_db_target("supabase3")

    def test_resolve_db_target_supabase2_ok(self):
        client = MagicMock()
        with patch.object(bf, "supabase2", client):
            c, upload, bucket = bf.resolve_db_target("supabase2")
        assert c is client
        assert upload is bf.upload_local_image_to_s3
        assert bucket == bf.S3_BUCKET

    def test_resolve_db_target_supabase3_ok(self):
        client = MagicMock()
        with patch.object(bf, "supabase3", client):
            c, upload, bucket = bf.resolve_db_target("supabase3")
        assert c is client
        assert upload is bf.upload_local_image_to_s3_bucket3
        assert bucket == bf.S3_BUCKET_3

    def test_fetch_pending_tachiyomi_rows(self):
        client = MagicMock()
        client.table.return_value.select.return_value.not_.is_.return_value = (
            client.table.return_value.select.return_value
        )
        chain = client.table.return_value.select.return_value
        chain.neq.return_value = chain
        chain.or_.return_value = chain
        chain.order.return_value = chain
        chain.range.return_value = chain
        chain.eq.return_value = chain
        with patch.object(
            bf,
            "execute_with_retry",
            return_value=MagicMock(data=[{"content_id": "a"}]),
        ):
            rows = bf.fetch_pending_tachiyomi_rows(
                client, limit=5, content_id="cid", offset=2
            )
        assert rows == [{"content_id": "a"}]
        chain.eq.assert_called_once_with("content_id", "cid")

    def test_upload_tachiyomi_paths_img_fail(self):
        upload = MagicMock(side_effect=["ok", None])
        with patch.object(bf, "call_with_retry", side_effect=lambda fn, **k: fn()):
            count = bf.upload_tachiyomi_paths(
                ["a", "b"],
                content_id="cid",
                floor="comic",
                upload_fn=upload,
            )
        assert count == 1

    def test_cleanup_local_files_file_not_found(self):
        with patch.object(bf.os, "remove", side_effect=FileNotFoundError()):
            bf.cleanup_local_files(["/tmp/missing.webp"])

    def test_cleanup_local_files_oserror(self):
        with patch.object(bf.os, "remove", side_effect=OSError("busy")):
            bf.cleanup_local_files(["/tmp/x.webp"])

    def test_process_one_row_sync_update_fail(self):
        row = {
            "content_id": "c",
            "tachiyomi_url": "https://x",
            "floor": "comic",
            "title": "t",
        }
        with patch.object(bf, "count_objects_under_prefix", return_value=2):
            with patch.object(bf, "update_tachiyomi_fields", return_value=False):
                status = bf.process_one_row(
                    row,
                    client=MagicMock(),
                    upload_fn=MagicMock(),
                    bucket="b",
                    dry_run=False,
                )
        assert status == "failed"

    def test_process_one_row_skip_missing_fields(self):
        assert bf.process_one_row({}, client=MagicMock(), upload_fn=MagicMock(), bucket="b", dry_run=True) == "skipped"

    def test_process_one_row_skip_no_floor(self):
        row = {"content_id": "c", "tachiyomi_url": "https://x", "floor": ""}
        assert (
            bf.process_one_row(
                row, client=MagicMock(), upload_fn=MagicMock(), bucket="b", dry_run=True
            )
            == "skipped"
        )

    def test_process_one_row_upload_zero_fails(self):
        row = {
            "content_id": "c",
            "tachiyomi_url": "https://x",
            "floor": "comic",
            "title": "t",
        }
        with patch.object(bf, "count_objects_under_prefix", return_value=0):
            with patch.object(bf, "capture_all_tachiyomi_pages", return_value=["p.webp"]):
                with patch.object(bf, "upload_tachiyomi_paths", return_value=0):
                    with patch.object(bf, "record_capture_failure") as fail:
                        with patch.object(bf, "cleanup_local_files"):
                            status = bf.process_one_row(
                                row,
                                client=MagicMock(),
                                upload_fn=MagicMock(),
                                bucket="b",
                                dry_run=False,
                            )
        assert status == "failed"
        fail.assert_called_once()

    def test_process_one_row_update_fail_after_upload(self):
        row = {
            "content_id": "c",
            "tachiyomi_url": "https://x",
            "floor": "comic",
            "title": "t",
        }
        with patch.object(bf, "count_objects_under_prefix", return_value=0):
            with patch.object(bf, "capture_all_tachiyomi_pages", return_value=["p.webp"]):
                with patch.object(bf, "upload_tachiyomi_paths", return_value=1):
                    with patch.object(bf, "update_tachiyomi_fields", return_value=False):
                        with patch.object(bf, "cleanup_local_files"):
                            status = bf.process_one_row(
                                row,
                                client=MagicMock(),
                                upload_fn=MagicMock(),
                                bucket="b",
                                dry_run=False,
                            )
        assert status == "failed"

    def test_run_backfill_marks_error_on_failed_status(self):
        rows = [{"content_id": "c1", "floor": "comic", "tachiyomi_url": "https://x", "title": "t"}]
        with patch.object(bf, "resolve_db_target", return_value=(MagicMock(), MagicMock(), "b")):
            with patch.object(bf, "fetch_pending_tachiyomi_rows", return_value=rows):
                with patch.object(bf, "process_one_row", return_value="failed"):
                    with patch.object(bf, "TachiyomiCaptureSession") as sess_cls:
                        sess_cls.return_value.__enter__.return_value = MagicMock()
                        code = bf.run_backfill(db_name="default", limit=1, dry_run=False)
        assert code == 1

    def test_run_backfill_row_exception_and_fail_count_update_fail(self):
        rows = [{"content_id": "c1", "tachiyomi_capture_fail_count": 0}]

        def boom(*a, **k):
            raise RuntimeError("boom")

        with patch.object(bf, "resolve_db_target", return_value=(MagicMock(), MagicMock(), "b")):
            with patch.object(bf, "fetch_pending_tachiyomi_rows", return_value=rows):
                with patch.object(bf, "process_one_row", side_effect=boom):
                    with patch.object(
                        bf, "record_capture_failure", side_effect=RuntimeError("db")
                    ):
                        with patch.object(bf, "TachiyomiCaptureSession") as sess_cls:
                            sess_cls.return_value.__enter__.return_value = MagicMock()
                            code = bf.run_backfill(db_name="default", limit=1, dry_run=False)
        assert code == 1

    def test_main_invalid_limit(self):
        with pytest.raises(SystemExit) as exc:
            bf.main(["--limit", "0"])
        assert exc.value.code == 2

    def test_main_invalid_offset(self):
        with pytest.raises(SystemExit) as exc:
            bf.main(["--offset", "-1"])
        assert exc.value.code == 2

    def test_main_success(self):
        with patch.object(bf, "run_backfill", return_value=0):
            with pytest.raises(SystemExit) as exc:
                bf.main(["--limit", "1"])
        assert exc.value.code == 0


class TestRunGaps:
    def test_resolve_lock_paths_no_phase_no_script(self):
        paths = run_mod.resolve_lock_paths(None, None)
        assert paths[0].name == "run.lock"

    def test_resolve_lock_paths_unknown_script(self):
        paths = run_mod.resolve_lock_paths(None, "scripts/manual/foo.py")
        assert paths[0].name == "run.lock"

    def test_resolve_scripts_unknown_script(self):
        tasks = run_mod.load_tasks()
        with pytest.raises(SystemExit, match="未定義"):
            run_mod.resolve_scripts(tasks, None, "scripts/no/such/script.py")

    def test_resolve_scripts_all_phases(self):
        tasks = run_mod.load_tasks()
        entries = run_mod.resolve_scripts(tasks, "all", None)
        phases = {e["phase"] for e in entries}
        assert phases == {"collect", "process"}

    def test_resolve_scripts_unknown_phase(self):
        tasks = {"phases": {}}
        with pytest.raises(SystemExit, match="未知"):
            run_mod.resolve_scripts(tasks, "bogus", None)

    def test_resolve_scripts_fallback_to_process(self):
        tasks = {
            "phases": {
                "process_main_weekly": {
                    "scripts": [{"path": "scripts/only/weekly.py"}],
                },
                "process": {
                    "scripts": [{"path": "scripts/only/weekly.py", "name": "fb"}],
                },
            }
        }
        entries = run_mod.resolve_scripts(tasks, None, "scripts/only/weekly.py")
        assert entries[0]["phase"] == "process"

    def test_run_script_returns_code_on_failure_without_continue(self, tmp_path: Path):
        entry = {"path": "scripts/process/update_items.py", "log": str(tmp_path / "f.log")}
        proc = MagicMock()
        proc.stdout = io.StringIO("err\n")
        proc.wait.return_value = 7
        with patch.object(run_mod.subprocess, "Popen", return_value=proc):
            with patch.object(run_mod, "should_echo_child_output", return_value=False):
                with patch.object(run_mod.logger, "info"):
                    with patch.object(run_mod.logger, "error"):
                        code = run_mod.run_script(entry, "python", False, 1, 1)
        assert code == 7

    def test_list_scripts(self, capsys):
        tasks = run_mod.load_tasks()
        run_mod.list_scripts(tasks)
        out = capsys.readouterr().out
        assert "[collect]" in out
        assert "scripts/" in out

    def test_main_list(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["run.py", "--list"])
        with patch.object(run_mod, "setup_logger"):
            run_mod.main()
        # no SystemExit

    def test_main_no_entries(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["run.py", "--phase", "collect"])
        with patch.object(run_mod, "setup_logger"):
            with patch.object(run_mod, "wait_for_peer_locks", return_value=False):
                with patch.object(run_mod, "resolve_scripts", return_value=[]):
                    with patch.object(run_mod, "LockSet") as lock_cls:
                        run_mod.main()
        lock_cls.assert_not_called()

    def test_main_lock_acquire_fail(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["run.py", "--phase", "process_main"])
        with patch.object(run_mod, "setup_logger"):
            with patch.object(run_mod, "wait_for_peer_locks", return_value=False):
                with patch.object(
                    run_mod,
                    "resolve_scripts",
                    return_value=[{"path": "scripts/process/update_items.py", "phase": "process_main"}],
                ):
                    with patch.object(run_mod, "LockSet") as lock_cls:
                        lock_cls.return_value.acquire.side_effect = run_mod.RunLockError("busy")
                        with patch.object(run_mod.logger, "error"):
                            with pytest.raises(SystemExit) as exc:
                                run_mod.main()
        assert exc.value.code == 2

    def test_main_success_path(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["run.py", "--phase", "process_main", "--continue-on-error"])
        entry = {"path": "scripts/process/update_items.py", "phase": "process_main", "name": "u"}
        with patch.object(run_mod, "setup_logger"):
            with patch.object(run_mod, "wait_for_peer_locks", return_value=True):
                with patch.object(run_mod, "apply_process_stagger"):
                    with patch.object(run_mod, "resolve_scripts", return_value=[entry]):
                        with patch.object(run_mod, "LockSet") as lock_cls:
                            lock_cls.return_value.acquire.return_value = None
                            with patch.object(run_mod, "run_script", return_value=0):
                                with patch.object(run_mod.logger, "info"):
                                    with pytest.raises(SystemExit) as exc:
                                        run_mod.main()
        assert exc.value.code == 0
        lock_cls.return_value.release.assert_called_once()

    def test_main_script_failure_exits(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["run.py", "--phase", "process_main"])
        entry = {"path": "scripts/process/update_items.py", "phase": "process_main"}
        with patch.object(run_mod, "setup_logger"):
            with patch.object(run_mod, "wait_for_peer_locks", return_value=False):
                with patch.object(run_mod, "resolve_scripts", return_value=[entry]):
                    with patch.object(run_mod, "LockSet") as lock_cls:
                        lock_cls.return_value.acquire.return_value = None
                        with patch.object(run_mod, "run_script", return_value=3):
                            with patch.object(run_mod.logger, "info"):
                                with patch.object(run_mod.logger, "error"):
                                    with pytest.raises(SystemExit) as exc:
                                        run_mod.main()
        assert exc.value.code == 3

    def test_main_continue_on_error_partial_fail(self, monkeypatch):
        monkeypatch.setattr(
            sys, "argv", ["run.py", "--phase", "process_main", "--continue-on-error"]
        )
        entries = [
            {"path": "scripts/process/update_items.py", "phase": "process_main"},
            {"path": "scripts/process/create_ai_review.py", "phase": "process_main"},
        ]
        with patch.object(run_mod, "setup_logger"):
            with patch.object(run_mod, "wait_for_peer_locks", return_value=False):
                with patch.object(run_mod, "resolve_scripts", return_value=entries):
                    with patch.object(run_mod, "LockSet") as lock_cls:
                        lock_cls.return_value.acquire.return_value = None
                        with patch.object(run_mod, "run_script", side_effect=[1, 0]):
                            with patch.object(run_mod.logger, "info"):
                                with patch.object(run_mod.logger, "warning") as warn:
                                    with pytest.raises(SystemExit) as exc:
                                        run_mod.main()
        assert exc.value.code == 1
        assert any("失敗あり" in str(c) for c in warn.call_args_list)

    def test_main_no_lock_skips_peer_wait(self, monkeypatch):
        monkeypatch.setattr(
            sys, "argv", ["run.py", "--phase", "process_main", "--no-lock", "--continue-on-error"]
        )
        entry = {"path": "scripts/process/update_items.py", "phase": "process_main"}
        with patch.object(run_mod, "setup_logger"):
            with patch.object(run_mod, "wait_for_peer_locks") as wait:
                with patch.object(run_mod, "resolve_scripts", return_value=[entry]):
                    with patch.object(run_mod, "run_script", return_value=0):
                        with patch.object(run_mod.logger, "info"):
                            with pytest.raises(SystemExit):
                                run_mod.main()
        wait.assert_not_called()

    def test_resolve_scripts_requires_phase_or_script(self):
        with pytest.raises(SystemExit, match="--phase"):
            run_mod.resolve_scripts({"phases": {}}, None, None)


class TestC1BranchGaps:
    def test_extract_x_account_skips_blocklisted_usernames(self):
        from bs4 import BeautifulSoup

        import dmm.dmm_actress_api as api

        html = """
        <html><body>
          <a href="https://x.com/intent/tweet">share</a>
          <a href="https://x.com/home">home</a>
          <a href="https://x.com/">empty</a>
          <a href="https://x.com/valid_user">ok</a>
        </body></html>
        """
        soup = BeautifulSoup(html, "html.parser")
        assert api._extract_x_account(soup) == "valid_user"

    def test_map_api_actress_image_url_not_dict(self):
        import dmm.dmm_actress_api as api

        record = api.map_api_actress_to_record(
            {"id": "1", "name": "n", "imageURL": "not-a-dict"}
        )
        assert record["image_url"] is None

    def test_merge_scrape_skips_empty_values_and_zero_works(self):
        import dmm.dmm_actress_api as api

        record = {"actress_id": 1, "alias": "keep"}
        scrape = {"profile": "", "alias": "new", "career_text": None}
        with patch.object(api, "scrape_osusume_profile", return_value=scrape):
            with patch.object(api, "fetch_works_count", return_value=0):
                merged = api._merge_scrape_and_works(record, 1, session=MagicMock())
        assert merged["alias"] == "keep"
        assert "works_count" not in merged

    def test_fetch_pending_without_content_id_filter(self):
        client = MagicMock()
        chain = client.table.return_value.select.return_value
        chain.not_.is_.return_value = chain
        chain.neq.return_value = chain
        chain.or_.return_value = chain
        chain.order.return_value = chain
        chain.range.return_value = chain
        with patch.object(
            bf,
            "execute_with_retry",
            return_value=MagicMock(data=[]),
        ):
            bf.fetch_pending_tachiyomi_rows(client, limit=5, offset=0)
        chain.eq.assert_not_called()

    def test_process_one_row_sync_dry_run_skips_update(self):
        row = {
            "content_id": "c",
            "tachiyomi_url": "https://x",
            "floor": "comic",
            "title": "t",
        }
        with patch.object(bf, "count_objects_under_prefix", return_value=2):
            with patch.object(bf, "update_tachiyomi_fields") as update:
                status = bf.process_one_row(
                    row,
                    client=MagicMock(),
                    upload_fn=MagicMock(),
                    bucket="b",
                    dry_run=True,
                )
        assert status == "synced"
        update.assert_not_called()

    def test_run_backfill_exception_skips_fail_count_when_dry_run(self):
        rows = [{"content_id": "c1", "tachiyomi_capture_fail_count": 0}]

        with patch.object(bf, "resolve_db_target", return_value=(MagicMock(), MagicMock(), "b")):
            with patch.object(bf, "fetch_pending_tachiyomi_rows", return_value=rows):
                with patch.object(bf, "process_one_row", side_effect=RuntimeError("boom")):
                    with patch.object(bf, "record_capture_failure") as fail:
                        with patch.object(bf, "TachiyomiCaptureSession") as sess_cls:
                            sess_cls.return_value.__enter__.return_value = MagicMock()
                            code = bf.run_backfill(db_name="default", limit=1, dry_run=True)
        assert code == 1
        fail.assert_not_called()

    def test_ensure_driver_reuses_existing_not_ready(self):
        session = tachiyomi.TachiyomiCaptureSession()
        driver = MagicMock()
        session._driver = driver
        session._ready = False
        with patch.object(session, "_verify_age") as verify:
            assert session._ensure_driver() is driver
            verify.assert_called_once_with(driver)
            assert session._ensure_driver() is driver
            verify.assert_called_once()

    def test_ensure_driver_skips_verify_when_already_ready_after_create(self):
        session = tachiyomi.TachiyomiCaptureSession()
        session._driver = None
        session._ready = True
        driver = MagicMock()
        with patch.object(tachiyomi, "create_chrome_driver", return_value=driver):
            with patch.object(session, "_verify_age") as verify:
                assert session._ensure_driver() is driver
        verify.assert_not_called()

    def test_ensure_driver_returns_immediately_when_ready(self):
        session = tachiyomi.TachiyomiCaptureSession()
        driver = MagicMock()
        session._driver = driver
        session._ready = True
        with patch.object(tachiyomi, "create_chrome_driver") as create:
            with patch.object(session, "_verify_age") as verify:
                assert session._ensure_driver() is driver
        create.assert_not_called()
        verify.assert_not_called()

    def test_capture_once_exception_without_recycle(self):
        driver = MagicMock()
        session = tachiyomi.TachiyomiCaptureSession()
        session._driver = driver
        session._ready = True

        class FakeWait:
            def __init__(self, drv, timeout):
                self.timeout = timeout

            def until(self, method):
                if self.timeout == 20:
                    return "publus"
                if self.timeout == 5:
                    raise RuntimeError("unexpected layout")
                return [1, 2]

            def until_not(self, method):
                return True

        with patch.object(tachiyomi, "WebDriverWait", FakeWait):
            with patch.object(tachiyomi, "ActionChains"):
                with patch.object(tachiyomi.os, "makedirs"):
                    with patch.object(tachiyomi, "is_end_of_book", return_value=False):
                        with patch.object(tachiyomi, "get_page_counter", return_value=(1, 5)):
                            with patch.object(tachiyomi.time, "sleep"):
                                with patch.object(tachiyomi, "save_page_source"):
                                    with patch.object(session, "_recycle") as recycle:
                                        assert session._capture_once("https://example.com/t") == []
        recycle.assert_not_called()

    def test_run_lock_release_when_fh_already_none(self, tmp_path: Path):
        lock = RunLock(tmp_path / "fh.lock")
        lock._held = True
        lock._fh = None
        lock.release()
        assert lock._held is False
