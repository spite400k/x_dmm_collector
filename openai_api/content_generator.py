import os
import logging
import json
from openai import OpenAI
from dotenv import load_dotenv
from bs4 import BeautifulSoup
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

# ログ設定
os.makedirs("logs", exist_ok=True)
logging.basicConfig(filename="logs/scraper.log", level=logging.INFO)

# 環境変数読み込み
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def get_page_source_with_age_verification(url: str) -> str:
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    try:
        driver.get(url)
        driver.implicitly_wait(5)

        # 年齢確認「はい」ボタンが存在する場合はクリック
        try:
            yes_button = driver.find_element(By.LINK_TEXT, "はい")
            yes_button.click()
            driver.implicitly_wait(5)
        except Exception:
            pass

        return driver.page_source
    finally:
        driver.quit()

def get_dmm_comment_text(url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0",
    }
    res = requests.get(url, headers=headers, timeout=10)
    res.raise_for_status()

    soup = BeautifulSoup(res.text, "html.parser")
    comment_div = soup.select_one("div.mg-b20.lh4")

    if comment_div:
        text = comment_div.get_text(separator="\n").strip()
        return text
    else:
        return ""

def scrape_product_details(url: str) -> dict:
    try:
        html = get_page_source_with_age_verification(url)
        soup = BeautifulSoup(html, "html.parser")

        summary_el = soup.select_one(".summary__txt")
        comment_el = soup.select_one(".trailer__txt")
        fallback_el = soup.select_one("div.mg-b20.lh4")

        summary = summary_el.get_text(strip=True) if summary_el else ""
        comment = comment_el.get_text(strip=True) if comment_el else ""

        if not summary and fallback_el:
            summary = fallback_el.get_text(separator="\n").strip()
            
            if not summary:
                # コメントがない場合は、別の場所から取得する
                # ▼ 商品情報エリアからあらすじを抽出（DMM動画用）
                # 特定のdiv構造： <div class="mg-b20 lh4"><p>作品説明</p></div>
                comment_div = get_dmm_comment_text(url)
                if comment_div:
                    summary = comment_div


        return summary

    except Exception as e:
        logging.warning(f"[Scrape Error] URL: {url} → {e}")
        return ""


def generate_content(item: dict) -> dict:
    title = item.get("title", "")
    genres_raw = item.get("iteminfo", {}).get("genre", [])
    genres = [g["name"] for g in genres_raw]
    review_score = item.get("review", {}).get("average", "不明")
    review_count = item.get("review", {}).get("count", 0)
    maker = item.get("iteminfo", {}).get("maker", [{}])[0].get("name", "")
    series = item.get("iteminfo", {}).get("series", [{}])[0].get("name", "")
    release_date = item.get("date", "")

    # HTMLからあらすじを取得
    url = item.get("URL", "")
    html_summary = scrape_product_details(url)

    prompt = f"""
    以下の情報をもとに、同人作品の紹介文を生成してください。
    出力はJSON形式で、3つの項目（感想・概要・買いたくなるポイント）を含めてください。
    値はテンプレではなく、実際に生成された日本語文で埋めてください。

    ### 入力情報:
    - タイトル: {title}
    - ジャンル: {genres}
    - レビュー: {review_score}点（{review_count}件）
    - サークル: {maker}
    - 発売日: {release_date}
    - シリーズ: {series or '該当なし'}

    ▼ HTMLから取得した内容:
    - あらすじ・紹介文: {html_summary}

    ### 出力形式（例）:
    ```json
    {{
        "auto_comment": "10～20文字の一言感想",
        "auto_summary": "50〜80文字の概要",
        "auto_point": "30〜50文字の買いたくなるポイント"
    }}
    テンプレのままではなく、内容を埋めて出力してください。
    次の文言は使用禁止「一冊」「作品」「一作」「話」「！」
    「の末路…」で終えるようにしてください。
    """

    logging.info("[OpenAI] Generating content for: %s", title)
    # logging.info("[OpenAI] Prompt:\n%s", prompt)

    try:
        response = client.chat.completions.create(
            model="gpt-4.1-nano",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.85
        )

        content = response.choices[0].message.content.strip()
        logging.debug("[OpenAI] Raw response:\n%s", content)

        # JSONブロックのみを抽出（```json ... ```を除去）
        json_str = content
        if "```" in content:
            json_str = content.split("```")[1]
            if json_str.startswith("json"):
                json_str = json_str[4:].strip()

        result = json.loads(json_str)
        return {
            "auto_comment": result.get("auto_comment", ""),
            "auto_summary": result.get("auto_summary", ""),
            "auto_point": result.get("auto_point", "")
        }

    except Exception as e:
        logging.error("[OpenAI ERROR] Failed to generate content for '%s': %s", title, str(e))
        return {
            "auto_comment": "",
            "auto_summary": "",
            "auto_point": ""
        }
