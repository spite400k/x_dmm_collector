# utils/content_generator.py

import os
import random
import re
import time
import logging
from typing import List, Dict
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import InvalidSessionIdException, WebDriverException
from openai import OpenAI

from bs4 import BeautifulSoup

from openai_api.content_generator import extract_synopsis_from_soup
from utils.dmm_review_scraper import get_doujin_reviews, get_video_reviews
from utils.screenshot import save_debug_files

client = OpenAI()

_CHROMEDRIVER_PATH = None
SUMMARY_MAX_CHARS_FOR_AI = 4000


def _chromedriver_path() -> str:
    global _CHROMEDRIVER_PATH
    if _CHROMEDRIVER_PATH is None:
        _CHROMEDRIVER_PATH = ChromeDriverManager().install()
    return _CHROMEDRIVER_PATH


# =========================
# 🚀 Driver生成（バッチ単位で1回だけ使う）
# =========================
def create_driver() -> webdriver.Chrome:
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-images")
    options.page_load_strategy = "eager"

    service = Service(_chromedriver_path())
    driver = webdriver.Chrome(service=service, options=options)
    driver.set_page_load_timeout(20)

    return driver


def is_driver_alive(driver) -> bool:
    try:
        _ = driver.current_url
        return True
    except (InvalidSessionIdException, WebDriverException):
        return False


def quit_driver_safe(driver) -> None:
    if driver is None:
        return
    try:
        driver.quit()
    except (InvalidSessionIdException, WebDriverException, OSError):
        pass


def ensure_driver_alive(driver):
    """セッション切れ時は driver を再作成して返す。"""
    if driver is not None and is_driver_alive(driver):
        return driver
    logging.warning("Chrome セッション切れ → driver を再作成します")
    quit_driver_safe(driver)
    return create_driver()

def handle_safe_mode(driver):
    print("現在URL:", driver.current_url)
    print("title:", driver.title)
    try:
        yes_button = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable(
                (By.XPATH, "//button[.//span[text()='はい']]")
            )
        )

        driver.execute_script("arguments[0].click();", yes_button)
        print("✅ セーフモード突破")

        # モーダルが消えるまで待機
        WebDriverWait(driver, 5).until_not(
            EC.presence_of_element_located(
                (By.XPATH, "//span[text()='表示しますか？']")
            )
        )

    except Exception:
        pass


        
# =========================
# 🔍 レビューURL構築
# =========================
def build_review_url(product_url: str, service: str, floor: str) -> str:
    if service == "doujin" and floor == "digital_doujin":
        # return product_url.rstrip("/") + "/review/"
        return product_url + "#review_anchor"
    else:
        if product_url.endswith("/"):
            return product_url + "#review"
        return product_url + "#review"



# =========================
# 📝 レビュー取得
# =========================
def scrape_review_comments(product_url: str, driver, service: str, floor: str, max_reviews=20):

    review_url = build_review_url(product_url, service, floor )
    logging.info(f"🔍 レビューURL: {review_url}")

    try:
        if service == "doujin" and floor == "digital_doujin":
            driver.get(review_url)
            handle_safe_mode(driver)
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "#review_anchor")
                    )
                )
            except Exception:
                pass
            return get_doujin_reviews(driver, product_url, max_reviews)

        # video / comic: Cookie 用に video.dmm 経由
        driver.get("https://video.dmm.co.jp/")
        try:
            yes_button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.LINK_TEXT, "はい"))
            )
            yes_button.click()
        except Exception:
            pass

        driver.get(review_url)
        handle_safe_mode(driver)

        try:
            rev = WebDriverWait(driver, 12).until(
                EC.presence_of_element_located((By.ID, "review"))
            )
            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center', behavior: 'instant'});",
                rev,
            )
            WebDriverWait(driver, 5).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            driver.execute_script("window.scrollBy(0, 600);")
        except Exception:
            driver.execute_script("window.scrollTo(0, 2000);")

    except InvalidSessionIdException:
        raise
    except Exception as e:
        logging.warning(f"[Review Page Error] {product_url} → {e}")
        return []

    return get_video_reviews(driver, product_url, max_reviews)


