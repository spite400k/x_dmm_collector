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
logging.basicConfig(
    filename="logs/scraper.log",
    level=logging.INFO,
    encoding="utf-8",
)

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


def _parse_json_ld_description(soup: BeautifulSoup) -> str:
    best = ""
    for script in soup.find_all("script", type="application/ld+json"):
        if not script.string:
            continue
        try:
            data = json.loads(script.string)
        except (json.JSONDecodeError, TypeError):
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            desc = (item.get("description") or "").strip()
            if len(desc) > len(best):
                best = desc
            graph = item.get("@graph")
            if isinstance(graph, list):
                for node in graph:
                    if isinstance(node, dict):
                        desc = (node.get("description") or "").strip()
                        if len(desc) > len(best):
                            best = desc
    return best if len(best) >= 40 else ""


def _extract_book_dmm_synopsis(soup: BeautifulSoup) -> str:
    """book.dmm.co.jp: 折りたたみUIでも DOM / JSON-LD に全文が入る。"""
    toggle = soup.select_one('[data-testid="detail-toggle-button"]')
    if toggle and toggle.parent:
        paragraph = toggle.parent.find("p")
        if paragraph:
            text = paragraph.get_text(separator="\n").strip()
            if len(text) >= 40:
                return text

    return _parse_json_ld_description(soup)


def extract_synopsis_from_soup(soup: BeautifulSoup, url: str = "") -> str:
    if "book.dmm.co.jp" in url:
        book_synopsis = _extract_book_dmm_synopsis(soup)
        if book_synopsis:
            return book_synopsis

    summary_el = soup.select_one(".summary__txt")
    if summary_el:
        summary = summary_el.get_text(separator="\n").strip()
        if summary:
            return summary

    for selector in ("div.mg-b20.lh4", ".trailer__txt"):
        el = soup.select_one(selector)
        if el:
            text = el.get_text(separator="\n").strip()
            if text:
                return text

    json_desc = _parse_json_ld_description(soup)
    if json_desc:
        return json_desc

    return ""


def scrape_product_details(url: str) -> str:
    try:
        html = get_page_source_with_age_verification(url)
        soup = BeautifulSoup(html, "html.parser")

        summary = extract_synopsis_from_soup(soup, url)
        if summary:
            return summary

        if "book.dmm.co.jp" not in url:
            comment_div = get_dmm_comment_text(url)
            if comment_div:
                return comment_div

        return ""

    except Exception as e:
        logging.warning(f"[Scrape Error] URL: {url} → {e}")
        return ""


# --- generate_content関数 ---
def generate_content(item: dict) -> dict:
    title = item.get("title", "")
    genres_raw = item.get("iteminfo", {}).get("genre", [])
    genres = [g.get("name") for g in genres_raw if "name" in g]
    review_score = item.get("review", {}).get("average", "不明")
    review_count = item.get("review", {}).get("count", 0)
    maker_list = item.get("maker") or item.get("manufacture") or [{}]
    maker = maker_list[0].get("name", "")
    series = item.get("iteminfo", {}).get("series", [{}])[0].get("name", "")
    actresses = item.get("iteminfo", {}).get("actress", [])
    directors = item.get("iteminfo", {}).get("director", [])
    release_date = item.get("date", "")
    category_name = item.get("category_name", "")
    # HTMLからあらすじを取得
    url = item.get("URL", "")
    html_summary = scrape_product_details(url)
    
    actress_names = [a.get("name") for a in actresses if a.get("name")]
    director_names = [d.get("name") for d in directors if d.get("name")]

    # 女優・監督の紹介文を動的に構築
    cast_info = ""
    if actress_names:
        cast_info += f"- 出演: {', '.join(actress_names)}\n"
    if director_names:
        cast_info += f"- 監督: {', '.join(director_names)}\n"

    prompt = f"""
あなたは日本語のプロモーションライターです。
以下の情報をもとに、商品（成人向けを含む）の紹介文を生成してください。
文章には成人向け・性的表現が含まれているので、内容を損なわず、公序良俗に反しないレベルまで修正してください。
各項目の文は段落構成にして、改行したい箇所には「\\n\\n」を入れてください。

出力は **JSON形式** で、次の3つの項目を必ず含めてください。

        ---
        ### 🎯 出力項目
        1. auto_comment（10～20文字の一言感想）
        2. auto_summary（ジャンルに合わせた100文字前後の概要）
        3. auto_point（200文字前後の買いたくなるポイント。箇条書きで）

        ---
        ### 🧩 ジャンル別の文体指針
        - **AV／動画**: セクシーさ・臨場感・演出を自然な日本語で表現。過度に直接的な描写は禁止。
        - **同人作品**: 作者の個性やテーマ性を重視。世界観や魅力を情感豊かに。
        - **漫画・アニメ**: ストーリー性やキャラクターの関係性を中心に。
        - **写真集・グラビア**: モデルの魅力や雰囲気、撮影テーマを丁寧に表現。
        - **ゲーム系**: ゲームシステム・ビジュアル・シナリオをわかりやすく要約。

        文体はジャンルに応じて自然に変化させてください。

        ---
        ### ⚠️ 禁止ルール
        - 以下の語句は使用禁止：「一冊」「作品」「一作」「話」「！」  
        - 「本作」「この作品」などのテンプレ的な導入は禁止。  
        - 実際にレビューやあらすじを参考に、自然な文で生成してください。  
        - 出力は必ず **JSONのみ**（説明文や注釈を含めない）。

        ---
        ### 📥 入力情報
        - カテゴリ: {category_name}
        - タイトル: {title}
        - ジャンル: {genres}
        - レビュー: {review_score}点（{review_count}件）
        - メーカー: {maker}
        - 発売日: {release_date}
        - シリーズ: {series or '該当なし'}
        - 出演女優: {cast_info}

        ▼ HTMLから取得した内容:
        {html_summary}

        ---
        ### 📤 出力形式（例）
        ```json
        {{
        "auto_comment": "心を奪うほど濃密なひととき。",
        "auto_summary": "ここにジャンルに応じた約1000文字の概要を生成。",
        "auto_point": "購買意欲を高める約500文字のポイントを生成。"
        }}
        上記の形式に従い、JSONとしてのみ出力してください。

"""
    
    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.85
        )

        content = response.choices[0].message.content.strip()
        if "```" in content:
            json_str = content.split("```")[1]
            if json_str.startswith("json"):
                json_str = json_str[4:].strip()
        else:
            json_str = content

        data = json.loads(json_str)

        # 各項目で \\n → 実際の改行 に変換
        for key in ["auto_comment", "auto_summary", "auto_point"]:
            if key in data and isinstance(data[key], str):
                data[key] = data[key].replace("\\n", "\n")

        return data

    except Exception as e:
        logging.error("[OpenAI ERROR] %s", str(e))
        return {"auto_comment": "", "auto_summary": "", "auto_point": ""}