"""utils.chromedriver のパス解決・起動リトライテスト。"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from utils import chromedriver as chromedriver_mod
from utils.chromedriver import (
    build_chrome_options,
    chromedriver_path,
    clear_chromedriver_cache,
    create_chrome_driver,
    quit_chrome_driver,
    resolve_chromedriver_path,
)


@pytest.fixture(autouse=True)
def _reset_cache():
    clear_chromedriver_cache()
    yield
    clear_chromedriver_cache()


class TestResolveChromedriverPath:
    def test_valid_binary_path_returned_as_is(self, tmp_path: Path):
        binary = tmp_path / "chromedriver.exe"
        binary.write_bytes(b"MZ")
        assert resolve_chromedriver_path(str(binary)) == str(binary.resolve())

    def test_missing_nested_path_resolves_parent_binary(self, tmp_path: Path):
        version_dir = tmp_path / "150.0.7871.124"
        nested = version_dir / "chromedriver-win32"
        nested.mkdir(parents=True)
        binary = version_dir / "chromedriver.exe"
        binary.write_bytes(b"MZ")

        raw = str(nested / "chromedriver.exe")
        assert resolve_chromedriver_path(raw) == str(binary.resolve())

    def test_missing_path_resolves_sibling_subdir_binary(self, tmp_path: Path):
        version_dir = tmp_path / "150.0.7871.124"
        empty = version_dir / "chromedriver-win32"
        empty.mkdir(parents=True)
        real_dir = version_dir / "chromedriver-win64"
        real_dir.mkdir()
        binary = real_dir / "chromedriver.exe"
        binary.write_bytes(b"MZ")

        raw = str(empty / "chromedriver.exe")
        assert resolve_chromedriver_path(raw) == str(binary.resolve())

    def test_notices_file_is_not_treated_as_binary(self, tmp_path: Path):
        version_dir = tmp_path / "150.0.7871.124"
        version_dir.mkdir()
        notices = version_dir / "THIRD_PARTY_NOTICES.chromedriver"
        notices.write_text("notice")
        binary = version_dir / "chromedriver.exe"
        binary.write_bytes(b"MZ")

        assert resolve_chromedriver_path(str(notices)) == str(binary.resolve())

    def test_not_found_raises(self, tmp_path: Path):
        missing = tmp_path / "missing" / "chromedriver.exe"
        with pytest.raises(FileNotFoundError, match="chromedriver executable not found"):
            resolve_chromedriver_path(str(missing))


class TestChromedriverPathCache:
    def test_caches_resolved_path(self, tmp_path: Path):
        binary = tmp_path / "chromedriver.exe"
        binary.write_bytes(b"MZ")

        with patch.object(
            chromedriver_mod,
            "ChromeDriverManager",
        ) as manager_cls:
            manager_cls.return_value.install.return_value = str(binary)
            first = chromedriver_path()
            second = chromedriver_path()

        assert first == second == str(binary.resolve())
        manager_cls.return_value.install.assert_called_once()

    def test_reinstalls_when_cached_file_missing(self, tmp_path: Path):
        first_binary = tmp_path / "old" / "chromedriver.exe"
        first_binary.parent.mkdir()
        first_binary.write_bytes(b"MZ")
        second_binary = tmp_path / "new" / "chromedriver.exe"
        second_binary.parent.mkdir()
        second_binary.write_bytes(b"MZ")

        with patch.object(
            chromedriver_mod,
            "ChromeDriverManager",
        ) as manager_cls:
            manager_cls.return_value.install.side_effect = [
                str(first_binary),
                str(second_binary),
            ]
            assert chromedriver_path() == str(first_binary.resolve())
            first_binary.unlink()
            assert chromedriver_path() == str(second_binary.resolve())

        assert manager_cls.return_value.install.call_count == 2


class TestCreateChromeDriver:
    def test_build_chrome_options_includes_stability_flags(self):
        options = build_chrome_options(
            user_data_dir="/tmp/x",
            window_size="440,932",
            user_agent="UA",
            extra_args=["--foo"],
        )
        args = options.arguments
        assert "--headless=new" in args
        assert "--remote-debugging-port=0" in args
        assert "--user-data-dir=/tmp/x" in args
        assert "--window-size=440,932" in args
        assert "--user-agent=UA" in args
        assert "--foo" in args

    def test_build_chrome_options_without_headless(self):
        options = build_chrome_options(headless=False)
        assert "--headless=new" not in options.arguments

    def test_retries_then_succeeds(self):
        driver = MagicMock()
        with patch.object(chromedriver_mod, "chromedriver_path", return_value="fake"):
            with patch.object(
                chromedriver_mod.webdriver,
                "Chrome",
                side_effect=[RuntimeError("fail"), driver],
            ) as chrome_cls:
                with patch.object(chromedriver_mod.time, "sleep") as sleep_mock:
                    with patch.object(chromedriver_mod.shutil, "rmtree"):
                        result = create_chrome_driver(
                            max_retries=3,
                            retry_delay=0.01,
                            page_load_timeout=30,
                        )

        assert result is driver
        assert chrome_cls.call_count == 2
        sleep_mock.assert_called_once()
        driver.set_page_load_timeout.assert_called_once_with(30)
        assert getattr(driver, "_chrome_user_data_dir")

    def test_raises_after_exhausted_retries(self):
        with patch.object(chromedriver_mod, "chromedriver_path", return_value="fake"):
            with patch.object(
                chromedriver_mod.webdriver,
                "Chrome",
                side_effect=RuntimeError("dead"),
            ):
                with patch.object(chromedriver_mod.time, "sleep"):
                    with patch.object(chromedriver_mod.shutil, "rmtree"):
                        with pytest.raises(RuntimeError, match="dead"):
                            create_chrome_driver(max_retries=2, retry_delay=0.01)

    def test_quit_chrome_driver_removes_user_data_dir(self, tmp_path: Path):
        user_dir = tmp_path / "chrome_profile"
        user_dir.mkdir()
        driver = MagicMock()
        driver._chrome_user_data_dir = str(user_dir)

        quit_chrome_driver(driver)

        driver.quit.assert_called_once()
        assert not user_dir.exists()

    def test_quit_chrome_driver_none_is_noop(self):
        quit_chrome_driver(None)

    def test_quit_chrome_driver_ignores_quit_error(self, tmp_path: Path):
        user_dir = tmp_path / "chrome_profile"
        user_dir.mkdir()
        driver = MagicMock()
        driver.quit.side_effect = RuntimeError("already closed")
        driver._chrome_user_data_dir = str(user_dir)

        quit_chrome_driver(driver)

        assert not user_dir.exists()
