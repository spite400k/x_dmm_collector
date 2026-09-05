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

    def test_positive_count_without_score_history_does_not_skip(self, create_ai_review):
        assert (
            create_ai_review.should_skip_selenium_precheck(
                3, has_saved_summary=True, has_score_history=False
            )
            is False
        )
        assert (
            create_ai_review.should_skip_selenium_precheck(
                3, has_saved_summary=True, has_score_history=True
            )
            is False
        )


class TestProcessContentPrecheck:
    def test_skips_chrome_when_db_zero_and_summary_exists(self, create_ai_review):
        create_ai_review.get_saved_summary = MagicMock(return_value="あらすじ本文")
        create_ai_review.has_score_history = MagicMock(return_value=False)
        scrape = MagicMock()
        create_ai_review.scrape_review_comments = scrape
        driver = MagicMock()

        create_ai_review.process_content(
            "cid1",
            "https://example.com/item",
            "digital",
            "videoa",
            driver,
            db_review_count=0,
        )

        scrape.assert_not_called()
        driver.get.assert_not_called()

    def test_opens_chrome_when_review_count_positive(self, create_ai_review):
        create_ai_review.get_saved_summary = MagicMock(return_value="あらすじ本文")
        create_ai_review.has_score_history = MagicMock(return_value=True)
        driver = MagicMock()
        create_ai_review.scrape_review_comments = MagicMock(return_value=[])
        create_ai_review.save_raw_reviews = MagicMock()
        create_ai_review.generate_review_insights = MagicMock(return_value=None)
        create_ai_review.scrape_product_summary = MagicMock(return_value="x")

        create_ai_review.process_content(
            "cid2",
            "https://example.com/item",
            "digital",
            "videoa",
            driver,
            db_review_count=2,
        )

        create_ai_review.scrape_review_comments.assert_called_once()
        driver.quit.assert_not_called()

    def test_opens_chrome_when_zero_but_no_summary(self, create_ai_review):
        create_ai_review.get_saved_summary = MagicMock(return_value=None)
        driver = MagicMock()
        create_ai_review.scrape_review_comments = MagicMock(return_value=[])
        create_ai_review.save_raw_reviews = MagicMock()
        create_ai_review.scrape_product_summary = MagicMock(return_value="初回あらすじ")
        create_ai_review.generate_review_insights = MagicMock(return_value=None)

        create_ai_review.process_content(
            "cid3",
            "https://example.com/item",
            "digital",
            "videoa",
            driver,
            db_review_count=0,
        )

        create_ai_review.scrape_review_comments.assert_called_once()
        driver.quit.assert_not_called()


AGE_GATE_SUMMARY = (
    "ここから先は、アダルト商品を扱うアダルトサイトとなります。"
    "18歳未満の方のアクセスは固くお断りします。"
)


