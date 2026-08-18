"""videoc / video.dmm レビュー抽出の分岐・境界テスト。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from utils import dmm_review_scraper as scraper


AMATEUR_REVIEW_HTML = """
<div id="review">
  <div>総評価数<span>2</span>(2件のコメント)</div>
  <div data-e2eid="review-item">
    <header><span class="font-bold">良い作品</span></header>
    <img src="https://assets.video.dmm.co.jp/icon/star/yellow.svg" width="24" height="24">
    <img src="https://assets.video.dmm.co.jp/icon/star/yellow.svg" width="24" height="24">
    <img src="https://assets.video.dmm.co.jp/icon/star/gray.svg" width="24" height="24">
    <div class="text-xs overflow-hidden break-all"><p>面白かったです。</p></div>
    <a href="https://review.dmm.co.jp/review-front/reviewer/list/abc">太郎さんのレビュー</a>
    <span>-2026/08/13 - 素人(動画)</span>
  </div>
  <div data-e2eid="review-item">
    <header><span class="font-bold">ネタバレのみ</span></header>
    <img src="https://assets.video.dmm.co.jp/icon/star/yellow.svg" width="24">
    <div class="text-xs overflow-hidden break-all">※このレビューは作品の内容に関する記述が含まれています。</div>
  </div>
</div>
"""

EMPTY_REVIEW_HTML = """
<div id="review">
  <div>総評価数<span>4</span>(0件のコメント)</div>
  <p>この作品に最初のレビューを書いてみませんか？</p>
