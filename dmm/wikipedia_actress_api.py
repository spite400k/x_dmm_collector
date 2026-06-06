import logging
import os
import re
import time
from typing import Any, Optional
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

from dmm.actress_merge import merge_supplement_record
from utils.logger import setup_logger

setup_logger("wikipedia_actress_api.log")

WIKIPEDIA_API_URL = "https://ja.wikipedia.org/w/api.php"
WIKIPEDIA_SUMMARY_URL = "https://ja.wikipedia.org/api/rest_v1/page/summary/{title}"
USER_AGENT = os.getenv(
    "WIKIDATA_USER_AGENT",
    "x_dmm_collector/1.0 (https://github.com/local/x_dmm_collector; batch enrichment)",
)
DEFAULT_REQUEST_INTERVAL = float(os.getenv("WIKIPEDIA_REQUEST_INTERVAL", "0.5"))
CAREER_SECTION_KEYWORDS = ("来歴", "経歴", "略歴", "デビュー", "人物", "生平")
LEAD_SECTION_KEYWORDS = ("概要", "人物", "経歴")


def _normalize_text(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text or None


def _normalize_actress_name(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    normalized = re.sub(r"\s+", "", str(name).strip())
    return normalized or None


def _wikipedia_get(params: dict) -> dict:
    response = requests.get(
        WIKIPEDIA_API_URL,
        params={**params, "format": "json"},
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def search_wikipedia_title(name: str) -> Optional[str]:
    keyword = _normalize_actress_name(name)
    if not keyword:
        return None

    payload = _wikipedia_get(
        {
            "action": "opensearch",
            "search": keyword,
            "limit": 5,
            "namespace": 0,
            "redirects": "resolve",
        }
    )
    titles = payload[1] if len(payload) > 1 else []
    if not titles:
        logging.info("[WIKIPEDIA] 記事が見つかりません name=%s", keyword)
        return None

    for title in titles:
        if _normalize_actress_name(title) == keyword:
            logging.info("[WIKIPEDIA] 記事一致 name=%s title=%s", keyword, title)
            return title

    logging.info("[WIKIPEDIA] 先頭記事を使用 name=%s title=%s", keyword, titles[0])
    return titles[0]


def fetch_wikipedia_summary(title: str) -> Optional[str]:
    url = WIKIPEDIA_SUMMARY_URL.format(title=quote(title, safe=""))
    try:
        response = requests.get(
            url,
            timeout=20,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return _normalize_text(response.json().get("extract"))
    except requests.RequestException as exc:
        logging.warning("[WIKIPEDIA] 要約取得失敗 title=%s: %s", title, exc)
        return None


def _list_wikipedia_sections(title: str) -> list[dict]:
    payload = _wikipedia_get({"action": "parse", "page": title, "prop": "sections"})
    return payload.get("parse", {}).get("sections", [])


def _fetch_wikipedia_section_text(title: str, section_index: str) -> Optional[str]:
    payload = _wikipedia_get(
        {
            "action": "parse",
            "page": title,
            "prop": "text",
            "section": section_index,
        }
    )
    html = payload.get("parse", {}).get("text", {}).get("*")
    if not html:
        return None
    text = BeautifulSoup(html, "html.parser").get_text("\n", strip=True)
    return _normalize_text(text)


def fetch_wikipedia_career_text(title: str) -> Optional[str]:
    sections = _list_wikipedia_sections(title)
    parts: list[str] = []

    for section in sections:
        heading = _normalize_text(section.get("line")) or ""
        if not any(keyword in heading for keyword in CAREER_SECTION_KEYWORDS):
            continue
        section_text = _fetch_wikipedia_section_text(title, str(section.get("index")))
        if section_text:
            parts.append(f"【{heading}】\n{section_text}")

    if not parts:
        return None
    return "\n\n".join(parts)


def fetch_wikipedia_lead_text(title: str) -> Optional[str]:
    summary = fetch_wikipedia_summary(title)
    if summary:
        return summary

    sections = _list_wikipedia_sections(title)
    for section in sections:
        heading = _normalize_text(section.get("line")) or ""
        if section.get("level") != "2":
            continue
        if heading in CAREER_SECTION_KEYWORDS and heading not in LEAD_SECTION_KEYWORDS:
            continue
        section_text = _fetch_wikipedia_section_text(title, str(section.get("index")))
        if section_text:
            return section_text
    return None


def fetch_actress_from_wikipedia(
    name: Optional[str],
    *,
    wiki_title: Optional[str] = None,
) -> Optional[dict]:
    title = wiki_title or (search_wikipedia_title(name) if name else None)
    if not title:
        return None

    record: dict[str, Any] = {"_wiki_title": title}
    profile = fetch_wikipedia_lead_text(title)
    career_text = fetch_wikipedia_career_text(title)

    if profile:
        record["profile"] = profile
    if career_text:
        record["career_text"] = career_text

    record = {key: value for key, value in record.items() if value not in (None, "")}
    if len(record) <= 1:
        logging.info("[WIKIPEDIA] 文章データなし title=%s", title)
        return None

    logging.info(
        "[WIKIPEDIA] 取得成功 title=%s fields=%s",
        title,
        [key for key in record.keys() if not key.startswith("_")],
    )
    return record


def enrich_with_wikipedia(
    record: dict,
    *,
    name: Optional[str] = None,
    wiki_title: Optional[str] = None,
    request_interval: float = DEFAULT_REQUEST_INTERVAL,
) -> dict:
    wiki_record = fetch_actress_from_wikipedia(name, wiki_title=wiki_title)
    merged = merge_supplement_record(record, wiki_record)
    if request_interval > 0:
        time.sleep(request_interval)
    return merged
