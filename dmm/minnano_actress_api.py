import logging
import os
import re
import time
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

from dmm.actress_merge import merge_supplement_record
from utils.logger import setup_logger

setup_logger("minnano_actress_api.log")

MINNANO_BASE_URL = "https://www.minnano-av.com"
MINNANO_SEARCH_URL = f"{MINNANO_BASE_URL}/search_result.php"
USER_AGENT = os.getenv(
    "MINNANO_USER_AGENT",
    "x_dmm_collector/1.0 (https://github.com/local/x_dmm_collector; batch enrichment)",
)
DEFAULT_REQUEST_INTERVAL = float(os.getenv("MINNANO_REQUEST_INTERVAL", "1.0"))

SIZE_PATTERN = re.compile(
    r"T(?P<height>\d+)\s*/\s*B(?P<bust>\d+)\(\s*(?P<cup>[A-Z]+)カップ\s*\)\s*/\s*W(?P<waist>\d+)\s*/\s*H(?P<hip>\d+)",
    re.IGNORECASE,
)
BIRTHDAY_PATTERN = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")
DEBUT_DATE_PATTERN = re.compile(r"(\d{4})年(\d{1,2})月\s*(\d{1,2})日")
ACTRESS_PAGE_PATTERN = re.compile(r"actress\d+\.html", re.IGNORECASE)


