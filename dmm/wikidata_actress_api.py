import logging
import os
import time
from typing import Any, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

from dmm.actress_merge import merge_supplement_record
from utils.logger import setup_logger

setup_logger("wikidata_actress_api.log")

WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"
USER_AGENT = os.getenv(
    "WIKIDATA_USER_AGENT",
    "x_dmm_collector/1.0 (https://github.com/local/x_dmm_collector; batch enrichment)",
)
DEFAULT_REQUEST_INTERVAL = float(os.getenv("WIKIDATA_REQUEST_INTERVAL", "0.5"))

_SPARQL_TEMPLATE = """
SELECT ?item ?itemLabel ?itemDescription ?birthDate ?height ?birthPlaceLabel
       ?xUsername ?alias ?enLabel ?bloodTypeLabel ?wikiTitle WHERE {{
  ?item wdt:P9781 "{actress_id}" .
  OPTIONAL {{ ?item wdt:P569 ?birthDate. }}
  OPTIONAL {{ ?item wdt:P2048 ?height. }}
  OPTIONAL {{
    ?item wdt:P19 ?birthPlace .
    ?birthPlace rdfs:label ?birthPlaceLabel .
    FILTER(LANG(?birthPlaceLabel) = "ja")
  }}
  OPTIONAL {{ ?item wdt:P2002 ?xUsername. }}
  OPTIONAL {{ ?item wdt:P742 ?alias. }}
  OPTIONAL {{
    ?item wdt:P1853 ?bloodType .
    ?bloodType rdfs:label ?bloodTypeLabel .
    FILTER(LANG(?bloodTypeLabel) = "ja")
  }}
  OPTIONAL {{
    ?item rdfs:label ?enLabel .
    FILTER(LANG(?enLabel) = "en")
  }}
  OPTIONAL {{
    ?article schema:about ?item ;
             schema:isPartOf <https://ja.wikipedia.org/> ;
             schema:name ?wikiTitle .
  }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "ja,en". }}
}}
LIMIT 5
"""


def _normalize_text(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text or None


def _to_int(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _parse_wikidata_date(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    date_part = value[:10]
    if len(date_part) == 10 and date_part[4] == "-" and date_part[7] == "-":
        return date_part
    return None


def _normalize_blood_type(value: Optional[str]) -> Optional[str]:
    text = _normalize_text(value)
    if not text:
        return None
    return text[:-1] if text.endswith("型") else text


def _binding_value(bindings: list[dict], key: str) -> Optional[str]:
    for row in bindings:
        value = row.get(key, {}).get("value")
        if value not in (None, ""):
            return str(value)
    return None


def fetch_actress_from_wikidata(actress_id: int | str) -> Optional[dict]:
    query = _SPARQL_TEMPLATE.format(actress_id=str(actress_id))
    try:
        response = requests.get(
            WIKIDATA_SPARQL_URL,
            params={"query": query, "format": "json"},
            headers={"User-Agent": USER_AGENT, "Accept": "application/sparql-results+json"},
            timeout=30,
        )
        response.raise_for_status()
        bindings = response.json().get("results", {}).get("bindings", [])
    except requests.RequestException as exc:
        logging.error("[WIKIDATA] SPARQL取得失敗 actress_id=%s: %s", actress_id, exc)
        return None

    if not bindings:
        logging.info("[WIKIDATA] 該当データなし actress_id=%s", actress_id)
        return None

    record: dict[str, Any] = {
        "name_en": _normalize_text(_binding_value(bindings, "enLabel")),
        "birthday": _parse_wikidata_date(_binding_value(bindings, "birthDate")),
        "height": _to_int(_binding_value(bindings, "height")),
        "prefectures": _normalize_text(_binding_value(bindings, "birthPlaceLabel")),
        "x_account": _normalize_text(_binding_value(bindings, "xUsername")),
        "alias": _normalize_text(_binding_value(bindings, "alias")),
        "blood_type": _normalize_blood_type(_binding_value(bindings, "bloodTypeLabel")),
    }

    wiki_title = _binding_value(bindings, "wikiTitle")
    if wiki_title:
        record["_wiki_title"] = wiki_title

    record = {key: value for key, value in record.items() if value not in (None, "")}
    if not record:
        return None

    logging.info(
        "[WIKIDATA] 取得成功 actress_id=%s item=%s fields=%s",
        actress_id,
        _binding_value(bindings, "item"),
        list(record.keys()),
    )
    return record


def merge_wikidata_record(base_record: dict, wikidata_record: Optional[dict]) -> dict:
    return merge_supplement_record(base_record, wikidata_record)


def enrich_with_wikidata(
    record: dict,
    actress_id: int | str,
    *,
    request_interval: float = DEFAULT_REQUEST_INTERVAL,
) -> tuple[dict, Optional[str]]:
    wikidata_record = fetch_actress_from_wikidata(actress_id)
    wiki_title = None
    if wikidata_record:
        wiki_title = wikidata_record.pop("_wiki_title", None)
    merged = merge_wikidata_record(record, wikidata_record)
    if request_interval > 0:
        time.sleep(request_interval)
    return merged, wiki_title
