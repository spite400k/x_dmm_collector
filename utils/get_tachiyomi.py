import os
import time
import logging
from urllib.parse import urlparse
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from PIL import Image

from utils.chromedriver import create_chrome_driver, quit_chrome_driver

# ---------------------
# ログ設定
# ---------------------

# DMM book は 2026-06 頃から Publus（Web Components + Shadow DOM）へ移行。
# 旧 #viewer / #pageSliderCounter / #endOfBook は残っていない。
_VIEWER_KIND_JS = """
const publus = document.querySelector('publus-viewer');
if (publus && publus.shadowRoot && publus.shadowRoot.querySelector('canvas')) {
  return 'publus';
}
if (document.getElementById('viewer')) {
  return 'legacy';
}
return null;
"""

_PUBLUS_CURRENT_CANVAS_JS = """
const viewer = document.querySelector('publus-viewer');
if (!viewer || !viewer.shadowRoot) return null;
const canvases = [...viewer.shadowRoot.querySelectorAll('canvas')];
let best = null;
let bestAbs = Infinity;
for (const c of canvases) {
  const rect = c.getBoundingClientRect();
  if (rect.width < 50 || rect.height < 50) continue;
  const left = Math.abs(parseFloat(c.style.left || '0'));
  if (left < bestAbs) {
    bestAbs = left;
    best = c;
  }
}
return best;
"""

_PUBLUS_PAGE_COUNTER_JS = """
const ctrl = document.querySelector('publus-controller');
if (!ctrl || !ctrl.shadowRoot) return null;
const cur = ctrl.shadowRoot.querySelector('.pages-indicator-rect .current');
const mx = ctrl.shadowRoot.querySelector('.pages-indicator-rect .max');
if (!cur || !mx) return null;
const current = parseInt((cur.textContent || '').trim(), 10);
const total = parseInt((mx.textContent || '').trim(), 10);
if (!Number.isFinite(current) || !Number.isFinite(total)) return null;
return [current, total];
"""

_PUBLUS_END_OF_BOOK_JS = """
const ctrl = document.querySelector('publus-controller');
if (!ctrl || !ctrl.shadowRoot) return false;
const el = ctrl.shadowRoot.querySelector('.last-page-screen');
if (!el) return false;
const st = getComputedStyle(el);
return st.visibility !== 'hidden' && st.display !== 'none' && Number(st.opacity || '1') > 0;
"""

def save_page_source(driver, idx, log_dir="logs"):
    # ログディレクトリがなければ作成
    os.makedirs(log_dir, exist_ok=True)

    # ファイル名に idx をつける
    log_file = os.path.join(log_dir, f"page_source_{idx}.html")

    # ページソースを保存
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(driver.page_source)

    print(f"✅ ページソースを保存しました: {log_file}")

def detect_viewer_kind(driver):
    """'publus' / 'legacy' / None"""
    return driver.execute_script(_VIEWER_KIND_JS)

def wait_for_viewer_ready(driver, timeout=20):
    """Publus または旧ビューアの描画完了を待つ。戻り値は kind。"""
    return WebDriverWait(driver, timeout).until(
        lambda d: detect_viewer_kind(d)
    )

def is_end_of_book(driver) -> bool:
    if detect_viewer_kind(driver) == "publus":
        return bool(driver.execute_script(_PUBLUS_END_OF_BOOK_JS))
    end_els = driver.find_elements(By.ID, "endOfBook")
    return bool(end_els and end_els[0].is_displayed())

# ---------------------
# 表示中のcanvas取得関数
# ---------------------
def get_visible_canvas(driver):
    logging.debug("canvas探索開始")
    if detect_viewer_kind(driver) == "publus":
        canvas = driver.execute_script(_PUBLUS_CURRENT_CANVAS_JS)
        if canvas is not None:
            return canvas
        raise Exception("Publus の表示中 canvas が見つかりません")

    candidates = driver.find_elements(By.CSS_SELECTOR, "canvas")
    logging.debug(f"候補canvas数: {len(candidates)}")

    for i, c in enumerate(candidates):
        try:
            visible = c.is_displayed()
            logging.debug(f"canvas[{i}] visible={visible}, size={c.size}, location={c.location}")
            if visible:
                return c
        except Exception as e:
            logging.warning(f"canvas[{i}] 可視チェック失敗: {e}")
    raise Exception("表示中のcanvasが見つかりません")