# =========================
# 📖 あらすじ取得
# =========================
def scrape_doujin_synopsis(driver, product_url: str) -> str:
    """レビュー取得済みの driver から同人あらすじを取得（別 Chrome 起動不要）。"""
    base_url = product_url.split("#")[0]
    current = (driver.current_url or "").split("#")[0]
    if base_url and base_url not in current:
        driver.get(base_url)
        handle_safe_mode(driver)
        try:
            WebDriverWait(driver, 12).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
        except Exception:
            pass

    soup = BeautifulSoup(driver.page_source, "html.parser")
    synopsis = extract_synopsis_from_soup(soup, base_url or driver.current_url)
    if synopsis:
        return synopsis

    for selector in ("motion.div.productDetail", "div.mg-b20.lh4"):
        el = soup.select_one(selector)
        if el:
            text = el.get_text(separator="\n").strip()
            if len(text) >= 40:
                return text
    return ""


def _summary_text_content(driver, el) -> str:
    try:
        raw = driver.execute_script(
            "return (arguments[0].textContent || '').trim();", el
        )
        return (raw or "").strip()
    except Exception:
        return ""


def _try_video_dmm_synopsis_block(driver) -> str:
    """
    video.dmm（ビデオ videoa 等）: あらすじは <p> ではなく <br> 区切りの div に入っている。
    参考: summary_snos00168_*.html — 「特集」h2 直前の兄弟 div。
    """
    if "video.dmm.co.jp" not in (driver.current_url or ""):
        return ""
    xpaths = (
        "//h2[contains(@class,'font-bold')][normalize-space(.)='特集']/parent::div/preceding-sibling::div[1]",
        "//h2[normalize-space(.)='特集']/parent::div/preceding-sibling::div[1]",
    )
    for xp in xpaths:
        try:
            els = driver.find_elements(By.XPATH, xp)
            if not els:
                continue
            t = _summary_text_content(driver, els[0])
            t = re.sub(r"\s+", " ", t).strip()
            if len(t) >= 40:
                return t
        except Exception:
            continue

    try:
        meta = driver.find_element(By.CSS_SELECTOR, 'meta[name="description"]')
        t = (meta.get_attribute("content") or "").strip()
        if len(t) >= 40:
            return t
    except Exception:
        pass
    return ""


def _try_comic_synopsis_block(driver) -> str:
    """
    book.dmm.co.jp (floor=comic) のあらすじ取得。
    meta description は約200文字で切れるため、折りたたみ本文 / JSON-LD を優先する。
    """
    current_url = driver.current_url or ""
    if "book.dmm.co.jp" not in current_url:
        return ""

    try:
        toggle = driver.find_element(
            By.CSS_SELECTOR, '[data-testid="detail-toggle-button"]'
        )
        container = toggle.find_element(By.XPATH, "./..")
        for paragraph in container.find_elements(By.TAG_NAME, "p"):
            t = re.sub(r"\s+", " ", _summary_text_content(driver, paragraph)).strip()
            if len(t) >= 40:
                return t
    except Exception:
        pass

    soup = BeautifulSoup(driver.page_source, "html.parser")
    synopsis = extract_synopsis_from_soup(soup, current_url)
    if synopsis:
        return synopsis

    return ""


def scrape_product_summary(product_url: str, driver) -> str:
    try:
        driver.get(product_url)
        wait = WebDriverWait(driver, 15)

        # 年齢確認があれば突破
        try:
            yes_button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.LINK_TEXT, "はい"))
            )
            yes_button.click()
        except:
            pass

        wait.until(
            lambda d: d.find_elements(By.CSS_SELECTOR, 'meta[name="description"]')
            or d.find_elements(By.TAG_NAME, "h1")
        )

        synopsis = _try_video_dmm_synopsis_block(driver)
        if synopsis:
            logging.info("あらすじ取得成功（video.dmm: 特集直前 / meta.description）")
            return synopsis

        synopsis = _try_comic_synopsis_block(driver)
        if synopsis:
            logging.info("あらすじ取得成功（book.dmm: 見出し近傍 / meta.description）")
            return synopsis

        # フォールバック: 最長ブロック（.text は clip で欠けるので textContent）
        divs = driver.find_elements(By.XPATH, "//div")
        best_text = ""
        max_len = 0
        min_len = 80
        for div in divs:
            text = _summary_text_content(driver, div)
            text = re.sub(r"\s+", " ", text).strip()
            if (
                len(text) > min_len
                and "※この商品" not in text
                and "特集" not in text
                and "動作環境" not in text
                and "サンプル画像" not in text
            ):
                if len(text) > max_len:
                    max_len = len(text)
                    best_text = text

        if best_text:
            logging.info("あらすじ取得成功（最長 div ヒューリスティック）")
            return best_text

        logging.warning("⚠ あらすじ候補なし")
        return ""

    except Exception as e:
        logging.warning(f"[Summary Error] {product_url} → {e}")
        return ""




