import os
import logging
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def generate_content(item: dict) -> dict:
    title = item.get("title", "")
    genres_raw = item.get("iteminfo", {}).get("genre", [])
    genres = [g["name"] for g in genres_raw]
    review_score = item.get("review", {}).get("average", "不明")
    review_count = item.get("review", {}).get("count", 0)
    maker = item.get("iteminfo", {}).get("maker", [{}])[0].get("name", "")
    series = item.get("iteminfo", {}).get("series", [{}])[0].get("name", "")
    release_date = item.get("date", "")

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

    ### 出力形式（例）:
    ```json
    {{
        "auto_comment": "60〜100文字の感想文",
        "auto_summary": "50〜80文字の概要",
        "auto_point": "30〜50文字の買いたくなるポイント"
    }}
    テンプレのままではなく、内容を埋めて出力してください。
    """

    logging.info("[OpenAI] Generating JSON content for: %s", title)

    try:
        response = client.chat.completions.create(
            model="gpt-4",
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