# ---------------------
# ページカウンタ取得関数
# ---------------------
def get_page_counter(driver, timeout=30):
    """現在/総ページ数を取得する（Publus / 旧 viewer 両対応）。"""
    try:
        def _read(d):
            if detect_viewer_kind(d) == "publus":
                return d.execute_script(_PUBLUS_PAGE_COUNTER_JS)
            elem = d.find_elements(By.ID, "pageSliderCounter")
            if not elem:
                return None
            text = (elem[0].text or "").strip()
            if "/" not in text:
                return None
            current_page, total_page = map(int, text.split("/"))
            return [current_page, total_page]

        pair = WebDriverWait(driver, timeout).until(_read)
        current_page, total_page = int(pair[0]), int(pair[1])
        logging.info("取得した page counter: %s/%s", current_page, total_page)
        return current_page, total_page
    except Exception as e:
        logging.warning("ページカウンタ取得失敗: %s", e)
        with open("debug_get_page_counter.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        driver.save_screenshot("debug_get_page_counter.png")
        return 1, 50

# ---------------------
# Tachiyomiページキャプチャ
# ---------------------
_MOBILE_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1"
)
_DMM_TOP_URL = "https://www.dmm.co.jp/top/"
_NAVIGATION_RETRIES = 3
_NAVIGATION_RETRY_BASE_DELAY = 3.0

# FANZA / book.dmm の年齢確認（旧「はい」と新「18歳以上なので進む」の両方）。
_AGE_CHECK_SELECTORS = (
    (By.XPATH, "//a[contains(normalize-space(.),'18歳以上なので進む')]"),
    (By.XPATH, "//a[contains(@href,'declared=yes')]"),
    (By.XPATH, "//a[normalize-space(text())='はい']"),
    (By.XPATH, "//a[normalize-space(text())='I Agree']"),
    (By.LINK_TEXT, "はい"),
    (By.LINK_TEXT, "I Agree"),
    (By.XPATH, "//button[.//span[normalize-space(text())='はい']]"),
    (By.XPATH, "//button[normalize-space(text())='はい']"),
)

def _is_age_check_url(url: str | None) -> bool:
    if not isinstance(url, str) or not url:
        return False
    parsed = urlparse(url)
    path = (parsed.path or "").lower()
    host = (parsed.hostname or "").lower()
    return "age_check" in path or "age_check" in host

def _apply_age_check_cookie(driver) -> None:
    try:
        driver.add_cookie(
            {
                "name": "age_check_done",
                "value": "1",
                "path": "/",
                "domain": ".dmm.co.jp",
            }
        )
    except Exception:
        logging.debug("age_check_done cookie 設定をスキップ", exc_info=True)

def _age_gate_elements_present(driver) -> bool:
    try:
        for by, selector in _AGE_CHECK_SELECTORS[:2]:
            found = driver.find_elements(by, selector)
            # Selenium は list を返す。MagicMock 等の偽陽性を避ける。
            if isinstance(found, list) and found:
                return True
    except Exception:
        return False
    return False

def _handle_age_check(driver) -> bool:
    """年齢確認ページ / モーダルがあれば突破する。クリックしたら True。"""
    current_url = driver.current_url if isinstance(getattr(driver, "current_url", None), str) else ""
    on_age_check = _is_age_check_url(current_url) or _age_gate_elements_present(driver)
    if not on_age_check:
        return False

    clicked = False
    for by, selector in _AGE_CHECK_SELECTORS:
        try:
            yes_button = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((by, selector))
            )
            driver.execute_script("arguments[0].click();", yes_button)
            clicked = True
            logging.info("年齢認証クリック成功: %s", selector)
            break
        except Exception:
            continue

    if not clicked:
        logging.warning("年齢認証ボタンを検出できず: url=%s title=%s", current_url, driver.title)
        return False

    try:
        WebDriverWait(driver, 10).until(lambda d: not _is_age_check_url(d.current_url))
        logging.info("年齢認証ページ離脱: %s", driver.current_url)
    except Exception:
        logging.warning("年齢認証ページ離脱を確認できず: %s", driver.current_url)

    _apply_age_check_cookie(driver)
    return True

