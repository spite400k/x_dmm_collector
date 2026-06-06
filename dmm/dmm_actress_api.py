import logging
import os
import re
import time
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

from db.storageS3 import S3_PUBLIC_BASE_URL, upload_actress_image_to_s3
from dmm.minnano_actress_api import enrich_with_minnano
from dmm.wikipedia_actress_api import enrich_with_wikipedia
from dmm.wikidata_actress_api import enrich_with_wikidata
from utils.logger import setup_logger

os.makedirs("logs", exist_ok=True)
setup_logger("dmm_actress_api.log")

DMM_API_ID = os.getenv("DMM_API_ID")
DMM_AFFILIATE_ID = os.getenv("DMM_AFFILIATE_ID")
ACTRESS_SEARCH_URL = "https://api.dmm.com/affiliate/v3/ActressSearch"
ITEM_LIST_URL = "https://api.dmm.com/affiliate/v3/ItemList"
OSUSUME_PROFILE_URL = "https://osusume.dmm.co.jp/list/?actress={actress_id}"

AGE_CHECK_COOKIE = {"age_check_done": "1"}
DEFAULT_REQUEST_INTERVAL = 1.0
IMAGE_OPTIMIZER_HOST = "image-optimizer.osusume.dmm.co.jp"
DEFAULT_ACTRESS_IMAGE_WIDTH = int(os.getenv("ACTRESS_IMAGE_WIDTH", "800"))


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


