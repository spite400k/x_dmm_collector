"""ChromeDriver パス解決と安定化付きドライバー生成。"""

from __future__ import annotations

import logging
import shutil
import tempfile
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

_CACHED: str | None = None

DEFAULT_LAUNCH_RETRIES = 3
DEFAULT_RETRY_DELAY = 2.0
DEFAULT_PAGE_LOAD_TIMEOUT = 60


def chromedriver_path() -> str:
    """有効な chromedriver 実行ファイルパスを返す。

    webdriver-manager が存在しないネストパス
    （例: .../chromedriver-win32/chromedriver.exe）を返すことがあるため、
    実ファイルを親ディレクトリ側から探す。
    """
    global _CACHED
    if _CACHED is not None and Path(_CACHED).is_file():
        return _CACHED

    resolved = resolve_chromedriver_path(ChromeDriverManager().install())
    _CACHED = resolved
    return resolved


def resolve_chromedriver_path(raw: str) -> str:
    """install() が返したパスから実在する chromedriver を解決する。"""
    path = Path(raw)
    if _is_chromedriver_binary(path):
        return str(path.resolve())

    # VERSION/ とその直下サブディレクトリまで（例: chromedriver-win32/）
    search_roots = [path.parent, path.parent.parent]
    candidates: list[Path] = []
    for root in search_roots:
        if not root.is_dir():
            continue
        candidates.extend(root.glob("chromedriver.exe"))
        candidates.extend(root.glob("chromedriver"))
        candidates.extend(root.glob("*/chromedriver.exe"))
        candidates.extend(root.glob("*/chromedriver"))

    for candidate in candidates:
        if _is_chromedriver_binary(candidate):
            return str(candidate.resolve())

    raise FileNotFoundError(f"chromedriver executable not found near {raw!r}")


def _is_chromedriver_binary(path: Path) -> bool:
    if not path.is_file():
        return False
    return path.name.lower() in ("chromedriver", "chromedriver.exe")


def clear_chromedriver_cache() -> None:
    """テスト用: キャッシュをクリアする。"""
    global _CACHED
    _CACHED = None


def build_chrome_options(
    *,
    headless: bool = True,
    window_size: str | None = None,
    user_agent: str | None = None,
    extra_args: list[str] | None = None,
    user_data_dir: str | None = None,
) -> Options:
    """安定化オプション付きの Chrome Options を構築する。"""
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--remote-debugging-port=0")
    if user_data_dir:
        options.add_argument(f"--user-data-dir={user_data_dir}")
    if window_size:
        options.add_argument(f"--window-size={window_size}")
    if user_agent:
        options.add_argument(f"--user-agent={user_agent}")
    for arg in extra_args or []:
        options.add_argument(arg)
    return options


def create_chrome_driver(
    *,
    headless: bool = True,
    page_load_timeout: int = DEFAULT_PAGE_LOAD_TIMEOUT,
    window_size: str | None = None,
    user_agent: str | None = None,
    extra_args: list[str] | None = None,
    max_retries: int = DEFAULT_LAUNCH_RETRIES,
    retry_delay: float = DEFAULT_RETRY_DELAY,
) -> webdriver.Chrome:
    """安定化オプション付きで Chrome を起動する（失敗時は短い間隔でリトライ）。"""
    last_exc: BaseException | None = None
    attempts = max(1, max_retries)

    for attempt in range(attempts):
        user_data_dir = tempfile.mkdtemp(prefix="x_dmm_chrome_")
        options = build_chrome_options(
            headless=headless,
            window_size=window_size,
            user_agent=user_agent,
            extra_args=extra_args,
            user_data_dir=user_data_dir,
        )
        try:
            driver = webdriver.Chrome(
                service=Service(chromedriver_path()),
                options=options,
            )
            driver.set_page_load_timeout(page_load_timeout)
            setattr(driver, "_chrome_user_data_dir", user_data_dir)
            return driver
        except Exception as exc:
            last_exc = exc
            shutil.rmtree(user_data_dir, ignore_errors=True)
            if attempt >= attempts - 1:
                break
            logging.warning(
                "Chrome 起動失敗 (%s)。%.1f 秒後にリトライ (%d/%d)",
                exc,
                retry_delay,
                attempt + 1,
                attempts,
            )
            time.sleep(retry_delay)

    assert last_exc is not None
    raise last_exc


def quit_chrome_driver(driver: webdriver.Chrome | None) -> None:
    """driver.quit() と一時 user-data-dir の削除を行う。"""
    if driver is None:
        return
    user_data_dir = getattr(driver, "_chrome_user_data_dir", None)
    try:
        driver.quit()
    except Exception:
        pass
    if user_data_dir:
        shutil.rmtree(user_data_dir, ignore_errors=True)
