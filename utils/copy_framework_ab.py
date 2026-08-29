"""FANZA Portal 向け BEAF / AIDMA コピーの A/B テスト支援。"""

from __future__ import annotations

import hashlib
from typing import Any, Mapping

PROMPT_VERSION = "v4_beaf_aidma_ab"

PORTAL_COPY_PROMPT_SECTION = """
【FANZA Portal 向けコピー（A/B テスト用・両方必須）】
あらすじ・レビュー・作品情報のみを根拠に、次の2形式を**両方**生成する。

■ portal_copy_beaf（BEAF法: Benefit→Evidence→Advantage→Feature）
・280〜380文字
・便益（誰向け・何が得か）→ 根拠（レビュー傾向・具体魅力）→ 差別化 → スペック（価格・出演・ジャンル）
・比較検討向きの説明的トーン

■ portal_copy_aidma（AIDMA法: Attention→Interest→Desire→Memory→Action）
・280〜380文字
・冒頭フック → 興味 → 欲求 → 覚えやすい一言 → FANZA公式で確認を促すCTA
・ランキング・発見・クリック向きトーン

【Portal コピー共通禁止】
・過度に露骨な描写、創作・推測、レビューにない事実の追加
・「本作」「この作品」などのテンプレ導入、SEOキーワード羅列
"""


def assign_copy_framework(content_id: str) -> str:
    """content_id から安定した 50/50 割当（beaf / aidma）。"""
    digest = hashlib.md5(content_id.encode("utf-8")).hexdigest()
    return "beaf" if int(digest, 16) % 2 == 0 else "aidma"


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
    """割当フレームワークと掲載用コピー（portal_copy）を返す。"""
    beaf = (insight.get("portal_copy_beaf") or "").strip()
    aidma = (insight.get("portal_copy_aidma") or "").strip()
    framework = assign_copy_framework(content_id)

    if not beaf and not aidma:
        fallback = (insight.get("review_digest") or "").strip()
        return framework, fallback

    if framework == "beaf":
        if beaf:
            return "beaf", beaf
        return "aidma", aidma

    if aidma:
        return "aidma", aidma
    return "beaf", beaf


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