</div>
"""


class TestReviewCommentCount:
    def test_none_and_empty(self):
        assert scraper.review_comment_count_from_text(None) is None
        assert scraper.review_comment_count_from_text("") is None
        assert scraper.review_comment_count_from_text("ユーザーレビュー") is None

    def test_parses_count_across_newlines(self):
        text = "総評価数\n4\n(0件のコメント)"
        assert scraper.review_comment_count_from_text(text) == 0
        assert scraper.review_comment_count_from_text("総評価数 6 (6件のコメント)") == 6

    def test_empty_list_cta_and_zero_comments(self):
        assert scraper.is_empty_video_review_list("") is False
        assert scraper.is_empty_video_review_list("最初のレビューを書いてみませんか") is True
        assert scraper.is_empty_video_review_list("総評価数 4 (0件のコメント)") is True
        assert scraper.is_empty_video_review_list("総評価数 6 (6件のコメント)") is False


class TestStarHelpers:
    def test_full_star_src_excludes_half(self):
        assert scraper._is_full_star_src(
            "https://x/icon/star/yellow.svg?hash=1"
        )
        assert not scraper._is_full_star_src(
            "https://x/icon/star/half-yellow.svg?hash=1"
        )
        assert not scraper._is_full_star_src("")

    def test_small_star_accepts_16_and_24_not_50(self):
        src = "https://x/icon/star/yellow.svg"

        def img(width, height=""):
            el = MagicMock()
            el.get_attribute.side_effect = lambda k: {
                "src": src,
                "width": width,
                "height": height,
            }.get(k, "")
            return el

        assert scraper._is_small_star_img(img("24", "24"))
        assert scraper._is_small_star_img(img("16"))
        assert not scraper._is_small_star_img(img("50", "50"))


class TestParseE2eVideoReviewsHtml:
    def test_empty_html(self):
        assert scraper.parse_e2e_video_reviews_html("") == []
        assert scraper.parse_e2e_video_reviews_html(EMPTY_REVIEW_HTML) == []

    def test_extracts_comment_and_skips_spoiler_placeholder(self):
        reviews = scraper.parse_e2e_video_reviews_html(AMATEUR_REVIEW_HTML)
        assert len(reviews) == 1
        r = reviews[0]
        assert r["rating"] == 2.0
        assert r["title"] == "良い作品"
        assert "面白かったです。" in r["text"]
        assert r["reviewer"] == "太郎さんのレビュー"
        assert r["date"] == "2026-08-13"

    def test_max_reviews_zero(self):
        assert scraper.parse_e2e_video_reviews_html(AMATEUR_REVIEW_HTML, max_reviews=0) == []


class TestWaitAndHydrate:
    def test_wait_returns_empty_when_zero_comments(self):
        root = MagicMock()
        root.text = "総評価数 4 (0件のコメント)"

        def find_elements(by, sel):
            if sel == "review":
                return [root]
            return []

        driver = MagicMock()
        driver.find_elements.side_effect = find_elements
        assert scraper._wait_video_review_ui(driver, timeout=0.4) == "empty"

    def test_wait_returns_legacy_when_items_present(self):
        driver = MagicMock()

        def find_elements(by, sel):
            if sel == '[data-e2eid="review-item"]':
                return [MagicMock()]
            return []

        driver.find_elements.side_effect = find_elements
        assert scraper._wait_video_review_ui(driver, timeout=0.4) == "legacy"

    def test_wait_times_out_to_digital_if_only_shell(self):
        root = MagicMock()
        root.text = "ユーザーレビュー"

        def find_elements(by, sel):
            if sel == "review":
                return [root]
            return []

        driver = MagicMock()
        driver.find_elements.side_effect = find_elements
        assert scraper._wait_video_review_ui(driver, timeout=0.3) == "digital"

    def test_wait_returns_none_without_review(self):
        driver = MagicMock()
        driver.find_elements.return_value = []
        assert scraper._wait_video_review_ui(driver, timeout=0.3) is None

    def test_hydrate_returns_empty(self):
        root = MagicMock()
        root.text = "この作品に最初のレビューを書いてみませんか？"
        root.find_elements.return_value = []
        driver = MagicMock()
        driver.find_element.return_value = root
        driver.find_elements.return_value = []
        assert scraper._hydrate_fanza_digital_review_list(driver, timeout=0.4) == "empty"

    def test_hydrate_returns_ready_on_e2e_item(self):
        root = MagicMock()
        root.text = "総評価数 1 (1件のコメント)"
        root.find_elements.return_value = []
        driver = MagicMock()
        driver.find_element.return_value = root

        def find_elements(by, sel):
            if sel == '[data-e2eid="review-item"]':
                return [MagicMock()]
            return []

        driver.find_elements.side_effect = find_elements
        assert scraper._hydrate_fanza_digital_review_list(driver, timeout=0.4) == "ready"


class TestGetVideoReviews:
    def test_empty_mode_skips_without_parse(self):
        driver = MagicMock()
        with (
            patch.object(scraper, "_wait_video_review_ui", return_value="empty"),
            patch.object(scraper, "_parse_legacy_e2e_video_reviews") as parse,
        ):
            assert scraper.get_video_reviews(driver, "https://example/x") == []
            parse.assert_not_called()

    def test_missing_region_returns_empty(self):
        driver = MagicMock()
        with patch.object(scraper, "_wait_video_review_ui", return_value=None):
            assert scraper.get_video_reviews(driver, "https://example/x") == []

    def test_legacy_path(self):
        driver = MagicMock()
        expected = [{"rating": 5, "text": "ok", "title": "t"}]
        with (
            patch.object(scraper, "_wait_video_review_ui", return_value="legacy"),
            patch.object(scraper, "expand_hidden_reviews"),
            patch.object(scraper, "time") as t,
            patch.object(
                scraper, "_parse_legacy_e2e_video_reviews", return_value=expected
            ),
        ):
            t.sleep.return_value = None
            assert scraper.get_video_reviews(driver, "https://example/x") == expected

    def test_digital_hydrate_empty_skips(self):
        driver = MagicMock()
        with (
            patch.object(scraper, "_wait_video_review_ui", return_value="digital"),
            patch.object(scraper, "expand_hidden_reviews"),
            patch.object(scraper, "time") as t,
            patch.object(
                scraper, "_hydrate_fanza_digital_review_list", return_value="empty"
            ),
            patch.object(scraper, "_parse_legacy_e2e_video_reviews") as parse,
        ):
            t.sleep.return_value = None
            assert scraper.get_video_reviews(driver, "https://example/x") == []
            parse.assert_not_called()

    def test_digital_hydrate_then_legacy_html(self):
        driver = MagicMock()
        expected = [{"rating": 4.0, "text": "body", "title": "t"}]

        def find_elements(by, sel):
            if sel == '[data-e2eid="review-item"]':
                return [MagicMock()]
            return []

        driver.find_elements.side_effect = find_elements
        with (
            patch.object(scraper, "_wait_video_review_ui", return_value="digital"),
            patch.object(scraper, "expand_hidden_reviews"),
            patch.object(scraper, "time") as t,
            patch.object(
                scraper, "_hydrate_fanza_digital_review_list", return_value="ready"
            ),
            patch.object(
                scraper, "_parse_legacy_e2e_video_reviews", return_value=expected
            ),
        ):
            t.sleep.return_value = None
            assert scraper.get_video_reviews(driver, "https://example/x") == expected

    def test_comic_path(self):
        driver = MagicMock()
        with (
            patch.object(scraper, "_wait_video_review_ui", return_value="comic"),
            patch.object(scraper, "expand_hidden_reviews"),
            patch.object(scraper, "time") as t,
            patch.object(scraper, "_parse_comic_reviews", return_value=[]),
        ):
            t.sleep.return_value = None
            assert scraper.get_video_reviews(driver, "https://example/x") == []

    def test_parse_error_returns_empty(self):
        driver = MagicMock()
        with patch.object(
            scraper, "_wait_video_review_ui", side_effect=RuntimeError("boom")
        ):
            assert scraper.get_video_reviews(driver, "https://example/x") == []


class TestLegacyHtmlFallback:
    def test_uses_html_parser_from_review_root(self):
        root = MagicMock()
        root.get_attribute.return_value = AMATEUR_REVIEW_HTML
        driver = MagicMock()
        driver.find_element.return_value = root
        reviews = scraper._parse_legacy_e2e_video_reviews(driver, max_reviews=10)
        assert len(reviews) == 1
        assert "面白かったです。" in reviews[0]["text"]


NESTED_COMIC_HTML = """
<section data-section-name="review">
  <div class="outer">
    <div class="card">
      <a data-testid="nickname">ｎｏｎｏｎｏ</a>
      <i data-name="yellow"></i><i data-name="yellow"></i><i data-name="yellow"></i>
      <i data-name="yellow"></i><i data-name="yellow"></i>
      <p>井ノ原課長の回がよかった</p>
      <p>このレビューは参考になりましたか？</p>
      <span>2026/08/01</span>
    </div>
    <div class="card">
      <a data-testid="nickname">小林剣士</a>
      <i data-name="yellow"></i><i data-name="yellow"></i><i data-name="yellow"></i>
      <i data-name="yellow"></i>
      <p>絵がリアルでストーリーに没頭できる。</p>
      <span>2026/07/20</span>
    </div>
  </div>