def _driver_get_with_retry(driver, url: str) -> None:
    """driver.get を一時障害時に数回リトライする。"""
    last_exc: BaseException | None = None
    for attempt in range(_NAVIGATION_RETRIES):
        try:
            driver.get(url)
            return
        except Exception as exc:
            last_exc = exc
            if attempt >= _NAVIGATION_RETRIES - 1:
                raise
            delay = _NAVIGATION_RETRY_BASE_DELAY * (attempt + 1)
            logging.warning(
                "driver.get 失敗 (%d/%d) url=%s: %r → %.0fs 後にリトライ",
                attempt + 1,
                _NAVIGATION_RETRIES,
                url,
                exc,
                delay,
            )
            time.sleep(delay)
    if last_exc is not None:  # pragma: no cover
        raise last_exc

def _wait_for_viewer_with_retry(driver, timeout: int = 20, *, url: str | None = None):
    """ビューア表示待ちを数回リトライする。戻り値は viewer kind。"""
    last_exc: BaseException | None = None
    for attempt in range(_NAVIGATION_RETRIES):
        try:
            _handle_age_check(driver)
            kind = wait_for_viewer_ready(driver, timeout=timeout)
            if kind == "legacy":
                WebDriverWait(driver, 12).until_not(
                    EC.visibility_of_any_elements_located((By.CSS_SELECTOR, ".loadingImage"))
                )
            return kind
        except (TimeoutException, NoSuchElementException) as exc:
            last_exc = exc
            if attempt >= _NAVIGATION_RETRIES - 1:
                raise
            delay = _NAVIGATION_RETRY_BASE_DELAY * (attempt + 1)
            logging.warning(
                "ビューア表示待ち失敗 (%d/%d): %r → %.0fs 後にリトライ",
                attempt + 1,
                _NAVIGATION_RETRIES,
                exc,
                delay,
            )
            time.sleep(delay)
            if url:
                try:
                    _driver_get_with_retry(driver, url)
                except Exception as reload_exc:
                    logging.warning("ビューア再取得失敗: %r", reload_exc)
    if last_exc is not None:  # pragma: no cover
        raise last_exc
    raise TimeoutException("viewer wait failed")

def _should_recycle_driver(exc: BaseException) -> bool:
    """セッション切断・Chrome ハングならドライバーを捨てて作り直す。"""
    from selenium.common.exceptions import InvalidSessionIdException

    if isinstance(exc, InvalidSessionIdException):
        return True
    text = f"{type(exc).__name__} {exc}".lower()
    needles = (
        "invalid session",
        "chrome not reachable",
        "session not created",
        "httpconnectionpool",
        "read timed out",
        "devtoolsactiveport",
        "timeoutexception",
    )
    return any(needle in text for needle in needles)

