import base64
import json
import logging
import os
import re
from typing import Optional
from urllib.parse import parse_qs, unquote, urlencode, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from utils.logger import setup_logger

load_dotenv()

os.makedirs("logs", exist_ok=True)
setup_logger("dmm_campaign_api.log")

CDS_LITE_API = "https://api.cds.dmm.co.jp/v1/delivers/lite"
AFFILIATE_LINK_BASE = "https://al.fanza.co.jp/"
DMM_AFFILIATE_LINK_ID = os.getenv("DMM_AFFILIATE_ID")
AGE_CHECK_COOKIE = {"age_check_done": "1"}

DMM_URL_PATTERN = re.compile(
    r"^https?://([^/]+\.)?(dmm\.co\.jp|dmm\.com|fanza\.jp)(/|$)",
    re.I,
)

SERVICE_FLOOR_PATTERNS = [
    (re.compile(r"dc/doujin|/doujin/", re.I), "doujin", "digital_doujin"),
    (re.compile(r"book\.dmm\.co\.jp/book", re.I), "ebook", "all"),
    (re.compile(r"book\.dmm\.co\.jp/comic|/ebook/.*comic", re.I), "ebook", "comic"),
    (re.compile(r"book\.dmm\.co\.jp/novel", re.I), "ebook", "novel"),
    (re.compile(r"book\.dmm\.co\.jp/photo", re.I), "ebook", "photo"),
    (re.compile(r"video\.dmm\.co\.jp/amateur|videoc", re.I), "digital", "videoc"),
    (re.compile(r"video\.dmm\.co\.jp/av|videoa", re.I), "digital", "videoa"),
    (re.compile(r"video\.dmm\.co\.jp/anime|/anime/", re.I), "digital", "anime"),
    (re.compile(r"pcgame|digital_pcgame", re.I), "pcgame", "digital_pcgame"),
]

CAMPAIGN_SOURCES = [
    {"name": "top", "url": "https://www.dmm.co.jp/top/", "service": "all", "floor": "all"},
    {"name": "doujin", "url": "https://www.dmm.co.jp/dc/doujin/-/list/", "service": "doujin", "floor": "digital_doujin"},
    {"name": "comic", "url": "https://book.dmm.co.jp/list/", "service": "ebook", "floor": "comic"},
    {"name": "videoa", "url": "https://video.dmm.co.jp/av/", "service": "digital", "floor": "videoa"},
    {"name": "videoc", "url": "https://video.dmm.co.jp/amateur/", "service": "digital", "floor": "videoc"},
    {"name": "anime", "url": "https://video.dmm.co.jp/anime/", "service": "digital", "floor": "anime"},
    {"name": "novel", "url": "https://book.dmm.co.jp/novel/", "service": "ebook", "floor": "novel"},
    {
        "name": "100yen-sale",
        "url": "https://video.dmm.co.jp/list/?key=%E5%86%86%E3%82%BB%E3%83%BC%E3%83%AB",
        "service": "digital",
        "floor": "all",
        "is_feature_page": True,
        "title": "100円セール",
    },
]

# FANZAブックス特集ページの自動検出用シード
BOOK_FEATURE_DISCOVERY_SEEDS = [
    "https://book.dmm.co.jp/list/",
    "https://book.dmm.co.jp/book/feature/picks-sale/pre-summer/",
]

BOOK_FEATURE_PATH_PATTERN = re.compile(
    r"(?:https?://book\.dmm\.co\.jp)?(/book/feature/[a-zA-Z0-9][a-zA-Z0-9_./-]*)",
    re.I,
)

VIDEO_TOP_URL = "https://video.dmm.co.jp/"
LIST_CAMPAIGN_QUERY_KEYS = ("campaign", "point_campaign")


def _create_session() -> requests.Session:
    session = requests.Session()
    for key, value in AGE_CHECK_COOKIE.items():
        session.cookies.set(key, value, domain=".dmm.co.jp")
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        }
    )
    return session


def infer_service_floor(url: str, default_service: str = "all", default_floor: str = "all") -> tuple[str, str]:
    for pattern, service, floor in SERVICE_FLOOR_PATTERNS:
        if pattern.search(url):
            return service, floor
    return default_service, default_floor


def _extract_deliver_ids(html: str) -> set[str]:
    deliver_ids = set()
    deliver_ids.update(re.findall(r'data-cds-deliver-api-deliver-ids="([^"]+)"', html))
    deliver_ids.update(re.findall(r'class="cds-deliver-tags"[^>]*\ss="([^"]+)"', html))
    return deliver_ids