</section>
"""


class TestParseComicReviewsHtml:
    def test_empty(self):
        assert scraper.parse_comic_reviews_html("") == []
        assert scraper.parse_comic_reviews_html("<div></div>") == []

    def test_nested_wrapper_does_not_duplicate(self):
        reviews = scraper.parse_comic_reviews_html(NESTED_COMIC_HTML)
        assert len(reviews) == 2
        assert [r["reviewer"] for r in reviews] == ["ｎｏｎｏｎｏ", "小林剣士"]
        assert reviews[0]["rating"] == 5.0
        assert reviews[1]["rating"] == 4.0
        assert "井ノ原課長" in reviews[0]["text"]
        assert "参考になりましたか" not in reviews[0]["text"]
        assert reviews[0]["date"] == "2026-08-01"
        assert reviews[1]["date"] == "2026-07-20"

    def test_max_reviews(self):
        reviews = scraper.parse_comic_reviews_html(NESTED_COMIC_HTML, max_reviews=1)
        assert len(reviews) == 1
        assert reviews[0]["reviewer"] == "ｎｏｎｏｎｏ"

    def test_driver_uses_html_parser(self):
        root = MagicMock()
        root.get_attribute.return_value = NESTED_COMIC_HTML
        driver = MagicMock()
        driver.find_elements.return_value = [root]
        reviews = scraper._parse_comic_reviews(driver, max_reviews=10)
        assert len(reviews) == 2

    def test_driver_no_section(self):
        driver = MagicMock()
        driver.find_elements.return_value = []
        assert scraper._parse_comic_reviews(driver, max_reviews=10) == []

