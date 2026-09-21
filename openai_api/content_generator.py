import os
import logging
import json
from openai import OpenAI
from dotenv import load_dotenv
from bs4 import BeautifulSoup
import requests
from selenium.webdriver.common.by import By

from openai_api.config import OPENAI_MODEL
from utils.chromedriver import create_chrome_driver, quit_chrome_driver

# 環境変数読み込み
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def get_page_source_with_age_verification(url: str) -> str:
    driver = create_chrome_driver(page_load_timeout=60)

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
        quit_chrome_driver(driver)

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
あなたは成人向けレビューサイトで活動する、経験豊富なレビュアーです。
以下の情報をもとに、サイト掲載用の感想文を生成してください。
読者の感情が動く、推敲済みの文章を書いてください。
成人向け・性的表現は内容を損なわず、公序良俗に反しないレベルに抑えてください。
各項目は段落構成にし、改行したい箇所には「\\n\\n」を入れてください。

出力は **JSON形式** で、次の3つの項目を必ず含めてください。

        ---
        ### 🎯 出力項目
        1. auto_comment（10～20文字の一言感想。余韻が残る短い一文）
        2. auto_summary（600〜900文字の情感ある感想文。複数段落）
        3. auto_point（200〜400文字。魅力ポイントを箇条書き。押し売りせず具体的に）

        ---
        ### ✍️ auto_summary の書き方（最重要）
        - 観たあとの余韻・印象から入り、そのあと出演者・演出・見どころへ進む
        - 評論調・分析レポート調・プレス原稿調は禁止（「〜場になっている」「〜を保っている」「訴求する」「正解を示す」など）
        - 抽象語の連発を避け、表情・距離感・関係性・リズムなど画面が浮かぶ言い方にする
        - 出演者が複数いる場合は役割や魅力を分けて書く。いちばん刺さった魅力は厚めに
        - 賛否の前置きや防御的な言い回し（「過激だが」「話題になるが過剰ではない」の連発）を減らす
        - 末尾はマーケ調の強いおすすめではなく、個人の感想として自然に締める
        - 日本語のみ。英語混入（density, balance など）は禁止
        - 体言止めの連続を避け、読みやすい口語寄りの文にする

        ---
        ### 🧩 ジャンル別の文体指針
        - **AV／動画**: セクシーさ・臨場感・演出を自然な日本語で。過度に直接的な描写は禁止
        - **同人**: 作者の個性やテーマ性を重視。世界観や魅力を情感豊かに
        - **漫画・アニメ**: ストーリー性やキャラクターの関係性を中心に
        - **写真集・グラビア**: モデルの魅力や雰囲気、撮影テーマを丁寧に
        - **ゲーム系**: システム・ビジュアル・シナリオをわかりやすく

        ---
        ### ⚠️ 禁止ルール
        - 以下の語句は使用禁止：「一冊」「作品」「一作」「話」「！」
        - 「本作」「この作品」などのテンプレ的な導入は禁止
        - SEO・購入行動・プロモーション戦略・データ分析の話は禁止
        - 「強くおすすめできる」「購買意欲を高める」「見応えのある娯楽として訴求」など広告コピー調は禁止
        - 入力のあらすじ・レビュー情報を根拠にし、ない事実は創作しない
        - 出力は必ず **JSONのみ**（説明文や注釈を含めない）

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
        "auto_comment": "観終わったあと余韻が残る。",
        "auto_summary": "（600〜900文字。余韻から入り、出演者の魅力と演出を情感を込めて語る感想文）",
        "auto_point": "・〇〇の表情と距離感が印象的\\n・演出のリズムが見やすい\\n・終盤にかけて感情の波が大きい"
        }}
        上記の形式に従い、JSONとしてのみ出力してください。

"""
    
    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
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