# =========================
# 🤖 AIレビュー分析
# =========================
# =========================
# 🎯 ジャンル別軸定義
# =========================
GENRE_AXIS_MAP = {
    "manga": ("作画完成度", "演出・没入感"),
    "lightnovel": ("世界観構築", "読みやすさ・テンポ"),
    "novel": ("深さ・専門性", "実用性・再現性"),
    "photobook": ("ビジュアルインパクト", "コンセプト完成度"),
}
# =========================
# 📊 総合スコア算出
# =========================
def calculate_total_score(scores: Dict) -> float:
    base_total = (
        scores["content_score"] * 0.25 +
        scores["emotion_score"] * 0.20 +
        scores["attraction_score"] * 0.15 +
        scores["genre_axis1_score"] * 0.20 +
        scores["genre_axis2_score"] * 0.20
    )
    return round(base_total, 1)

def adjust_score(ai_score, review_avg, review_count):
    if review_avg is None:
        return ai_score

    # 信頼度（最大1.0）
    confidence = min(review_count / 50, 1.0)

    # レビュー平均を100点換算（例: 5点満点）
    review_score_100 = (review_avg / 5.0) * 100

    # AI 70% + レビュー30%（信頼度で変動）
    final = ai_score * (1 - 0.3 * confidence) + review_score_100 * (0.3 * confidence)

    return round(final, 1)

# =========================
# 🎯 ジャンル別スコア設定
# =========================
def getGenreConfig(genre_type):

    default_config = {
        "axes": [
            {"key": "axis1", "label": "基本評価", "weight": 0.5},
            {"key": "axis2", "label": "満足度", "weight": 0.5},
        ],
        "score_type": "standard",
        "review_bias_factor": 1.0,
    }

    switcher = {

        # =========================
        # 🎬 動画（素人）
        # =========================
        "digital_videoc": {
            "axes": [
                {"key": "realism", "label": "リアル感", "weight": 0.6},
                {"key": "excitement", "label": "興奮度", "weight": 0.4},
            ],
            "score_type": "video_amateur",
            "review_bias_factor": 1.2,  # レビュー影響強め
        },

        # =========================
        # 🎬 動画（女優・企画）
        # =========================
        "digital_videoa": {
            "axes": [
                {"key": "actress", "label": "女優魅力", "weight": 0.5},
                {"key": "production", "label": "作品クオリティ", "weight": 0.5},
            ],
            "score_type": "video_pro",
            "review_bias_factor": 1.1,
        },

        # =========================
        # 🎞️ アニメ
        # =========================
        "digital_anime": {
            "axes": [
                {"key": "visual", "label": "作画・クオリティ", "weight": 0.6},
                {"key": "fetish", "label": "フェチ性", "weight": 0.4},
            ],
            "score_type": "anime",
            "review_bias_factor": 1.0,
        },

        # =========================
        # 📚 同人誌
        # =========================
        "doujin_digital_doujin": {
            "axes": [
                {"key": "fetish", "label": "刺さり度（フェチ）", "weight": 0.7},
                {"key": "uniqueness", "label": "独自性", "weight": 0.3},
            ],
            "score_type": "doujin",
            "review_bias_factor": 0.9,  # レビュー少ないので弱め
        },

        # =========================
        # 📚 コミック
        # =========================
        "ebook_comic": {
            "axes": [
                {"key": "visual", "label": "作画・エロさ", "weight": 0.6},
                {"key": "story", "label": "ストーリー", "weight": 0.4},
            ],
            "score_type": "comic",
            "review_bias_factor": 1.0,
        },

        # =========================
        # 📖 官能小説
        # =========================
        "ebook_novel": {
            "axes": [
                {"key": "immersion", "label": "没入感", "weight": 0.7},
                {"key": "readability", "label": "読みやすさ", "weight": 0.3},
            ],
            "score_type": "novel",
            "review_bias_factor": 1.0,
        },

        # =========================
        # 📸 写真集（将来用）
        # =========================
        "ebook_photo": {
            "axes": [
                {"key": "visual", "label": "ビジュアル完成度", "weight": 0.7},
                {"key": "erotic", "label": "色気", "weight": 0.3},
            ],
            "score_type": "photo",
            "review_bias_factor": 1.1,
        },

        # =========================
        # 🎮 PCゲーム（将来用）
        # =========================
        "pcgame_digital_pcgame": {
            "axes": [
                {"key": "story", "label": "シナリオ", "weight": 0.5},
                {"key": "gameplay", "label": "ゲーム性", "weight": 0.5},
            ],
            "score_type": "game",
            "review_bias_factor": 1.0,
        },
    }

    return switcher.get(genre_type, default_config)


