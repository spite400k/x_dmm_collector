"""create_ai_review の DB 事前スキップ（Selenium 省略）判定。"""

from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock, patch

import pytest


def load_create_ai_review_module():
    module_name = "scripts.process.create_ai_review"
    if "openai" not in sys.modules:
        openai_mock = MagicMock()
        openai_mock.OpenAI = MagicMock()
        sys.modules["openai"] = openai_mock
    with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}, clear=False):
        if module_name in sys.modules:
            return importlib.reload(sys.modules[module_name])
        return importlib.import_module(module_name)


@pytest.fixture
def create_ai_review():
    return load_create_ai_review_module()


class TestNormalizeReviewCount:
    def test_none_and_empty(self, create_ai_review):
        assert create_ai_review.normalize_review_count(None) == 0
        assert create_ai_review.normalize_review_count("") == 0

    def test_int_and_string(self, create_ai_review):
        assert create_ai_review.normalize_review_count(0) == 0
        assert create_ai_review.normalize_review_count(3) == 3
        assert create_ai_review.normalize_review_count("12") == 12

    def test_negative_and_invalid(self, create_ai_review):
        assert create_ai_review.normalize_review_count(-1) == 0
        assert create_ai_review.normalize_review_count("x") == 0


class TestShouldSkipSeleniumPrecheck:
    def test_zero_with_summary_skips(self, create_ai_review):
        assert (
            create_ai_review.should_skip_selenium_precheck(
                0, has_saved_summary=True
            )
            is True
        )
        assert (
            create_ai_review.should_skip_selenium_precheck(
                None, has_saved_summary=True
            )
            is True
        )

    def test_zero_without_summary_does_not_skip(self, create_ai_review):
        assert (
            create_ai_review.should_skip_selenium_precheck(
                0, has_saved_summary=False
            )
            is False
        )
        assert (
            create_ai_review.should_skip_selenium_precheck(
                0, has_saved_summary=""
            )
            is False
        )

    def test_positive_count_does_not_skip(self, create_ai_review):
        assert (
            create_ai_review.should_skip_selenium_precheck(
                1, has_saved_summary=True
            )
            is False
        )
        assert (
            create_ai_review.should_skip_selenium_precheck(
                5, has_saved_summary=False
            )
            is False
        )


class TestProcessContentPrecheck:
    def test_skips_chrome_when_db_zero_and_summary_exists(self, create_ai_review):
        create_ai_review.get_saved_summary = MagicMock(return_value="あらすじ本文")
        create_driver = MagicMock()
        create_ai_review.create_driver = create_driver
        scrape = MagicMock()
        create_ai_review.scrape_review_comments = scrape

        create_ai_review.process_content(
            "cid1",
            "https://example.com/item",
            "digital",
            "videoa",
            db_review_count=0,
        )

        create_driver.assert_not_called()
        scrape.assert_not_called()

    def test_opens_chrome_when_review_count_positive(self, create_ai_review):
        create_ai_review.get_saved_summary = MagicMock(return_value="あらすじ本文")
        driver = MagicMock()
        create_ai_review.create_driver = MagicMock(return_value=driver)
        create_ai_review.scrape_review_comments = MagicMock(return_value=[])
        create_ai_review.save_raw_reviews = MagicMock()
        create_ai_review.generate_review_insights = MagicMock(return_value=None)
        create_ai_review.scrape_product_summary = MagicMock(return_value="x")

        create_ai_review.process_content(
            "cid2",
            "https://example.com/item",
            "digital",
            "videoa",
            db_review_count=2,
        )

        create_ai_review.create_driver.assert_called_once()
        create_ai_review.scrape_review_comments.assert_called_once()
        driver.quit.assert_called_once()

    def test_opens_chrome_when_zero_but_no_summary(self, create_ai_review):
        create_ai_review.get_saved_summary = MagicMock(return_value=None)
        driver = MagicMock()
        create_ai_review.create_driver = MagicMock(return_value=driver)
        create_ai_review.scrape_review_comments = MagicMock(return_value=[])
        create_ai_review.save_raw_reviews = MagicMock()
        create_ai_review.scrape_product_summary = MagicMock(return_value="初回あらすじ")
        create_ai_review.generate_review_insights = MagicMock(return_value=None)

        create_ai_review.process_content(
            "cid3",
            "https://example.com/item",
            "digital",
            "videoa",
            db_review_count=0,
        )

        create_ai_review.create_driver.assert_called_once()
        driver.quit.assert_called_once()


