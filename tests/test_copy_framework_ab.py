import importlib

import pytest


def load_copy_framework_ab():
    return importlib.import_module("utils.copy_framework_ab")


@pytest.fixture
def ab_module():
    return load_copy_framework_ab()


def test_assign_copy_framework_is_stable(ab_module):
    assert ab_module.assign_copy_framework("abc123") == ab_module.assign_copy_framework("abc123")
    assert ab_module.assign_copy_framework("abc123") in ("beaf", "aidma")


def test_pick_portal_copy_prefers_assigned_variant(ab_module):
    content_id = "cid001"
    framework = ab_module.assign_copy_framework(content_id)
    beaf = "BEAF本文"
    aidma = "AIDMA本文"
    insight = {
        "portal_copy_beaf": beaf,
        "portal_copy_aidma": aidma,
    }
    picked_framework, picked_copy = ab_module.pick_portal_copy(insight, content_id)
    assert picked_framework == framework
    if framework == "beaf":
        assert picked_copy == beaf
    else:
        assert picked_copy == aidma


def test_pick_portal_copy_falls_back_when_assigned_empty(ab_module):
    insight = {
        "portal_copy_beaf": "",
        "portal_copy_aidma": "AIDMAのみ",
    }
    framework, copy = ab_module.pick_portal_copy(insight, "cid002")
    assert framework == "aidma"
    assert copy == "AIDMAのみ"


def test_pick_portal_copy_uses_review_digest_when_portal_copies_missing(ab_module):
    insight = {"review_digest": "分析要約"}
    framework, copy = ab_module.pick_portal_copy(insight, "cid003")
    assert framework in ("beaf", "aidma")
    assert copy == "分析要約"


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
    assert enriched["copy_framework"] in ("beaf", "aidma")
    assert enriched["portal_copy"] in ("BEAF", "AIDMA")
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