REVIEW_INSIGHTS_SYSTEM_PROMPT = """
あなたはエンタメ作品のレビュー編集者兼スコアアナリストです。

【採点フィールド】content_score, emotion_score, attraction_score, genre_axis1_score, genre_axis2_score
・各項目100点満点の整数（0〜100）のみ出力
・あらすじとレビューの内容のみを根拠に、客観的かつ厳しめに採点
・市場平均は75点前後を基準とする
・レビュー件数が少ない場合は過信しない
・文体ルールは採点フィールドには適用しない

【テキストフィールド】review_digest, reader_types, warning_points
review_digest: 350〜450文字。作品の魅力を感情豊かに要約する。
  体言止め・評論調・論文調は禁止。「あなた」と語りかけてよい（「読者」は使わない）。
reader_types: この作品に合う読者像を2〜3件、具体的な短文で列挙する。
warning_points: 購入前に知っておくべき注意点を1〜3件、具体的な短文で列挙する。

【共通禁止】
・レビュー原文の出力・引用
・JSONオブジェクト以外の出力
・登場人物はすべて18歳以上の成人として扱う
"""


def generate_review_insights(
    reviews: List[Dict],
    html_summary: str,
    review_avg: float,
    review_count: int,
    genre_type: str
) -> Dict:

    config = getGenreConfig(genre_type)

    axes = config["axes"]
    score_type = config["score_type"]

    axis1 = axes[0]["label"]
    axis2 = axes[1]["label"]

    review_text_block = "レビューなし"
    if reviews:
        review_text_block = "\n".join(
            f"- ({r.get('rating', '-')}) {r.get('text', '')[:500]}"
            for r in reviews[:15]
        )

    summary_for_ai = (html_summary or "")[:SUMMARY_MAX_CHARS_FOR_AI]

    prompt = f"""
以下の作品情報を分析し、JSON を出力してください。

【各フィールドの内容】
- review_digest: 作品の魅力を要約（テキストフィールドのルールを適用）
- content_score: 内容力（採点ルールを適用）
- emotion_score: 感情インパクト（採点ルールを適用）
- attraction_score: 魅力（採点ルールを適用）
- genre_axis1_score: {axis1}（{score_type}型のジャンル特性を反映して採点）
- genre_axis2_score: {axis2}（{score_type}型のジャンル特性を反映して採点）
- reader_types: この作品に合う読者像を2〜3件（テキストフィールドのルールを適用）
- warning_points: 購入前の注意点を1〜3件（テキストフィールドのルールを適用）

【作品情報】
ジャンル: {genre_type}（評価タイプ: {score_type}）
レビュー平均: {review_avg} / 件数: {review_count}

【あらすじ】
{summary_for_ai}

【レビュー】
{review_text_block}

【出力スキーマ】
{{
  "review_digest": "...",
  "content_score": 0,
  "emotion_score": 0,
  "attraction_score": 0,
  "genre_axis1_score": 0,
  "genre_axis2_score": 0,
  "reader_types": ["...", "..."],
  "warning_points": ["..."]
}}
"""
    try:
        response = client.chat.completions.create(
            model="gpt-5.4-nano",
            messages=[
                {"role": "system", "content": REVIEW_INSIGHTS_SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            max_completion_tokens=1200,
        )

        import json
        result = json.loads(response.choices[0].message.content)

        # =========================
        # 🔥 レビュー補正適用
        # =========================
        for key in [
            "content_score",
            "emotion_score",
            "attraction_score",
            "genre_axis1_score",
            "genre_axis2_score"
        ]:
            result[key] = adjust_score(
                result.get(key, 70),
                review_avg,
                review_count
            )

        # =========================
        # 📊 総合スコア算出
        # =========================
        result["total_score"] = calculate_total_score(result)

        # =========================
        # 📈 レーダーチャート用データ
        # =========================
        result["radar_chart"] = {
            "labels": [
                "内容力",
                "感情インパクト",
                "魅力",
                axis1,
                axis2
            ],
            "values": [
                result["content_score"],
                result["emotion_score"],
                result["attraction_score"],
                result["genre_axis1_score"],
                result["genre_axis2_score"]
            ]
        }

        return result

    except Exception as e:
        logging.warning(f"[AI Error] {e}")
        return {}