class TestProcessContentAgeGate:
    def test_opens_chrome_when_age_gate_summary_and_review_zero(self, create_ai_review):
        create_ai_review.get_saved_summary = MagicMock(return_value=AGE_GATE_SUMMARY)
        driver = MagicMock()
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
            driver,
            db_review_count=0,
        )

        create_ai_review.scrape_product_summary.assert_called_once()
        driver.quit.assert_not_called()

    def test_uses_auto_summary_when_scrape_empty(self, create_ai_review):
        create_ai_review.get_saved_summary = MagicMock(return_value=AGE_GATE_SUMMARY)
        driver = MagicMock()
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
            driver,
            db_review_count=1,
            fallback_summary=fallback,
        )

        kwargs = create_ai_review.generate_review_insights.call_args.kwargs
        assert kwargs["html_summary"] == fallback

    def test_uses_title_and_genres_when_auto_summary_empty(self, create_ai_review):
        create_ai_review.get_saved_summary = MagicMock(return_value=None)
        driver = MagicMock()
        create_ai_review.scrape_review_comments = MagicMock(return_value=[])
        create_ai_review.save_raw_reviews = MagicMock()
        create_ai_review.scrape_product_summary = MagicMock(return_value="")
        create_ai_review.generate_review_insights = MagicMock(return_value=None)

        create_ai_review.process_content(
            "pai436",
            "https://example.com",
            "digital",
            "videoc",
            driver,
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
        create_ai_review.scrape_review_comments = MagicMock(return_value=[])
        create_ai_review.save_raw_reviews = MagicMock()
        create_ai_review.scrape_product_summary = MagicMock(return_value="")
        create_ai_review.generate_review_insights = MagicMock()

        create_ai_review.process_content(
            "cid4",
            "https://example.com",
            "digital",
            "videoc",
            driver,
            db_review_count=1,
        )

        create_ai_review.generate_review_insights.assert_not_called()

    def test_regenerates_when_reviews_unchanged_but_summary_is_age_gate(
        self, create_ai_review
    ):
        create_ai_review.get_saved_summary = MagicMock(return_value=AGE_GATE_SUMMARY)
        driver = MagicMock()
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
            driver,
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

    def test_main_dry_run_empty_summary(self, create_ai_review, capsys):
        create_ai_review.fetch_empty_summary_items = MagicMock(
            return_value=[{"content_id": "d_808452"}]
        )
        create_ai_review.main(["--regenerate-empty-summary", "--dry-run"])
        assert "d_808452" in capsys.readouterr().out

    def test_fetch_empty_summary_items(self, create_ai_review):
        table = MagicMock()
        table.select.return_value = table
        table.or_.return_value = table
        table.range.return_value = table
        table.in_.return_value = table
        table.execute.side_effect = [
            MagicMock(data=[{"content_id": "d_808452"}]),
            MagicMock(
                data=[
                    {
                        "content_id": "d_808452",
                        "item_url": "https://x",
                        "service": "doujin",
                        "floor": "digital_doujin",
                    }
                ]
            ),
        ]
        with patch.object(create_ai_review.supabase, "table", return_value=table):
            rows = create_ai_review.fetch_empty_summary_items()
        assert rows[0]["content_id"] == "d_808452"

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

    def test_fetch_recent_items_filters_future_and_prioritizes_reviews(self, create_ai_review):
        from datetime import date

        table = MagicMock()
        table.select.return_value = table
        table.eq.return_value = table
        table.gte.return_value = table
        table.order.return_value = table
        table.range.return_value = table
        table.in_.return_value = table
        table.execute.side_effect = [
            MagicMock(
                data=[
                    {
                        "content_id": "future",
                        "release_date": "2099-01-01",
                        "review_count": 99,
                    },
                    {
                        "content_id": "old-reviewed",
                        "release_date": "2026-08-01",
                        "review_count": 5,
                    },
                    {
                        "content_id": "old-no-review",
                        "release_date": "2026-08-02",
                        "review_count": 0,
                    },
                ]
            ),
            MagicMock(data=[]),
            MagicMock(data=[]),
            MagicMock(data=[]),
            MagicMock(data=[]),
            # filter: summaries / score_history（未生成扱い）
            MagicMock(data=[]),
            MagicMock(data=[]),
        ]
        with patch("scripts.process.create_ai_review.date") as mock_date:
            mock_date.today.return_value = date(2026, 8, 19)
            with patch.object(create_ai_review.supabase, "table", return_value=table):
                rows = create_ai_review.fetch_recent_items()
        assert [row["content_id"] for row in rows] == ["old-reviewed", "old-no-review"]

    def test_fetch_recent_items_drops_unchanged_zero_review(self, create_ai_review):
        from datetime import date

        table = MagicMock()
        table.select.return_value = table
        table.eq.return_value = table
        table.gte.return_value = table
        table.order.return_value = table
        table.range.return_value = table
        table.in_.return_value = table
        table.execute.side_effect = [
            MagicMock(
                data=[
                    {
                        "content_id": "done-zero",
                        "release_date": "2026-08-01",
                        "review_count": 0,
                    },
                    {
                        "content_id": "new-reviews",
                        "release_date": "2026-08-02",
                        "review_count": 3,
                    },
                ]
            ),
            MagicMock(data=[]),
            MagicMock(data=[]),
            MagicMock(data=[]),
            MagicMock(data=[]),
            MagicMock(
                data=[
                    {
                        "content_id": "done-zero",
                        "summary_text": "既存あらすじ",
                        "review_count": 0,
                    },
                    {
                        "content_id": "new-reviews",
                        "summary_text": "既存あらすじ",
                        "review_count": 1,
                    },
                ]
            ),
            MagicMock(data=[{"content_id": "done-zero"}, {"content_id": "new-reviews"}]),
        ]
        with patch("scripts.process.create_ai_review.date") as mock_date:
            mock_date.today.return_value = date(2026, 8, 19)
            with patch.object(create_ai_review.supabase, "table", return_value=table):
                rows = create_ai_review.fetch_recent_items()
        assert [row["content_id"] for row in rows] == ["new-reviews"]

    def test_prioritize_reviewed_items(self, create_ai_review):
        rows = create_ai_review.prioritize_reviewed_items(
            [
                {"content_id": "a", "review_count": 0},
                {"content_id": "b", "review_count": 10},
                {"content_id": "c", "review_count": 2},
            ]
        )
        assert [row["content_id"] for row in rows] == ["b", "c", "a"]

    def test_process_batch_reuses_single_driver(self, create_ai_review):
        driver = MagicMock()
        create_ai_review.create_driver = MagicMock(return_value=driver)
        create_ai_review.quit_driver_safe = MagicMock()
        create_ai_review._process_item_with_retry = MagicMock(side_effect=[driver, driver])
        rows = [
            {
                "content_id": "a",
                "service": "digital",
                "floor": "videoa",
                "item_url": "https://a",
                "review_count": 1,
            },
            {
                "content_id": "b",
                "service": "digital",
                "floor": "videoa",
                "item_url": "https://b",
                "review_count": 1,
            },
        ]
        with patch.object(create_ai_review.time, "sleep"):
            create_ai_review.process_batch(rows, batch_index=1, total=2)
        create_ai_review.create_driver.assert_called_once()
        assert create_ai_review._process_item_with_retry.call_count == 2
        create_ai_review.quit_driver_safe.assert_called_once_with(driver)

    def test_process_item_with_retry_recreates_on_webdriver_error(self, create_ai_review):
        from selenium.common.exceptions import WebDriverException

        first = MagicMock()
        second = MagicMock()
        create_ai_review.ensure_driver_alive = MagicMock(side_effect=[first, second])
        create_ai_review.create_driver = MagicMock(return_value=second)
        create_ai_review.quit_driver_safe = MagicMock()
        create_ai_review.get_saved_summary = MagicMock(return_value=None)
        create_ai_review.process_content = MagicMock(
            side_effect=[WebDriverException("timeout"), None]
        )
        out = create_ai_review._process_item_with_retry(
            first,
            "cid",
            "https://x",
            "digital",
            "videoa",
            db_review_count=1,
        )
        assert out is second
        assert create_ai_review.process_content.call_count == 2
        create_ai_review.quit_driver_safe.assert_called()

    def test_needs_ai_review_refresh_matrix(self, create_ai_review):
        row0 = {"content_id": "a", "review_count": 0}
        row3 = {"content_id": "b", "review_count": 3}
        assert create_ai_review.needs_ai_review_refresh(
            row0, saved_summary_text=None, saved_review_count=0, has_score=False
        )
        assert not create_ai_review.needs_ai_review_refresh(
            row0,
            saved_summary_text="あらすじ",
            saved_review_count=0,
            has_score=True,
        )
        assert create_ai_review.needs_ai_review_refresh(
            row3,
            saved_summary_text="あらすじ",
            saved_review_count=3,
            has_score=False,
        )
        assert create_ai_review.needs_ai_review_refresh(
            row3,
            saved_summary_text="あらすじ",
            saved_review_count=1,
            has_score=True,
        )
        assert not create_ai_review.needs_ai_review_refresh(
            row3,
            saved_summary_text="あらすじ",
            saved_review_count=3,
            has_score=True,
        )

    def test_filter_ai_review_candidates_empty(self, create_ai_review):
        assert create_ai_review.filter_ai_review_candidates([]) == []

    def test_main_content_id_missing_exits(self, create_ai_review):
        create_ai_review.fetch_item_by_content_id = MagicMock(return_value=[])
        with pytest.raises(SystemExit) as exc:
            create_ai_review.main(["--content-id", "missing"])
        assert exc.value.code == 0