def resolve_feature_url(url: str) -> str:
    """トラッキング・アフィリエイト URL を実際の遷移先 URL に解決する。"""
    if not url:
        return url

    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    lurl = query.get("lurl", [None])[0]
    if lurl:
        return unquote(lurl)

    return url


def to_affiliate_feature_url(url: str) -> str:
    """DMM 系 URL を al.fanza.co.jp アフィリエイト URL に変換する。"""
    direct_url = resolve_feature_url(url)
    if not DMM_URL_PATTERN.match(direct_url):
        return direct_url
    if not DMM_AFFILIATE_LINK_ID:
        logging.warning("DMM_AFFILIATE_ID 未設定のため URL 変換をスキップ: %s", direct_url)
        return direct_url

    params = urlencode(
        {
            "lurl": direct_url,
            "af_id": DMM_AFFILIATE_LINK_ID,
            "ch": "toolbar",
            "ch_id": "link",
        }
    )
    return f"{AFFILIATE_LINK_BASE}?{params}"


def _decode_tracking_link_url(tracking_url: str) -> Optional[str]:
    match = re.search(r"ic_key=([^&\"']+)", tracking_url)
    if not match:
        return None
    token = match.group(1)
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload))
        return data.get("link_url")
    except Exception:
        return None


def _resolve_feature_url(session: requests.Session, url: str) -> str:
    resolved = resolve_feature_url(url)
    if resolved != url:
        return resolved

    if "tracking.cds.dmm.co.jp" not in url:
        return url

    link_url = _decode_tracking_link_url(url)
    if link_url:
        return resolve_feature_url(link_url)

    try:
        response = session.get(url, timeout=15, allow_redirects=True)
        return resolve_feature_url(response.url)
    except Exception:
        return url


def _fetch_html_with_selenium(url: str) -> Optional[str]:
    """SPA ページ向け。video.dmm.co.jp TOP のセール一覧などは JS 描画が必要。"""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.common.by import By
        from webdriver_manager.chrome import ChromeDriverManager
    except ImportError as exc:
        logging.warning("[WARN] Selenium 未インストールのため video TOP 取得をスキップ: %s", exc)
        return None

    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    try:
        driver.get(url)
        driver.implicitly_wait(8)
        try:
            driver.find_element(By.LINK_TEXT, "はい").click()
            driver.implicitly_wait(5)
        except Exception:
            pass
        return driver.page_source
    except Exception as exc:
        logging.warning("[WARN] Selenium 取得失敗 url=%s: %s", url, exc)
        return None
    finally:
        driver.quit()


def _normalize_video_list_url(url: str) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    kept = {key: query[key][0] for key in LIST_CAMPAIGN_QUERY_KEYS if key in query}
    if not kept:
        return url
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{urlencode(kept)}"


def _parse_video_top_sale_links(html: str, priority_offset: int) -> list[dict]:
    """video.dmm.co.jp TOP の「お得な商品」セールリンクを抽出する。"""
    soup = BeautifulSoup(html, "html.parser")
    campaigns = []
    seen_urls: set[str] = set()

    for index, anchor in enumerate(soup.select("a[href]")):
        title = (anchor.get_text(strip=True) or "").strip()
        href = anchor.get("href", "")
        if not title or not href or len(title) > 80:
            continue

        feature_url = _normalize_video_list_url(urljoin(VIDEO_TOP_URL, href))
        parsed = urlparse(feature_url)
        if "video.dmm.co.jp" not in parsed.netloc:
            continue
        if "/list/" not in parsed.path or "/content/" in parsed.path:
            continue

        query = parse_qs(parsed.query)
        if not any(key in query for key in LIST_CAMPAIGN_QUERY_KEYS):
            continue
        if feature_url in seen_urls:
            continue
        seen_urls.add(feature_url)

        service, floor = infer_service_floor(feature_url, "digital", "all")
        campaigns.append(
            {
                "title": title,
                "description": None,
                "feature_url": feature_url,
                "picture_url": None,
                "type": "sale",
                "service": service,
                "floor": floor,
                "priority": priority_offset + index,
                "is_active": True,
            }
        )

    logging.info("video TOP セールリンクを %d 件検出", len(campaigns))
    return campaigns


def _fetch_video_top_sale_campaigns(priority_offset: int) -> list[dict]:
    html = _fetch_html_with_selenium(VIDEO_TOP_URL)
    if not html:
        return []
    return _parse_video_top_sale_links(html, priority_offset)