def _normalize_text(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text or None


def _to_int(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_iso_date(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    try:
        if "T" in value:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
        return datetime.strptime(value[:10], "%Y-%m-%d").date().isoformat()
    except ValueError:
        return None


def _extract_image_filename(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    path = urlparse(url).path.rstrip("/")
    filename = path.split("/")[-1]
    if filename.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
        return filename
    return None


def build_high_res_image_download_url(
    *,
    image_source_url: Optional[str] = None,
    api_image_url: Optional[str] = None,
    width: int = DEFAULT_ACTRESS_IMAGE_WIDTH,
) -> Optional[str]:
    filename = None
    if image_source_url and IMAGE_OPTIMIZER_HOST in image_source_url:
        filename = _extract_image_filename(image_source_url)
    if not filename and api_image_url:
        filename = _extract_image_filename(api_image_url)
    if not filename:
        return None
    return f"https://{IMAGE_OPTIMIZER_HOST}/actress/{filename}/width={width}"


def _is_hosted_actress_image(url: Optional[str]) -> bool:
    if not url:
        return False
    if S3_PUBLIC_BASE_URL and url.startswith(S3_PUBLIC_BASE_URL.rstrip("/")):
        return True
    return "/actress/" in url and "amazonaws.com" in url


def _upload_actress_image(record: dict) -> dict:
    actress_id = record.get("actress_id")
    if not actress_id:
        return record

    current_image_url = record.get("image_url")
    if _is_hosted_actress_image(current_image_url):
        logging.info("[IMAGE] 自前ストレージ済みのためスキップ actress_id=%s", actress_id)
        return record

    download_url = build_high_res_image_download_url(
        image_source_url=record.pop("image_source_url", None),
        api_image_url=current_image_url,
    )
    if not download_url:
        logging.warning("[IMAGE] 高解像度画像URLを生成できません actress_id=%s", actress_id)
        return record

    public_url = upload_actress_image_to_s3(actress_id, download_url)
    if public_url:
        record["image_url"] = public_url
    return record


def _extract_alias(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    match = re.search(r"[（(]([^）)]+)[）)]", name)
    return match.group(1).strip() if match else None


def _extract_x_account(soup: BeautifulSoup) -> Optional[str]:
    for anchor in soup.find_all("a", href=True):
        parsed = urlparse(anchor["href"])
        if parsed.netloc not in ("x.com", "twitter.com", "www.x.com", "www.twitter.com"):
            continue
        username = parsed.path.strip("/").split("/")[0]
        if username and username not in ("intent", "share", "home"):
            return username
    return None


def _extract_section_text(soup: BeautifulSoup, section_id: str) -> Optional[str]:
    heading = soup.find(id=section_id)
    if not heading:
        return None

    parts: list[str] = []
    for sibling in heading.find_next_siblings():
        if sibling.name in ("h2", "h3"):
            break
        text = sibling.get_text("\n", strip=True)
        if text:
            parts.append(text)
    return "\n".join(parts).strip() or None


def _extract_debut_date(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    match = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", text)
    if not match:
        return None
    year, month, day = match.groups()
    return f"{year}-{int(month):02d}-{int(day):02d}"


def _extract_favorite_count(text: str) -> Optional[int]:
    patterns = [
        r"お気に入り登録[^\d]{0,20}(\d[\d,]*)",
        r"(\d[\d,]*)人がお気に入り",
        r'favorite_count\\":(\d+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return _to_int(match.group(1).replace(",", ""))
    return None


def _extract_embedded_field(html: str, field_name: str) -> Optional[str]:
    pattern = rf'{re.escape(field_name)}\\":\\"((?:\\\\.|[^"\\])*)\\"'
    match = re.search(pattern, html)
    if not match:
        pattern = rf'{re.escape(field_name)}\\":(\d+)'
        match = re.search(pattern, html)
        if match:
            return match.group(1)
        return None
    return match.group(1).replace("\\\\n", "\n").replace('\\"', '"')


def _dmm_get(url: str, params: dict) -> dict:
    response = requests.get(url, params=params, timeout=20)
    response.raise_for_status()
    payload = response.json()
    result = payload.get("result", {})
    if str(result.get("status")) != "200":
        message = result.get("message", "unknown error")
        raise Exception(f"API error: {message}")
    return result


def _normalize_actress_name(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    normalized = re.sub(r"\s+", "", str(name).strip())
    return normalized or None


def is_unenrichable_name(name: Optional[str]) -> bool:
    normalized = _normalize_actress_name(name)
    if not normalized:
        return True
    return normalized in {"----", "-", "不明", "unknown", "なし"}


def fetch_actress_by_id(actress_id: int | str) -> Optional[dict]:
    result = _dmm_get(
        ACTRESS_SEARCH_URL,
        {
            "api_id": DMM_API_ID,
            "affiliate_id": DMM_AFFILIATE_ID,
            "actress_id": str(actress_id),
            "output": "json",
        },
    )
    actresses = result.get("actress") or []
    if not actresses:
        logging.warning("[API] 女優が見つかりません actress_id=%s", actress_id)
        return None
    return actresses[0]


def fetch_actress_by_keyword(name: str) -> Optional[dict]:
    if is_unenrichable_name(name):
        return None

    keyword = _normalize_actress_name(name)
    if not keyword or len(keyword) < 2:
        return None

    result = _dmm_get(
        ACTRESS_SEARCH_URL,
        {
            "api_id": DMM_API_ID,
            "affiliate_id": DMM_AFFILIATE_ID,
            "keyword": keyword,
            "hits": 10,
            "offset": 1,
            "output": "json",
        },
    )
    actresses = result.get("actress") or []
    if not actresses:
        logging.warning("[API] キーワード検索で女優が見つかりません keyword=%s", keyword)
        return None

    for actress in actresses:
        api_name = _normalize_actress_name(actress.get("name"))
        api_ruby = _normalize_actress_name(actress.get("ruby"))
        if api_name == keyword or api_ruby == keyword:
            logging.info(
                "[API] キーワード検索で一致 actress_id=%s name=%s",
                actress.get("id"),
                actress.get("name"),
            )
            return actress

    logging.warning("[API] キーワード検索の候補に一致なし keyword=%s", keyword)
    return None


def fetch_works_count(actress_id: int | str) -> Optional[int]:
    result = _dmm_get(
        ITEM_LIST_URL,
        {
            "api_id": DMM_API_ID,
            "affiliate_id": DMM_AFFILIATE_ID,
            "site": "FANZA",
            "service": "digital",
            "floor": "videoa",
            "article": "actress",
            "article_id": str(actress_id),
            "hits": 1,
            "offset": 1,
            "output": "json",
        },
    )
    return _to_int(result.get("total_count"))


def scrape_osusume_profile(actress_id: int | str, *, session: Optional[requests.Session] = None) -> dict:
    own_session = session is None
    session = session or _create_session()
    url = OSUSUME_PROFILE_URL.format(actress_id=actress_id)

    try:
        try:
            response = session.get(url, timeout=20, allow_redirects=True)
            response.raise_for_status()
        except requests.RequestException as exc:
            if getattr(exc, "response", None) is not None and exc.response.status_code == 404:
                logging.warning("[SCRAPE] プロフィールページなし actress_id=%s", actress_id)
            else:
                logging.error("[SCRAPE] プロフィール取得失敗 actress_id=%s: %s", actress_id, exc)
            return {}

        html = response.text
        soup = BeautifulSoup(html, "html.parser")

        profile = _normalize_text(_extract_embedded_field(html, "profile")) or _extract_section_text(
            soup, "profile-detail"
        )
        career_text = _normalize_text(
            _extract_embedded_field(html, "background_and_personality")
        ) or _extract_section_text(soup, "personality")
        fanza_activity = _normalize_text(_extract_embedded_field(html, "product_and_award"))
        awards = _extract_section_text(soup, "award")
        x_account = _extract_x_account(soup)

        debut_date = _parse_iso_date(_extract_embedded_field(html, "activity_period_from"))
        if not debut_date:
            debut_date = _extract_debut_date(career_text)

        favorite_count = _to_int(_extract_embedded_field(html, "favorite_count"))
        if favorite_count is None:
            favorite_count = _extract_favorite_count(html)

        return {
            "profile": profile,
            "career_text": career_text,
            "fanza_activity": fanza_activity,
            "awards": awards,
            "x_account": x_account,
            "debut_date": debut_date,
            "favorite_count": favorite_count,
            "name_en": _normalize_text(_extract_embedded_field(html, "name_en")),
            "alias": _normalize_text(_extract_embedded_field(html, "alias")),
            "image_source_url": _normalize_text(_extract_embedded_field(html, "image_url")),
        }
    finally:
        if own_session:
            session.close()


def map_api_actress_to_record(api_actress: dict) -> dict:
    image_url = None
    image_info = api_actress.get("imageURL") or {}
    if isinstance(image_info, dict):
        image_url = image_info.get("large") or image_info.get("small")

    name = _normalize_text(api_actress.get("name"))
    return {
        "actress_id": _to_int(api_actress.get("id")),
        "name": name,
        "name_kana": _normalize_text(api_actress.get("ruby")),
        "image_url": _normalize_text(image_url),
        "bust": _to_int(api_actress.get("bust")),
        "cup": _normalize_text(api_actress.get("cup")),
        "waist": _to_int(api_actress.get("waist")),
        "hip": _to_int(api_actress.get("hip")),
        "height": _to_int(api_actress.get("height")),
        "birthday": _parse_iso_date(api_actress.get("birthday")),
        "blood_type": _normalize_text(api_actress.get("blood_type")),
        "hobby": _normalize_text(api_actress.get("hobby")),
        "prefectures": _normalize_text(api_actress.get("prefectures")),
        "alias": _extract_alias(name),
    }


def _merge_scrape_and_works(
    record: dict,
    actress_id: int | str,
    *,
    session: Optional[requests.Session],
) -> dict:
    scrape_data = scrape_osusume_profile(actress_id, session=session)
    for key, value in scrape_data.items():
        if value not in (None, ""):
            if key == "alias" and record.get("alias"):
                continue
            record[key] = value

    works_count = fetch_works_count(actress_id)
    if works_count:
        record["works_count"] = works_count
    return record


def enrich_actress(
    actress_id: int | str,
    *,
    name: Optional[str] = None,
    session: Optional[requests.Session] = None,
    request_interval: float = DEFAULT_REQUEST_INTERVAL,
) -> Optional[dict]:
    api_actress = fetch_actress_by_id(actress_id)
    if not api_actress and name:
        api_actress = fetch_actress_by_keyword(name)

    if api_actress:
        record = map_api_actress_to_record(api_actress)
        target_id = record.get("actress_id") or actress_id
        record = _merge_scrape_and_works(record, target_id, session=session)
    else:
        record = {"actress_id": _to_int(actress_id)}
        record = _merge_scrape_and_works(record, actress_id, session=session)
        if len(record) <= 1:
            return None

    record = _upload_actress_image(record)
    record, wiki_title = enrich_with_wikidata(record, actress_id, request_interval=0)
    record = enrich_with_wikipedia(
        record,
        name=name or record.get("name"),
        wiki_title=wiki_title,
        request_interval=0,
    )
    record = enrich_with_minnano(
        record,
        name=name or record.get("name"),
        session=session,
        request_interval=0,
    )

    if request_interval > 0:
        time.sleep(request_interval)

    return record
