import logging
import re
import time
from typing import Optional

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def expand_hidden_reviews(driver):
    """
    ネタバレ扱いの折りたたみ（「レビューを表示する」）や「続きを読む」を開く。
    video.dmm 新 UI では button / a にラベルが載るため p 固定 XPath だけでは足りない。
    """
    try:
        selectors = [
            (By.XPATH, "//*[self::button or self::a or self::p or self::span][normalize-space(.)='レビューを表示する']"),
            (By.XPATH, "//button[contains(normalize-space(.),'レビューを表示する')]"),
            (By.XPATH, "//a[contains(normalize-space(.),'レビューを表示する')]"),
            (By.XPATH, "//p[normalize-space(.)='レビューを表示する']"),
            (By.CSS_SELECTOR, "span.dcd-review__modtogglelink-open"),
            # FANZA動画 review-item 内「続きを読む」（折りたたみ本文）
            (By.XPATH, "//button[contains(normalize-space(.),'続きを読む')]"),
        ]
        for _ in range(4):
            clicked = False
            for by, sel in selectors:
                for el in driver.find_elements(by, sel):
                    try:
                        driver.execute_script(
                            "arguments[0].scrollIntoView({block: 'center', behavior: 'instant'});",
                            el,
                        )
                        driver.execute_script("arguments[0].click();", el)
                        clicked = True
                    except Exception:
                        continue
            if not clicked:
                break
            time.sleep(0.45)
    except Exception as e:
        logging.warning(f"ネタバレ展開失敗: {e}")


def _node_text_content(driver, node) -> str:
    if node is None:
        return ""
    try:
        raw = driver.execute_script("return (arguments[0].textContent || '').trim();", node)
        return (raw or "").strip()
    except Exception:
        return ""


def _legacy_e2e_review_body_text(driver, block) -> str:
    """overflow-hidden 内は Selenium .text が空になりやすいので textContent を使う。"""
    try:
        body_el = block.find_element(
            By.CSS_SELECTOR,
            "div.text-xs.overflow-hidden.break-all",
        )
        t = _node_text_content(driver, body_el)
        if t:
            return t
    except Exception:
        pass
    parts = []
    for p in block.find_elements(By.CSS_SELECTOR, "p"):
        try:
            p.find_element(
                By.XPATH,
                "./ancestor::div[contains(@class,'border-t')][contains(@class,'border-gray-300')]",
            )
            continue
        except Exception:
            pass
        tc = _node_text_content(driver, p)
        if tc:
            parts.append(tc)
    return " ".join(parts)


def _parse_doujin_rating_from_unit(unit) -> float:
    for span in unit.find_elements(By.CSS_SELECTOR, "span[class*='dcd-review-rating-']"):
        cls = span.get_attribute("class") or ""
        m = re.search(r"dcd-review-rating-(\d+)", cls)
        if m:
            return int(m.group(1)) / 10.0
    return 0.0


def _is_small_star_img(img) -> bool:
    w = (img.get_attribute("width") or "").strip()
    h = (img.get_attribute("height") or "").strip()
    return w == "16" or h == "16"


def _element_inside(driver, container, node) -> bool:
    try:
        return bool(
            driver.execute_script(
                "return arguments[0].contains(arguments[1]);", container, node
            )
        )
    except Exception:
        return False