AGE_GATE_SUMMARY = (
    "ここから先は、アダルト商品を扱うアダルトサイトとなります。"
    "18歳未満の方のアクセスは固くお断りします。"
)


class TestProcessContentAgeGate:
    def test_opens_chrome_when_age_gate_summary_and_review_zero(self, create_ai_review):
        create_ai_review.get_saved_summary = MagicMock(return_value=AGE_GATE_SUMMARY)
        driver = MagicMock()
        create_ai_review.create_driver = MagicMock(return_value=driver)
        create_ai_review.scrape_review_comments = MagicMock(return_value=[])
        create_ai_review.save_raw_reviews = MagicMock()
        create_ai_review.scrape_product_summary = MagicMock(
            return_value="作品固有のあらすじを40文字以上で書いた本文です。"
        )
        create_ai_review.generate_review_insights = MagicMock(return_value=None)

        create_ai_review.process_content(
            "pai436",
            "https://video.dmm.co.jp/amateur/content/?id=pai436",
            "digital",
            "videoc",
            db_review_count=0,
        )

        create_ai_review.create_driver.assert_called_once()
        create_ai_review.scrape_product_summary.assert_called_once()
        driver.quit.assert_called_once()

    def test_uses_auto_summary_when_scrape_empty(self, create_ai_review):
        create_ai_review.get_saved_summary = MagicMock(return_value=AGE_GATE_SUMMARY)
        driver = MagicMock()
        create_ai_review.create_driver = MagicMock(return_value=driver)
        create_ai_review.scrape_review_comments = MagicMock(return_value=[])
        create_ai_review.save_raw_reviews = MagicMock()
        create_ai_review.scrape_product_summary = MagicMock(return_value="")
        create_ai_review.generate_review_insights = MagicMock(return_value=None)
        fallback = "交際2年の素人が初めてカメラの前で素顔を見せる紹介文です。"

        create_ai_review.process_content(
            "pai436",
            "https://example.com",
            "digital",
            "videoc",
            db_review_count=1,
            fallback_summary=fallback,
        )

        kwargs = create_ai_review.generate_review_insights.call_args.kwargs
        assert kwargs["html_summary"] == fallback

    def test_uses_title_and_genres_when_auto_summary_empty(self, create_ai_review):
        create_ai_review.get_saved_summary = MagicMock(return_value=None)
        driver = MagicMock()
        create_ai_review.create_driver = MagicMock(return_value=driver)
        create_ai_review.scrape_review_comments = MagicMock(return_value=[])
        create_ai_review.save_raw_reviews = MagicMock()
        create_ai_review.scrape_product_summary = MagicMock(return_value="")
        create_ai_review.generate_review_insights = MagicMock(return_value=None)

        create_ai_review.process_content(
            "pai436",
            "https://example.com",
            "digital",
            "videoc",
            db_review_count=1,
            title="みな",
            genres=["素人配信", "ハメ撮り"],
        )

        kwargs = create_ai_review.generate_review_insights.call_args.kwargs
        assert "タイトル: みな" in kwargs["html_summary"]
        assert "ジャンル: 素人配信 / ハメ撮り" in kwargs["html_summary"]

    def test_skips_ai_when_no_synopsis(self, create_ai_review):
        create_ai_review.get_saved_summary = MagicMock(return_value=None)
        driver = MagicMock()
        create_ai_review.create_driver = MagicMock(return_value=driver)
        create_ai_review.scrape_review_comments = MagicMock(return_value=[])
        create_ai_review.save_raw_reviews = MagicMock()
        create_ai_review.scrape_product_summary = MagicMock(return_value="")
        create_ai_review.generate_review_insights = MagicMock()

        create_ai_review.process_content(
            "cid4",
            "https://example.com",
            "digital",
            "videoc",
            db_review_count=1,
        )

        create_ai_review.generate_review_insights.assert_not_called()

    def test_regenerates_when_reviews_unchanged_but_summary_is_age_gate(
        self, create_ai_review
    ):
        create_ai_review.get_saved_summary = MagicMock(return_value=AGE_GATE_SUMMARY)
        driver = MagicMock()
        create_ai_review.create_driver = MagicMock(return_value=driver)
        create_ai_review.scrape_review_comments = MagicMock(
            return_value=[{"rating": 5, "text": "良い"}]
        )
        create_ai_review.has_no_review_changed = MagicMock(return_value=True)
        create_ai_review.save_raw_reviews = MagicMock()
        create_ai_review.scrape_product_summary = MagicMock(
            return_value="作品固有のあらすじを40文字以上で書いた本文です。"
        )
        create_ai_review.generate_review_insights = MagicMock(return_value=None)

        create_ai_review.process_content(
            "pai436",
            "https://example.com",
            "digital",
            "videoc",
            db_review_count=1,
        )

        create_ai_review.scrape_product_summary.assert_called_once()
        create_ai_review.has_no_review_changed.assert_not_called()