def _normalize_book_feature_url(raw: str) -> Optional[str]:
    if not raw or "#" in raw:
        return None

    path = raw
    if path.startswith("http"):
        path = urlparse(path).path

    path = path.split("?")[0]
    if not path.startswith("/book/feature/"):
        return None

    segments = [segment for segment in path.strip("/").split("/") if segment]
    if len(segments) < 3 or segments[1] != "feature":
        return None

    if not path.endswith("/"):
        path += "/"

    return f"https://book.dmm.co.jp{path}"


def _discover_book_feature_urls(session: requests.Session, seed_urls: list[str]) -> list[str]:
    discovered: set[str] = set()

    for seed_url in seed_urls:
        try:
            response = session.get(seed_url, timeout=20)
            response.raise_for_status()
        except Exception as exc:
            logging.warning("[WARN] 特集URL探索失敗 seed=%s: %s", seed_url, exc)
            continue

        for match in BOOK_FEATURE_PATH_PATTERN.findall(response.text):
            normalized = _normalize_book_feature_url(match)
            if normalized:
                discovered.add(normalized)

    logging.info("FANZAブックス特集URLを %d 件検出", len(discovered))
    return sorted(discovered)


def _fetch_book_feature_campaigns(
    session: requests.Session,
    feature_urls: list[str],
    priority_offset: int,
) -> list[dict]:
    campaigns = []

    for index, feature_url in enumerate(feature_urls):
        logging.info("[FETCH] book-feature url=%s", feature_url)
        try:
            response = session.get(feature_url, timeout=20)
            response.raise_for_status()
        except Exception as exc:
            logging.warning("[WARN] 特集ページ取得失敗: %s (%s)", feature_url, exc)
            continue

        feature_campaign = _parse_feature_page(
            response.text,
            response.url,
            default_service="ebook",
            default_floor="all",
            priority_offset=priority_offset + index,
        )
        if feature_campaign:
            campaigns.append(feature_campaign)

    return campaigns


def _meta_content(soup: BeautifulSoup, prop: str) -> Optional[str]:
    tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
    if tag and tag.get("content"):
        return tag["content"].strip()
    return None


def _parse_feature_page(
    html: str,
    page_url: str,
    default_service: str,
    default_floor: str,
    priority_offset: int,
    source: Optional[dict] = None,
) -> Optional[dict]:
    """特集ページ自身を1件のキャンペーンとして取得する。"""
    source = source or {}
    soup = BeautifulSoup(html, "html.parser")

    page_title = soup.title.string.strip() if soup.title and soup.title.string else None
    og_title = _meta_content(soup, "og:title")
    title = source.get("title") or page_title or og_title
    if not title:
        return None

    for suffix in (" - FANZAブックス", " - FANZA", " | FANZA"):
        if suffix in title:
            title = title.split(suffix)[0].strip()
    if title.endswith("..."):
        title = title[:-3].strip()

    picture_url = source.get("picture_url") or _meta_content(soup, "og:image")
    description = (
        source.get("description")
        or _meta_content(soup, "og:description")
        or _meta_content(soup, "description")
    )
    service, floor = infer_service_floor(page_url, default_service, default_floor)

    return {
        "title": title,
        "description": description,
        "feature_url": page_url,
        "picture_url": picture_url,
        "type": "feature",
        "service": service,
        "floor": floor,
        "priority": priority_offset,
        "is_active": True,
    }


def _parse_html_banners(
    session: requests.Session,
    html: str,
    page_url: str,
    default_service: str,
    default_floor: str,
    priority_offset: int,
) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    campaigns = []
    seen_urls: set[str] = set()

    for index, anchor in enumerate(soup.select("a[href]")):
        href = anchor.get("href", "")
        if "tracking.cds.dmm.co.jp" not in href:
            continue
        image = anchor.select_one("img")
        if not image:
            continue

        title = (image.get("alt") or image.get("title") or "").strip()
        picture_url = image.get("src") or image.get("data-src")
        if not title or not picture_url:
            continue

        feature_url = _resolve_feature_url(session, urljoin(page_url, href))
        if feature_url in seen_urls:
            continue
        seen_urls.add(feature_url)

        service, floor = infer_service_floor(feature_url, default_service, default_floor)
        campaigns.append(
            {
                "title": title,
                "description": None,
                "feature_url": feature_url,
                "picture_url": picture_url,
                "type": "banner",
                "service": service,
                "floor": floor,
                "priority": priority_offset + index,
                "is_active": True,
            }
        )

    return campaigns