def _strip_digital_review_noise(text: str) -> str:
    for noise in (
        "このレビューは参考になりましたか？",
        "が参考になったと投票しています。",
        "レビューを書く",
        "レビューを編集",
    ):
        if noise in text:
            text = text.split(noise)[0].strip()
    spoiler_note = "※このレビューは作品の内容に関する記述が含まれています。"
    if spoiler_note in text:
        text = text.replace(spoiler_note, "").strip()
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _parse_legacy_e2e_video_reviews(driver, max_reviews: int) -> list:
    review_blocks = driver.find_elements(
        By.CSS_SELECTOR,
        '[data-e2eid="review-item"]',
    )
    n_blocks = len(review_blocks)
    logging.info(
        "動画レビュー取得(legacy): [data-e2eid=review-item] を %s 件検出", n_blocks
    )
    reviews = []
    for idx, block in enumerate(review_blocks[:max_reviews], start=1):
        stars = block.find_elements(
            By.CSS_SELECTOR,
            'img[src*="yellow.svg"]',
        )
        rating = len(stars)
        title = ""
        try:
            title_el = block.find_element(
                By.CSS_SELECTOR,
                "header span.font-bold",
            )
            title = _node_text_content(driver, title_el)
        except Exception:
            pass
        text = _legacy_e2e_review_body_text(driver, block)
        if text:
            reviews.append({"rating": rating, "title": title, "text": text})
        else:
            logging.debug(
                "動画レビュー取得(legacy): [%s] 本文なし（段落テキスト空）preview=%r",
                idx,
                (block.text or "").replace("\n", " ")[:100],
            )
        logging.debug(
            "動画レビュー取得(legacy): [%s/%s] rating=%s title=%r text_len=%s",
            idx,
            min(n_blocks, max_reviews),
            rating,
            title[:80] if title else "",
            len(text),
        )
    logging.info(
        "動画レビュー取得(legacy): 本文抽出できたレビュー %s / %s 件",
        len(reviews),
        min(n_blocks, max_reviews),
    )
    return reviews


def _parse_fanza_digital_video_reviews(driver, root, summary_el, max_reviews: int) -> list:
    """video.dmm.co.jp 新UI（#review 内。参考: review_simw005_*.html）"""
    reviews = []
    seen_prefix = set()

    links = root.find_elements(
        By.CSS_SELECTOR,
        'a[href*="/review-front/reviewer/"]',
    )
    for link in links:
        if len(reviews) >= max_reviews:
            break
        unit = None
        el = link
        for _ in range(16):
            try:
                el = el.find_element(By.XPATH, "..")
            except Exception:
                break
            if summary_el and _element_inside(driver, summary_el, el):
                continue
            imgs = el.find_elements(By.CSS_SELECTOR, 'img[src*="yellow.svg"]')
            n_small = sum(1 for im in imgs if _is_small_star_img(im))
            if 1 <= n_small <= 5 and len(el.text.strip()) > 20:
                unit = el
        if unit is None:
            continue
        sig = unit.text.strip()[:160]
        if sig in seen_prefix:
            continue
        seen_prefix.add(sig)

        rating = sum(
            1
            for im in unit.find_elements(By.CSS_SELECTOR, 'img[src*="yellow.svg"]')
            if _is_small_star_img(im)
        )
        rating = min(rating, 5) if rating else 0

        title = ""
        for sel in ("span.font-bold", "h4", "[class*='font-semibold']"):
            try:
                t = unit.find_element(By.CSS_SELECTOR, sel).text.strip()
                if t and len(t) < 200:
                    title = t
                    break
            except Exception:
                pass

        body = _strip_digital_review_noise(unit.text.strip())
        if title and body.startswith(title):
            text = body
        elif title:
            text = f"{title}\n{body}"
        else:
            text = body

        reviewer = None
        try:
            reviewer = link.text.replace("\n", "").strip() or None
        except Exception:
            pass

        date_str = None
        try:
            t_el = unit.find_element(By.TAG_NAME, "time")
            date_str = (t_el.get_attribute("datetime") or t_el.text or "").strip() or None
        except Exception:
            m = re.search(r"(\d{4})[./年](\d{1,2})[./月](\d{1,2})", unit.text)
            if m:
                date_str = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

        if text:
            reviews.append(
                {
                    "rating": float(rating),
                    "title": title,
                    "text": text,
                    "date": date_str,
                    "reviewer": reviewer,
                }
            )

    if reviews:
        return reviews

    # レビュアリンクが無い場合（稀）: 16px 星でブロックを推定
    for img in root.find_elements(By.CSS_SELECTOR, 'img[src*="yellow.svg"]'):
        if len(reviews) >= max_reviews:
            break
        if not _is_small_star_img(img):
            continue
        if summary_el and _element_inside(driver, summary_el, img):
            continue
        el = img
        unit = None
        for _ in range(14):
            try:
                el = el.find_element(By.XPATH, "..")
            except Exception:
                break
            if summary_el and _element_inside(driver, summary_el, el):
                continue
            txt = el.text.strip()
            n_small = sum(
                1
                for im in el.find_elements(By.CSS_SELECTOR, 'img[src*="yellow.svg"]')
                if _is_small_star_img(im)
            )
            if 1 <= n_small <= 5 and len(txt) > 50:
                unit = el
        if unit is None:
            continue
        sig = unit.text.strip()[:160]
        if sig in seen_prefix:
            continue
        seen_prefix.add(sig)
        rating = min(
            sum(
                1
                for im in unit.find_elements(By.CSS_SELECTOR, 'img[src*="yellow.svg"]')
                if _is_small_star_img(im)
            ),
            5,
        )
        text = _strip_digital_review_noise(unit.text.strip())
        if text:
            reviews.append({"rating": float(rating), "title": "", "text": text})

    return reviews