class TestCreateAiReviewCli:
    def test_parse_args(self, create_ai_review):
        args = create_ai_review.parse_args(
            ["--regenerate-age-gate", "--dry-run", "--limit", "3", "--content-id", "pai436"]
        )
        assert args.regenerate_age_gate is True
        assert args.dry_run is True
        assert args.limit == 3
        assert args.content_id == "pai436"

    def test_main_dry_run_age_gate(self, create_ai_review, capsys):
        create_ai_review.fetch_age_gate_items = MagicMock(
            return_value=[{"content_id": "pai436"}]
        )
        create_ai_review.main(["--regenerate-age-gate", "--dry-run"])
        assert "pai436" in capsys.readouterr().out

    def test_fetch_item_by_content_id(self, create_ai_review):
        table = MagicMock()
        table.select.return_value = table
        table.eq.return_value = table
        table.limit.return_value = table
        table.execute.return_value = MagicMock(
            data=[{"content_id": "pai436", "item_url": "https://x"}]
        )
        with patch.object(create_ai_review.supabase, "table", return_value=table):
            rows = create_ai_review.fetch_item_by_content_id("pai436")
        assert rows[0]["content_id"] == "pai436"

    def test_fetch_age_gate_items(self, create_ai_review):
        table = MagicMock()
        table.select.return_value = table
        table.or_.return_value = table
        table.range.return_value = table
        table.in_.return_value = table
        table.execute.side_effect = [
            MagicMock(data=[{"content_id": "pai436"}]),
            MagicMock(
                data=[
                    {
                        "content_id": "pai436",
                        "item_url": "https://x",
                        "service": "digital",
                        "floor": "videoc",
                    }
                ]
            ),
        ]
        with patch.object(create_ai_review.supabase, "table", return_value=table):
            rows = create_ai_review.fetch_age_gate_items()
        assert rows[0]["content_id"] == "pai436"

    def test_fetch_age_gate_items_limit_and_missing(self, create_ai_review):
        table = MagicMock()
        table.select.return_value = table
        table.or_.return_value = table
        table.range.return_value = table
        table.in_.return_value = table
        table.execute.side_effect = [
            MagicMock(data=[{"content_id": "a"}, {"content_id": "b"}]),
            MagicMock(data=[{"content_id": "a", "item_url": "https://a"}]),
        ]
        with patch.object(create_ai_review.supabase, "table", return_value=table):
            rows = create_ai_review.fetch_age_gate_items(limit=1)
        assert [r["content_id"] for r in rows] == ["a"]

    def test_fetch_recent_items_empty_page(self, create_ai_review):
        table = MagicMock()
        table.select.return_value = table
        table.eq.return_value = table
        table.gte.return_value = table
        table.order.return_value = table
        table.range.return_value = table
        table.execute.return_value = MagicMock(data=[])
        with patch.object(create_ai_review.supabase, "table", return_value=table):
            assert create_ai_review.fetch_recent_items() == []

    def test_main_content_id_missing_exits(self, create_ai_review):
        create_ai_review.fetch_item_by_content_id = MagicMock(return_value=[])
        with pytest.raises(SystemExit) as exc:
            create_ai_review.main(["--content-id", "missing"])
        assert exc.value.code == 0
