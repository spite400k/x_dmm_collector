import importlib
import json
import sys
from unittest.mock import MagicMock, patch

import pytest


def load_content_generator_review_module():
    module_name = "utils.content_generator_review"
    if "openai" not in sys.modules:
        openai_mock = MagicMock()
        openai_mock.OpenAI = MagicMock()
        sys.modules["openai"] = openai_mock
    if module_name in sys.modules:
        return importlib.reload(sys.modules[module_name])
    return importlib.import_module(module_name)


@pytest.fixture
def review_module():
    return load_content_generator_review_module()


def test_generate_review_insights_uses_structured_prompt(review_module):
    ai_payload = {
        "review_digest": "要約",
        "content_score": 80,
        "emotion_score": 75,
        "attraction_score": 70,
        "genre_axis1_score": 85,
        "genre_axis2_score": 65,
        "reader_types": ["タイA", "タイB"],
        "warning_points": ["注意A"],
    }
    message = MagicMock()
    message.content = json.dumps(ai_payload)
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]

    reviews = [{"rating": 5, "text": "とても良い作品でした"}]

    with patch.object(review_module.client.chat.completions, "create", return_value=response) as create_mock:
        result = review_module.generate_review_insights(
            reviews=reviews,
            html_summary="あらすじテキスト",
            review_avg=4.5,
            review_count=10,
            genre_type="doujin_digital_doujin",
        )

        call_kwargs = create_mock.call_args.kwargs
        assert call_kwargs["response_format"] == {"type": "json_object"}
        messages = call_kwargs["messages"]
        assert messages[0]["content"] == review_module.REVIEW_INSIGHTS_SYSTEM_PROMPT
        user_content = messages[1]["content"]
        assert "あらすじテキスト" in user_content
        assert "とても良い作品でした" in user_content
        assert "刺さり度（フェチ）" in user_content
        assert "タイプ1" not in user_content
        assert "ワーニング1" not in user_content
        assert '"reader_types": ["...", "..."]' in user_content
        assert "review_digest" in result
        assert "total_score" in result


def test_handle_safe_mode_skips_when_not_age_check(review_module):
    driver = MagicMock()
    driver.current_url = "https://video.dmm.co.jp/amateur/content/?id=x"
    driver.title = "作品"
    driver.find_elements.return_value = []
    review_module.handle_safe_mode(driver)
    driver.execute_script.assert_not_called()


def test_handle_safe_mode_clicks_modal_yes(review_module):
    driver = MagicMock()
    driver.current_url = "https://www.dmm.co.jp/age_check/=/?rurl=https://video.dmm.co.jp/"
    driver.title = "年齢認証 - FANZA"
    btn = MagicMock()
    wait = MagicMock()
    wait.until.side_effect = [btn, True]
    with patch.object(review_module, "WebDriverWait", return_value=wait):
        review_module.handle_safe_mode(driver)
    driver.execute_script.assert_called_once()
    driver.add_cookie.assert_called()
    cookie = driver.add_cookie.call_args.args[0]
    assert cookie["name"] == "age_check_done"
    assert cookie["value"] == "1"


def test_apply_age_check_cookie_swallows_error(review_module):
    driver = MagicMock()
    driver.add_cookie.side_effect = Exception("not on domain")
    review_module.apply_age_check_cookie(driver)


def test_handle_safe_mode_ignores_helpful_yes_on_product_page(review_module):
    """同人・comic の「参考になりましたか？ はい」を年齢確認と誤認しない。"""
    driver = MagicMock()
    driver.current_url = "https://www.dmm.co.jp/dc/doujin/-/detail/=/cid=d_798570/"
    driver.title = "同人作品"

    def find_elements(by, sel):
        if sel == "はい" or (isinstance(sel, str) and "はい" in sel):
            return [MagicMock()]
        return []

    driver.find_elements.side_effect = find_elements
    review_module.handle_safe_mode(driver)
    driver.execute_script.assert_not_called()
    driver = MagicMock()
    driver.current_url = "https://www.dmm.co.jp/age_check/=/?rurl=x"
    driver.title = "年齢認証"
    wait = MagicMock()
    wait.until.side_effect = Exception("not clickable")
    with patch.object(review_module, "WebDriverWait", return_value=wait):
        review_module.handle_safe_mode(driver)
    driver.execute_script.assert_not_called()


def test_age_check_url_uses_path_not_rurl_query(review_module):
    age_url = (
        "https://www.dmm.co.jp/age_check/=/"
        "?rurl=https%3A%2F%2Fvideo.dmm.co.jp%2Famateur%2Fcontent%2F%3Fid%3Dpai436"
    )
    product_url = "https://video.dmm.co.jp/amateur/content/?id=pai436"
    assert review_module.is_age_check_url(age_url) is True
    assert review_module.is_age_check_url(product_url) is False
    assert review_module.is_age_check_url(None) is False
    assert review_module.is_age_check_url("") is False
    assert review_module.is_video_dmm_host(age_url) is False
    assert review_module.is_video_dmm_host(product_url) is True
    assert review_module.is_book_dmm_host(
        "https://book.dmm.co.jp/detail/b123/"
    ) is True
    assert review_module.is_book_dmm_host(age_url) is False


