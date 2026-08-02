"""utils.chromedriver のパス解決テスト。"""

from pathlib import Path
from unittest.mock import patch

import pytest

from utils import chromedriver as chromedriver_mod
from utils.chromedriver import (
    chromedriver_path,
    clear_chromedriver_cache,
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