def _wait_video_review_ui(driver, timeout: float = 20) -> Optional[str]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        # book.dmm (comic) React UI
        if driver.find_elements(By.CSS_SELECTOR, '[data-section-name="review"]'):
            return "comic"
        if driver.find_elements(By.CSS_SELECTOR, '[data-e2eid="review-item"]'):
            return "legacy"
        if driver.find_elements(By.ID, "review"):
            return "digital"
        time.sleep(0.25)
    return None


def _hydrate_fanza_digital_review_list(driver, timeout: float = 25) -> None:
    """
    video.dmm の #review は枠だけ先に SSR され、レビュアリンクや 16px 星のカードが
    後からクライアント描画されることがある（review_sivr00484_*.html 参照）。
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            root = driver.find_element(By.ID, "review")
        except Exception:
            time.sleep(0.3)
            continue
        try:
            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center', behavior: 'instant'});",
                root,
            )
        except Exception:
            pass
        try:
            if root.find_elements(
                By.CSS_SELECTOR, 'a[href*="/review-front/reviewer/"]'
            ):
                return
            if driver.find_elements(By.CSS_SELECTOR, '[data-e2eid="review-item"]'):
                return
            small = root.find_elements(
                By.CSS_SELECTOR, 'img[src*="yellow.svg"][width="16"]'
            )
            if len(small) >= 5:
                return
        except Exception:
            pass
        try:
            driver.execute_script("window.scrollBy(0, 500);")
        except Exception:
            pass
        time.sleep(0.35)
    logging.warning(
        "動画レビュー: #review 内の一覧が %.0f 秒以内に現れませんでした",
        timeout,
    )


# =========================
# 📝 動画レビュー取得（legacy e2e / FANZA動画 #review 新UI）
# =========================
def get_video_reviews(driver, product_url, max_reviews=10):
    logging.info(f"🔍 動画レビュー取得: {product_url}")

    try:
        mode = _wait_video_review_ui(driver, timeout=20)
        if not mode:
            logging.warning(
                f"[Video Review] レビュー領域が見つかりません: {product_url}"
            )
            return []

        expand_hidden_reviews(driver)
        time.sleep(0.8)

        if mode == "legacy":
            logging.info("🔍 動画レビュー取得: legacy")
            expand_hidden_reviews(driver)
            time.sleep(0.5)
            return _parse_legacy_e2e_video_reviews(driver, max_reviews)

        if mode == "comic":
            logging.info("🔍 動画レビュー取得: comic")
            expand_hidden_reviews(driver)
            time.sleep(0.5)
            return _parse_comic_reviews(driver, max_reviews)

        logging.info("🔍 動画レビュー取得: digital")
        _hydrate_fanza_digital_review_list(driver, timeout=25)
        # 一覧が遅延描画されたあとにネタバレ折りたたみが付くため、展開をもう一度試す
        expand_hidden_reviews(driver)
        time.sleep(0.6)
        root = driver.find_element(By.ID, "review")
        summaries = root.find_elements(
            By.CSS_SELECTOR,
            "div.border.rounded-lg.border-gray-300",
        )
        summary_el = summaries[0] if summaries else None
        reviews = _parse_fanza_digital_video_reviews(
            driver, root, summary_el, max_reviews
        )
        logging.info(f"動画(デジタル)レビュー取得: {len(reviews)} 件")
        return reviews

    except Exception as e:
        logging.warning(f"[Video Review Parse Error] {product_url} → {repr(e)}")
        return []


def _parse_comic_reviews(driver, max_reviews: int) -> list:
    """
    floor=comic(book.dmm) のレビュー抽出。
    目印: section[data-section-name="review"]
    """
    roots = driver.find_elements(By.CSS_SELECTOR, '[data-section-name="review"]')
    if not roots:
        logging.info("comicレビュー: 0件（review section なし）")
        return []

    root = roots[0]
    reviews = []

    # 本文候補: review-content 配下の p が最優先
    cards = root.find_elements(
        By.XPATH,
        ".//div[.//a[@data-testid='nickname'] and .//p]",
    )
    if not cards:
        cards = root.find_elements(By.XPATH, ".//div[.//p and .//i[@data-name='yellow']]")

    for card in cards[:max_reviews]:
        try:
            paragraphs = card.find_elements(By.XPATH, ".//p")
            body_parts = []
            for p in paragraphs:
                t = p.text.strip()
                if not t:
                    continue
                # 評価UI文言を除外
                if "参考になった" in t or "このレビューは参考になりましたか" in t:
                    continue
                body_parts.append(t)
            text = _strip_digital_review_noise("\n".join(body_parts).strip())

            if not text:
                continue

            rating = len(card.find_elements(By.XPATH, ".//i[@data-name='yellow']"))
            rating = min(rating, 5)

            reviewer = None
            date_str = None
            try:
                reviewer = card.find_element(
                    By.CSS_SELECTOR, 'a[data-testid="nickname"]'
                ).text.strip()
            except Exception:
                pass

            # 2026/03/06 のような日付を拾う
            m = re.search(r"(20\d{2})[./年](\d{1,2})[./月](\d{1,2})", card.text)
            if m:
                date_str = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

            reviews.append(
                {
                    "rating": float(rating) if rating else 0.0,
                    "text": text,
                    "date": date_str,
                    "reviewer": reviewer,
                }
            )
        except Exception:
            continue

    logging.info("comicレビュー取得: %s 件", len(reviews))
    return reviews




# =========================
# 📝 同人誌レビュー取得（FANZA同人: #review_anchor / .dcd-review__unit）
# =========================
def get_doujin_reviews(driver, product_url, max_reviews=10):

    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "#review_anchor"))
        )

        units = driver.find_elements(By.CSS_SELECTOR, "#review_anchor li.dcd-review__unit")
        if not units:
            try:
                WebDriverWait(driver, 4).until(
                    lambda d: d.find_elements(
                        By.CSS_SELECTOR, "#review_anchor li.dcd-review__unit"
                    )
                )
            except Exception:
                pass
            units = driver.find_elements(
                By.CSS_SELECTOR, "#review_anchor li.dcd-review__unit"
            )

        if not units:
            logging.info("同人レビュー: 0件（セクション内に .dcd-review__unit なし）")
            return []

        expand_hidden_reviews(driver)
        time.sleep(0.25)

        units = driver.find_elements(By.CSS_SELECTOR, "#review_anchor li.dcd-review__unit")

        reviews = []

        for unit in units[:max_reviews]:
            title = ""
            try:
                title = unit.find_element(
                    By.CSS_SELECTOR, "span.dcd-review__unit__title"
                ).text.strip()
            except Exception:
                pass

            comment_parts = []
            for div in unit.find_elements(By.CSS_SELECTOR, "div.dcd-review__unit__comment"):
                t = div.text.strip()
                if t:
                    comment_parts.append(t)
            body = "\n".join(comment_parts)

            reviewer = None
            try:
                reviewer = unit.find_element(
                    By.CSS_SELECTOR, "span.dcd-review__unit__reviewer a"
                ).text.replace("\n", "").strip()
            except Exception:
                pass

            date_str = None
            try:
                raw = unit.find_element(
                    By.CSS_SELECTOR, "span.dcd-review__unit__postdate"
                ).text.strip()
                date_str = raw.lstrip("-").strip() or None
            except Exception:
                pass

            rating_val = _parse_doujin_rating_from_unit(unit)

            lines = [s for s in (title, body) if s]
            text = "\n".join(lines)

            if text:
                reviews.append({
                    "rating": rating_val if rating_val else 0,
                    "text": text,
                    "date": date_str,
                    "reviewer": reviewer,
                })

        logging.info(f"取得レビュー件数: {len(reviews)}")

        return reviews

    except Exception as e:
        logging.warning(f"[Doujin Review Parse Error] {product_url} → {repr(e)}")
        return []