def _fetch_cds_campaigns(
    session: requests.Session,
    deliver_id: str,
    default_service: str,
    default_floor: str,
    priority_offset: int,
) -> list[dict]:
    response = session.get(
        CDS_LITE_API,
        params={"deliver_ids": deliver_id},
        timeout=20,
        headers={"Referer": "https://www.dmm.co.jp/top/"},
    )
    response.raise_for_status()
    payload = response.json()

    campaigns = []
    for deliver in payload.get("result", []):
        for index, content in enumerate(deliver.get("deliver_contents", [])):
            feature_url = resolve_feature_url(content.get("link_url") or "")
            if not feature_url:
                continue

            title = (content.get("alternative_text") or content.get("text") or "").strip()
            if not title:
                title = feature_url

            creative = content.get("creative") or {}
            picture_url = creative.get("file_url")
            service, floor = infer_service_floor(feature_url, default_service, default_floor)

            campaigns.append(
                {
                    "title": title,
                    "description": content.get("text") or None,
                    "feature_url": feature_url,
                    "picture_url": picture_url,
                    "type": "banner",
                    "service": service,
                    "floor": floor,
                    "priority": priority_offset + index,
                    "is_active": True,
                }
            )

    return campaigns


def fetch_campaigns(sources: Optional[list[dict]] = None) -> list[dict]:
    """DMM/FANZA 各ページからキャンペーン情報を収集する（Session は finally で close）。"""
    session = _create_session()
    try:
        return _fetch_campaigns_with_session(session, sources)
    finally:
        session.close()


def _fetch_campaigns_with_session(
    session: requests.Session,
    sources: Optional[list[dict]] = None,
) -> list[dict]:
    source_list = sources or CAMPAIGN_SOURCES
    merged: list[dict] = []
    seen_feature_urls: set[str] = set()
    deliver_ids_seen: set[str] = set()

    for source_index, source in enumerate(source_list):
        page_url = source["url"]
        default_service = source.get("service", "all")
        default_floor = source.get("floor", "all")
        priority_offset = (source_index + 1) * 100

        logging.info("[FETCH] source=%s url=%s", source.get("name"), page_url)
        try:
            response = session.get(page_url, timeout=20)
            response.raise_for_status()
        except Exception as exc:
            logging.error("[ERROR] ページ取得失敗: %s (%s)", page_url, exc)
            continue

        html = response.text
        page_campaigns = []

        if source.get("is_feature_page"):
            feature_campaign = _parse_feature_page(
                html,
                response.url,
                default_service,
                default_floor,
                priority_offset,
                source=source,
            )
            if feature_campaign:
                page_campaigns.append(feature_campaign)

        page_campaigns.extend(
            _parse_html_banners(
                session,
                html,
                response.url,
                default_service,
                default_floor,
                priority_offset,
            )
        )

        for deliver_id in _extract_deliver_ids(html):
            if deliver_id in deliver_ids_seen:
                continue
            deliver_ids_seen.add(deliver_id)
            try:
                page_campaigns.extend(
                    _fetch_cds_campaigns(
                        session,
                        deliver_id,
                        default_service,
                        default_floor,
                        priority_offset,
                    )
                )
            except Exception as exc:
                logging.warning("[WARN] CDS API 取得失敗 deliver_id=%s: %s", deliver_id, exc)

        for campaign in page_campaigns:
            feature_url = campaign.get("feature_url")
            if not feature_url or feature_url in seen_feature_urls:
                continue
            seen_feature_urls.add(feature_url)
            merged.append(campaign)

    for campaign in _fetch_video_top_sale_campaigns(priority_offset=(len(source_list) + 1) * 100):
        feature_url = campaign.get("feature_url")
        if not feature_url or feature_url in seen_feature_urls:
            continue
        seen_feature_urls.add(feature_url)
        merged.append(campaign)

    book_feature_urls = _discover_book_feature_urls(session, BOOK_FEATURE_DISCOVERY_SEEDS)
    for campaign in _fetch_book_feature_campaigns(
        session,
        book_feature_urls,
        priority_offset=(len(source_list) + 1) * 100,
    ):
        feature_url = campaign.get("feature_url")
        if not feature_url or feature_url in seen_feature_urls:
            continue
        seen_feature_urls.add(feature_url)
        merged.append(campaign)

    logging.info("キャンペーン取得完了: %d 件", len(merged))
    return merged