def _normalize_text(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


def _normalize_actress_name(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    return re.sub(r"\s+", "", str(name).strip()) or None


def _to_int(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_birthday(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    match = BIRTHDAY_PATTERN.search(text)
    if not match:
        return None
    year, month, day = match.groups()
    return f"{year}-{int(month):02d}-{int(day):02d}"


def _parse_debut_date(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    match = DEBUT_DATE_PATTERN.search(text)
    if not match:
        return None
    year, month, day = match.groups()
    return f"{year}-{int(month):02d}-{int(day):02d}"


def _parse_size(text: Optional[str]) -> dict[str, Any]:
    if not text:
        return {}
    match = SIZE_PATTERN.search(text)
    if not match:
        return {}
    return {
        "height": _to_int(match.group("height")),
        "bust": _to_int(match.group("bust")),
        "cup": match.group("cup").upper(),
        "waist": _to_int(match.group("waist")),
        "hip": _to_int(match.group("hip")),
    }


def _extract_alias(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    match = re.search(r"[（(]([^）)]+)[）)]", text)
    if match:
        inner = match.group(1).strip()
        inner = re.split(r"/", inner)[0].strip()
        return inner or None
    return _normalize_text(text)


def _extract_x_account(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    if "twitter.com" in text or "x.com" in text:
        parsed = urlparse(text if text.startswith("http") else f"https://{text}")
        username = parsed.path.strip("/").split("/")[0]
        if username and username not in ("intent", "share", "home"):
            return username
    if text.startswith("@"):
        return text.lstrip("@")
    return None


def _extract_name_en(title_text: Optional[str]) -> Optional[str]:
    if not title_text:
        return None
    match = re.search(r"/\s*([A-Za-z][A-Za-z\s.'-]+)$", title_text)
    return _normalize_text(match.group(1)) if match else None


def _normalize_blood_type(value: Optional[str]) -> Optional[str]:
    text = _normalize_text(value)
    if not text:
        return None
    return text[:-1] if text.endswith("型") else text


def _parse_profile_rows(soup: BeautifulSoup) -> dict[str, str]:
    rows: dict[str, str] = {}
    for tr in soup.find_all("tr"):
        label_tag = tr.find("span")
        value_tag = tr.find("p")
        if not label_tag or not value_tag:
            continue
        label = _normalize_text(label_tag.get_text())
        value = _normalize_text(value_tag.get_text(" ", strip=True))
        if label and value:
            rows[label] = value
    return rows


def _find_profile_url(name: str, *, session: requests.Session) -> Optional[str]:
    keyword = _normalize_actress_name(name)
    if not keyword:
        return None

    response = session.get(
        MINNANO_SEARCH_URL,
        params={"search_scope": "actress", "search_word": keyword},
        timeout=20,
        allow_redirects=True,
    )
    response.raise_for_status()

    if ACTRESS_PAGE_PATTERN.search(response.url):
        return response.url

    soup = BeautifulSoup(response.text, "html.parser")
    candidates: list[tuple[str, str]] = []
    for anchor in soup.select("a[href]"):
        href = anchor.get("href", "")
        if not ACTRESS_PAGE_PATTERN.search(href):
            continue
        text = _normalize_actress_name(anchor.get_text())
        if not text:
            continue
        candidates.append((urljoin(MINNANO_BASE_URL, href), text))

    for url, text in candidates:
        if text == keyword:
            return url

    if len(candidates) == 1:
        return candidates[0][0]

    logging.warning("[MINNANO] 記事候補が特定できません name=%s count=%d", keyword, len(candidates))
    return None


def scrape_minnano_profile(profile_url: str, *, session: requests.Session) -> Optional[dict]:
    response = session.get(profile_url, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    h1 = soup.find("h1")
    title_text = h1.get_text(" ", strip=True) if h1 else None
    rows = _parse_profile_rows(soup)

    record: dict[str, Any] = {
        "name_en": _extract_name_en(title_text),
        "alias": _extract_alias(rows.get("別名")),
        "birthday": _parse_birthday(rows.get("生年月日")),
        "blood_type": _normalize_blood_type(rows.get("血液型")),
        "prefectures": rows.get("出身地"),
        "hobby": rows.get("趣味・特技"),
        "fanza_activity": rows.get("AV出演期間"),
        "debut_date": _parse_debut_date(rows.get("デビュー作品")),
        "x_account": _extract_x_account(rows.get("ブログ")),
    }
    record.update(_parse_size(rows.get("サイズ")))

    career_parts = []
    if rows.get("デビュー作品"):
        career_parts.append(f"デビュー作品: {rows['デビュー作品']}")
    if rows.get("AV出演期間"):
        career_parts.append(f"AV出演期間: {rows['AV出演期間']}")
    if rows.get("所属事務所"):
        career_parts.append(f"所属事務所: {rows['所属事務所']}")
    if career_parts:
        record["career_text"] = "\n".join(career_parts)

    meta_description = soup.find("meta", attrs={"name": "description"})
    if meta_description and meta_description.get("content"):
        record["profile"] = _normalize_text(meta_description["content"])

    record = {
        key: value
        for key, value in record.items()
        if value not in (None, "")
    }
    if not record:
        return None

    logging.info(
        "[MINNANO] 取得成功 url=%s fields=%s",
        profile_url,
        list(record.keys()),
    )
    return record


def fetch_actress_from_minnano(
    name: Optional[str],
    *,
    session: Optional[requests.Session] = None,
) -> Optional[dict]:
    if not name:
        return None

    own_session = session is None
    session = session or requests.Session()
    session.headers.setdefault("User-Agent", USER_AGENT)
    session.cookies.set("age_check_done", "1", domain=".minnano-av.com")

    try:
        profile_url = _find_profile_url(name, session=session)
        if not profile_url:
            logging.info("[MINNANO] プロフィールページなし name=%s", name)
            return None
        return scrape_minnano_profile(profile_url, session=session)
    except requests.RequestException as exc:
        logging.error("[MINNANO] 取得失敗 name=%s: %s", name, exc)
        return None
    finally:
        if own_session:
            session.close()


def enrich_with_minnano(
    record: dict,
    *,
    name: Optional[str] = None,
    session: Optional[requests.Session] = None,
    request_interval: float = DEFAULT_REQUEST_INTERVAL,
) -> dict:
    minnano_record = fetch_actress_from_minnano(name, session=session)
    merged = merge_supplement_record(record, minnano_record)
    if request_interval > 0:
        time.sleep(request_interval)
    return merged
