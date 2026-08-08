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
