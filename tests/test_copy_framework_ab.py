import importlib

import pytest


def load_copy_framework_ab():
    return importlib.import_module("utils.copy_framework_ab")


@pytest.fixture
def ab_module():
    return load_copy_framework_ab()


def test_portal_copy_prompt_section_is_always_aidma(ab_module):
    for framework in ("beaf", "aidma"):
        text = ab_module.portal_copy_prompt_section(framework)
        assert "portal_copy_aidma" in text
        assert "AIDMA" in text
        assert "portal_copy_beaf" not in text
        assert "BEAF" not in text
    assigned, field = ab_module.assigned_portal_copy_field("cid-1")
    assert assigned == "aidma"
    assert field == "portal_copy_aidma"


def test_assign_copy_framework_is_always_aidma(ab_module):
    assert ab_module.assign_copy_framework("abc123") == "aidma"
    assert ab_module.assign_copy_framework("other-id") == "aidma"


def test_pick_portal_copy_prefers_aidma(ab_module):
    insight = {
        "portal_copy_beaf": "BEAF本文",
        "portal_copy_aidma": "AIDMA本文",
    }
    picked_framework, picked_copy = ab_module.pick_portal_copy(insight, "cid001")
    assert picked_framework == "aidma"
    assert picked_copy == "AIDMA本文"


def test_pick_portal_copy_falls_back_when_assigned_empty(ab_module):
    insight = {
        "portal_copy_beaf": "",
        "portal_copy_aidma": "AIDMAのみ",
    }
    framework, copy = ab_module.pick_portal_copy(insight, "cid002")
    assert framework == "aidma"
    assert copy == "AIDMAのみ"


def test_pick_portal_copy_ignores_beaf_and_uses_review_digest(ab_module):
    insight = {
        "portal_copy_beaf": "BEAF本文",
        "review_digest": "分析要約",
    }
    framework, copy = ab_module.pick_portal_copy(insight, "cid003")
    assert framework == "aidma"
    assert copy == "分析要約"


def test_pick_portal_copy_returns_empty_when_texts_missing(ab_module):
    framework, copy = ab_module.pick_portal_copy({}, "cid003b")
    assert framework == "aidma"
    assert copy == ""


def test_enrich_ai_summary_for_ab(ab_module):
    content_id = "cid004"
    insight = {
        "portal_copy_beaf": "BEAF",
        "portal_copy_aidma": "AIDMA",
        "review_digest": "digest",
    }
    summary = {"content_id": content_id, "review_digest": "digest"}
    enriched = ab_module.enrich_ai_summary_for_ab(summary, insight, content_id)
    assert enriched["portal_copy_beaf"] == "BEAF"
    assert enriched["portal_copy_aidma"] == "AIDMA"
    assert enriched["copy_framework"] == "aidma"
    assert enriched["portal_copy"] == "AIDMA"
    assert enriched["prompt_version"] == ab_module.PROMPT_VERSION


def test_build_product_context_from_row(ab_module):
    row = {
        "title": "作品タイトル",
        "genres": ["OL", "企画"],
        "price": 2180,
        "actress": [{"name": "女優A"}],
        "series": "シリーズX",
        "maker": "メーカーY",
    }
    ctx = ab_module.build_product_context_from_row(row, "digital", "videoa")
    block = ab_module.format_product_context_block(ctx)
    assert "作品タイトル" in block
    assert "女優A" in block
    assert "¥2180" in block
    assert "digital/videoa" in block