class TachiyomiCaptureSession:
    """1 収集プロセスで Chrome を使い回す。"""

    def __init__(self) -> None:
        self._driver = None
        self._ready = False

    def __enter__(self) -> "TachiyomiCaptureSession":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def close(self) -> None:
        quit_chrome_driver(self._driver)
        self._driver = None
        self._ready = False

    def _recycle(self) -> None:
        logging.warning("立ち読み Chrome を破棄して再作成します")
        self.close()

    def _ensure_driver(self):
        if self._driver is not None and self._ready:
            return self._driver
        if self._driver is None:
            self._driver = create_chrome_driver(
                page_load_timeout=60,
                window_size="440,932",
                user_agent=_MOBILE_USER_AGENT,
            )
        if not self._ready:
            self._verify_age(self._driver)
            self._ready = True
        return self._driver

    def _verify_age(self, driver) -> None:
        logging.info("DMMトップページを開く")
        driver.get(_DMM_TOP_URL)
        if _handle_age_check(driver):
            logging.info("年齢認証成功")
            time.sleep(1)
        else:
            logging.info("年齢認証不要 or 既認証済み")
        _apply_age_check_cookie(driver)

    def capture(self, tachiyomi_url: str) -> list[str]:
        logging.info("立ち読み対象URL: %s", tachiyomi_url)
        try:
            return self._capture_once(tachiyomi_url)
        except Exception as e:
            logging.warning("立ち読み処理失敗（空リストで続行）: %s", e)
            if _should_recycle_driver(e):
                self._recycle()
            return []

    def _capture_once(self, tachiyomi_url: str) -> list[str]:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        temp_dir = os.path.join(base_dir, "temp")
        os.makedirs(temp_dir, exist_ok=True)

        try:
            driver = self._ensure_driver()
        except Exception as e:
            logging.warning("Chrome 起動失敗（立ち読みをスキップ）: %s", e)
            self._recycle()
            return []

        images: list[str] = []
        try:
            _driver_get_with_retry(driver, tachiyomi_url)
        except Exception as e:
            logging.warning("driver.get 失敗（立ち読みをスキップ）: %r", e)
            if _should_recycle_driver(e):
                self._recycle()
            return []

        time.sleep(2)
        _handle_age_check(driver)
        page_idx = 1
        current_page = 0

        try:
            kind = _wait_for_viewer_with_retry(driver, timeout=20, url=tachiyomi_url)
            logging.info("ビューア準備完了: kind=%s", kind)
        except (TimeoutException, NoSuchElementException) as e:
            logging.warning("ビューア表示待ちに失敗（立ち読みをスキップ）: %r", e)
            save_page_source(driver, idx=0)
            return images

        _, total_page = get_page_counter(driver, timeout=10)
        logging.info("総ページ数: %s", total_page)

        actions = ActionChains(driver)
        time.sleep(2)

        while True:
            try:
                logging.info(
                    "=== ページ処理開始 idx=%s, 現在=%s, 総数=%s ===",
                    page_idx,
                    current_page,
                    total_page,
                )
                if is_end_of_book(driver):
                    logging.info("最終ページを検出 → スクリーンショット終了")
                    break

                canvas = WebDriverWait(driver, 5).until(lambda d: get_visible_canvas(d))
                screenshot_path = os.path.join(temp_dir, f"page_{page_idx:03}.png")
                canvas.screenshot(screenshot_path)

                webp_path = screenshot_path.replace(".png", ".webp")
                with Image.open(screenshot_path) as im:
                    im.save(webp_path, "webp", quality=90)
                os.remove(screenshot_path)

                images.append(webp_path)
                logging.info("保存成功 (WebP): %s", webp_path)

                if current_page == 0:
                    current_page, _ = get_page_counter(driver, timeout=5)

                if current_page >= total_page:
                    logging.info("最後のページに到達 → 終了")
                    break

                logging.debug("次ページへ移動 (ARROW_LEFT)")
                actions.send_keys(Keys.ARROW_LEFT).perform()
                page_idx += 1
                current_page += 1
                time.sleep(1)

            except (TimeoutException, NoSuchElementException) as e:
                logging.warning("canvas取得失敗 idx=%s: %s", page_idx, e)
                save_page_source(driver, idx=page_idx)
                break
            except Exception as e:
                logging.exception("予期せぬエラー idx=%s: %s", page_idx, e)
                save_page_source(driver, idx=page_idx)
                if _should_recycle_driver(e):
                    self._recycle()
                break

        return images

def capture_all_tachiyomi_pages(
    tachiyomi_url: str,
    *,
    session: TachiyomiCaptureSession | None = None,
) -> list[str]:
    """立ち読みページをキャプチャする。session 省略時は都度 Chrome を起動・終了する。"""
    if session is not None:
        return session.capture(tachiyomi_url)
    with TachiyomiCaptureSession() as owned:
        return owned.capture(tachiyomi_url)

if __name__ == "__main__":
    test_url = "https://book.dmm.co.jp/tachiyomi/?cid=FRNfXRNVFW1RAQxaBwFUVgMLU1gAClAPVU5EDl0VClQMBllNB1o*UFcKWhRHVwVfCBxZW1kEVQ__&lin=1&sd=0"
    capture_all_tachiyomi_pages(test_url)
