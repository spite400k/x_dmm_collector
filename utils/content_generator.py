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
from openai import OpenAI

from utils.screenshot import save_debug_files

client = OpenAI()


# =========================
# 🚀 Driver生成（1回だけ使う）
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

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.set_page_load_timeout(20)

    return driver

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

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

        time.sleep(1)

    except:
        print("セーフモードなし")
        pass


def expand_hidden_reviews(driver):
    try:
        buttons = driver.find_elements(
            By.XPATH,
            "//p[text()='レビューを表示する']"
        )

        for btn in buttons:
            try:
                driver.execute_script("arguments[0].click();", btn)
            except:
                continue

    except Exception as e:
        logging.warning(f"ネタバレ展開失敗: {e}")
        
# =========================
# 🔍 レビューURL構築
# =========================
def build_review_url(product_url: str) -> str:
    if product_url.endswith("/"):
        return product_url + "#review"
    return product_url + "#review"


# =========================
# 📝 レビュー取得
# =========================
def scrape_review_comments(product_url: str, driver, max_reviews=20):

    review_url = build_review_url(product_url)
    logging.info(f"🔍 レビューURL: {review_url}")

    try:
        # ① まずトップページに行く（Cookie発行）
        driver.get("https://video.dmm.co.jp/")
        time.sleep(2)

        # ③ 年齢確認ボタンがあればクリック
        try:
            yes_button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.LINK_TEXT, "はい"))
            )
            yes_button.click()

        except:
            pass  # 既に通過済み

        driver.get(review_url)
        time.sleep(3)
        # save_debug_files(driver, product_url, prefix="review")

        handle_safe_mode(driver)

        # ④ スクロール（レビュー描画トリガー）
        driver.execute_script("window.scrollTo(0, 2000);")
        # # URLをファイル名用に変換
        # safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', product_url)
        # filepath = os.path.join("debug", f"{safe_name}.png")
        # driver.save_screenshot(filepath)
        # driver.page_source  # ページソースを取得してみる（デバッグ用）
        # save_debug_files(driver, product_url, prefix="review")

    except Exception as e:
        logging.warning(f"[Review Page Error] {product_url} → {e}")
        return []

    try:
        # ① review-bodyが1件以上出るまで待つ
        WebDriverWait(driver, 15).until(
            lambda d: len(
                d.find_elements(By.CSS_SELECTOR, '[data-testid="review-body"]')
            ) > 0
        )
        
        # ② ネタバレ展開（描画後に実行）
        expand_hidden_reviews(driver)
        time.sleep(1)

        review_blocks = driver.find_elements(
            By.CSS_SELECTOR,
            'div[data-e2eid="review-item"]'
        )

        reviews = []

        for block in review_blocks[:max_reviews]:

            # ⭐ 星取得
            stars = block.find_elements(
                By.CSS_SELECTOR,
                '[data-testid="star-icon"][data-name="yellow"]'
            )
            rating = len(stars)

            # 📝 本文取得（全pから本文っぽいものを探す）
            paragraphs = block.find_elements(By.TAG_NAME, "p")

            text = ""
            for p in paragraphs:
                t = p.text.strip()
                if (
                    t and
                    "レビューを表示する" not in t and
                    "このレビューは参考になりましたか" not in t and
                    "※このレビューは作品の内容に関する記述" not in t
                ):
                    text = t
                    break

            if text:
                reviews.append({
                    "rating": rating,
                    "text": text
                })

        logging.info(f"取得レビュー件数: {len(reviews)}")

        return reviews

    except Exception as e:
        logging.warning(f"[Review Parse Error] {product_url} → {e}")
        return []




# =========================
# 📖 あらすじ取得
# =========================
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

        # 説明文ブロックが描画されるまで待つ
        wait.until(
            EC.presence_of_element_located(
                (By.XPATH, "//div[p and not(.//h2)]")
            )
        )

        # 長文候補をすべて取得
        divs = driver.find_elements(By.XPATH, "//div")

        best_text = ""
        max_len = 0

        for div in divs:
            text = div.text.strip()

            # 条件
            if (
                len(text) > 200 and
                "※この商品" not in text and
                "特集" not in text and
                "動作環境" not in text
            ):
                if len(text) > max_len:
                    max_len = len(text)
                    best_text = text

        if best_text:
            logging.info("🔍 video.dmm あらすじ取得成功")
            return best_text

        logging.warning("⚠ あらすじ候補なし")
        return ""

    except Exception as e:
        logging.warning(f"[Summary Error] {product_url} → {e}")
        return ""




# =========================
# 🤖 AIレビュー分析
# =========================
def generate_review_insights(
    reviews: List[Dict],
    html_summary: str
) -> Dict:

    review_text_block = "レビューなし"
    if reviews:
        review_text_block = "\n".join(
            f"- ({r.get('rating', '-')}) {r.get('text', '')}"
            for r in reviews
        )

    prompt = f"""
あなたはエンタメ作品のレビュー編集者です。

以下のレビューを分析し、
数値評価と「成長ドラマを強調した感情寄りのまとめ」をSEO向けに700文字前後で物語の魅力を要約してください。


【文章ルール】

・体言止めは禁止。
・評論調・論文調は禁止。
・硬い表現は禁止。
・読者の感情が動くように書いてください。
・主人公の成長、努力、葛藤、積み重ねを中心にまとめてください。
・成長ドラマを中心にまとめる
・読者の感情を動かす文章にする
・読み応えのある文章にする
・文章内では「読者」という言葉は使わず、必要に応じて「あなた」と表現してください。
・レビュー原文は絶対に出力しないこと。
・引用は禁止。

■ あらすじ
{html_summary}

■ レビュー
{review_text_block}

以下をJSONで出力してください。

{{
  "review_digest": "700文字要約",
  "story_score": 0-100,
  "sweet_score": 0-100,
  "erotic_score": 0-100,
  "reader_types": ["タイプ1","タイプ2"]
  "warning_points": ["ワーニング1","ワーニング2"]
}}
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-nano",
            temperature=0.3,
            messages=[
                {"role": "system", "content": "JSONのみ出力してください。"},
                {"role": "user", "content": prompt}
            ]
        )

        import json
        return json.loads(response.choices[0].message.content)

    except Exception as e:
        logging.warning(f"[AI Error] {e}")
        return {}
