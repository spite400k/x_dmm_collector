"""FANZA Portal 向けコピー。紹介文は AIDMA に統一する。"""

from __future__ import annotations

from typing import Any, Mapping

PROMPT_VERSION = "v7_favorable_review"


def portal_copy_prompt_section(framework: str = "aidma") -> str:
    """Portal コピーは常に AIDMA で書く。framework は呼び出し互換のため残す。"""
    del framework
    field_name = "portal_copy_aidma"
    body = """
■ portal_copy_aidma（AIDMA法: Attention→Interest→Desire→Memory→Action）
・280〜380文字
・冒頭フック → 興味 → 欲求 → 覚えやすい一言 → FANZA公式で確認を促すCTA
・ランキング・発見・クリック向きトーン
""".strip()
    return f"""
【FANZA Portal 向けコピー】
あらすじ・レビュー・作品情報のみを根拠に、{field_name} だけを生成する。

{body}

【Portal コピー共通禁止】
・過度に露骨な描写、創作・推測、レビューにない事実の追加
・「本作」「この作品」などのテンプレ導入、SEOキーワード羅列
""".strip()


def assigned_portal_copy_field(content_id: str | None) -> tuple[str, str]:
    """生成する Portal コピー。常に AIDMA。"""
    del content_id
    return "aidma", "portal_copy_aidma"


def assign_copy_framework(content_id: str) -> str:
    """掲載フレームワーク。常に aidma。content_id は呼び出し互換のため残す。"""
    del content_id
    return "aidma"


def _format_product_context(product: Mapping[str, Any] | None) -> str:
    if not product:
        return "（作品メタ情報なし）"

    lines: list[str] = []
    field_map = (
        ("タイトル", "title"),
        ("出演/サークル", "actress_or_circle"),
        ("ジャンル", "genres"),
        ("カテゴリ", "category"),
        ("価格", "price"),
        ("シリーズ", "series"),
        ("メーカー", "maker"),
        ("ランキング", "ranking_label"),
    )
    for label, key in field_map:
        value = product.get(key)
        if value is None or value == "":
            continue
        if isinstance(value, list):
            value = " / ".join(str(v) for v in value if v)
        lines.append(f"- {label}: {value}")

    return "\n".join(lines) if lines else "（作品メタ情報なし）"


def build_product_context(
    *,
    title: str | None = None,
    genres=None,
    price: int | str | None = None,
    actress_or_circle: str | None = None,
    series: str | None = None,
    maker: str | None = None,
    category: str | None = None,
    ranking_label: str | None = None,
) -> dict[str, Any]:
    genres_text = genres
    if isinstance(genres, list):
        genres_text = " / ".join(str(g) for g in genres if g)
    price_text = f"¥{price}" if price not in (None, "") else None
    return {
        "title": title,
        "genres": genres_text,
        "price": price_text,
        "actress_or_circle": actress_or_circle,
        "series": series,
        "maker": maker,
        "category": category,
        "ranking_label": ranking_label or "該当なし",
    }


def format_product_context_block(product: Mapping[str, Any] | None) -> str:
    return _format_product_context(product)


def pick_portal_copy(insight: Mapping[str, Any], content_id: str) -> tuple[str, str]:
    """掲載用コピーは常に AIDMA。本文が無ければ review_digest。"""
    del content_id
    aidma = (insight.get("portal_copy_aidma") or "").strip()
    if aidma:
        return "aidma", aidma
    fallback = (insight.get("review_digest") or "").strip()
    return "aidma", fallback


def build_product_context_from_row(
    row: Mapping[str, Any],
    service_code: str,
    floor_code: str,
) -> dict[str, Any]:
    actress = row.get("actress")
    actress_or_circle: str | None = None
    if isinstance(actress, list):
        names = []
        for entry in actress:
            if isinstance(entry, str) and entry.strip():
                names.append(entry.strip())
            elif isinstance(entry, dict):
                name = (entry.get("name") or "").strip()
                if name:
                    names.append(name)
        if names:
            actress_or_circle = ", ".join(names)
    elif isinstance(actress, str) and actress.strip():
        actress_or_circle = actress.strip()

    maker = row.get("maker")
    if not actress_or_circle and maker and str(maker).strip():
        actress_or_circle = str(maker).strip()

    return build_product_context(
        title=row.get("title"),
        genres=row.get("genres"),
        price=row.get("price"),
        actress_or_circle=actress_or_circle,
        series=row.get("series"),
        maker=maker,
        category=f"{service_code}/{floor_code}",
    )


def enrich_ai_summary_for_ab(
    summary: dict[str, Any],
    insight: Mapping[str, Any],
    content_id: str,
) -> dict[str, Any]:
    """DB 保存用 dict に Portal A/B フィールドを付与する。"""
    framework, portal_copy = pick_portal_copy(insight, content_id)
    summary["portal_copy_beaf"] = insight.get("portal_copy_beaf")
    summary["portal_copy_aidma"] = insight.get("portal_copy_aidma")
    summary["copy_framework"] = framework
    summary["portal_copy"] = portal_copy or None
    summary["prompt_version"] = PROMPT_VERSION
    return summary