def test_is_age_gate_synopsis(review_module):
    gate = "ここから先は、アダルト商品を扱うアダルトサイトとなります。18歳未満の方のアクセスは固くお断りします。"
    assert review_module.is_age_gate_synopsis(gate) is True
    assert review_module.is_age_gate_synopsis("交際2年の素人が初めてカメラの前で") is False
    assert review_module.is_age_gate_synopsis(None) is False
    assert review_module.is_age_gate_synopsis("") is False


def test_try_video_dmm_synopsis_rejects_age_check_rurl(review_module):
    driver = MagicMock()
    driver.current_url = (
        "https://www.dmm.co.jp/age_check/=/"
        "?rurl=https%3A%2F%2Fvideo.dmm.co.jp%2Famateur%2Fcontent%2F%3Fid%3Dpai436"
    )
    meta = MagicMock()
    meta.get_attribute.return_value = (
        "ここから先は、アダルト商品を扱うアダルトサイトとなります。"
        "18歳未満の方のアクセスは固くお断りします。"
    )
    driver.find_element.return_value = meta
    driver.find_elements.return_value = []
    assert review_module._try_video_dmm_synopsis_block(driver) == ""
    driver.find_element.assert_not_called()


def test_try_video_dmm_synopsis_rejects_age_gate_meta(review_module):
    driver = MagicMock()
    driver.current_url = "https://video.dmm.co.jp/amateur/content/?id=pai436"
    driver.find_elements.return_value = []
    meta = MagicMock()
    meta.get_attribute.return_value = (
        "ここから先は、アダルト商品を扱うアダルトサイトとなります。"
        "18歳未満の方のアクセスは固くお断りします。"
    )
    driver.find_element.return_value = meta
    assert review_module._try_video_dmm_synopsis_block(driver) == ""


def test_try_video_dmm_synopsis_uses_xpath_block(review_module):
    driver = MagicMock()
    driver.current_url = "https://video.dmm.co.jp/av/content/?id=x"
    block = MagicMock()
    driver.find_elements.return_value = [block]
    driver.execute_script.return_value = "作品固有のあらすじがここに入っている。撮影と演出の見どころ。" * 2
    result = review_module._try_video_dmm_synopsis_block(driver)
    assert "作品固有のあらすじ" in result
    driver.find_element.assert_not_called()


def test_try_video_dmm_synopsis_skips_age_gate_xpath(review_module):
    driver = MagicMock()
    driver.current_url = "https://video.dmm.co.jp/amateur/content/?id=pai436"
    block = MagicMock()
    driver.find_elements.return_value = [block]
    driver.execute_script.return_value = (
        "ここから先は、アダルト商品を扱うアダルトサイトとなります。"
        "18歳未満の方のアクセスは固くお断りします。"
    )
    meta = MagicMock()
    meta.get_attribute.return_value = (
        "作品の見どころを40文字以上で具体的に書いた紹介文です。"
        "出演者と撮影環境にも触れている。"
    )
    driver.find_element.return_value = meta
    result = review_module._try_video_dmm_synopsis_block(driver)
    assert "見どころ" in result


def test_try_video_dmm_synopsis_accepts_product_meta(review_module):
    driver = MagicMock()
    driver.current_url = "https://video.dmm.co.jp/amateur/content/?id=pai436"
    driver.find_elements.return_value = []
    meta = MagicMock()
    meta.get_attribute.return_value = (
        "交際2年の素人カップルが初めてカメラの前で素顔を見せる。"
        "撮影環境や演出の方向性が具体的に書かれた紹介文。"
    )
    driver.find_element.return_value = meta
    result = review_module._try_video_dmm_synopsis_block(driver)
    assert "素人カップル" in result
    assert len(result) >= 40


def test_scrape_product_summary_aborts_on_age_check(review_module):
    driver = MagicMock()
    driver.current_url = (
        "https://www.dmm.co.jp/age_check/=/"
        "?rurl=https%3A%2F%2Fvideo.dmm.co.jp%2Famateur%2Fcontent%2F%3Fid%3Dpai436"
    )
    with patch.object(review_module, "handle_safe_mode") as handle:
        result = review_module.scrape_product_summary(
            "https://video.dmm.co.jp/amateur/content/?id=pai436",
            driver,
        )
    assert result == ""
    handle.assert_called_once()
    driver.get.assert_called_once()


def test_try_comic_synopsis_rejects_age_check_rurl(review_module):
    driver = MagicMock()
    driver.current_url = (
        "https://www.dmm.co.jp/age_check/=/?rurl=https%3A%2F%2Fbook.dmm.co.jp%2Fdetail%2Fx"
    )
    assert review_module._try_comic_synopsis_block(driver) == ""


def test_scrape_doujin_synopsis_aborts_on_age_check(review_module):
    driver = MagicMock()
    driver.current_url = "https://www.dmm.co.jp/age_check/=/?rurl=https://www.dmm.co.jp/dc/doujin/"
    with patch.object(review_module, "handle_safe_mode"):
        result = review_module.scrape_doujin_synopsis(
            driver,
            "https://www.dmm.co.jp/dc/doujin/-/detail/=/cid=d_1/",
        )
    assert result == ""
