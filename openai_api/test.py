import os
import json
import logging
from openai import OpenAI
from dotenv import load_dotenv

# ログ設定
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    filename="logs/test_generate.log",
    level=logging.INFO,
    encoding="utf-8",
)

# 環境変数読み込み
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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
    html_summary = item.get("html_summary", "(テスト用のあらすじ)")

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

# --- Markdown整形関数 ---
def format_markdown(item: dict, content: dict) -> str:
    return f"""
# 🎬 {item['title']}

**カテゴリ:** {item.get('category_name', '')}  
**ジャンル:** {', '.join([g['name'] for g in item.get('iteminfo', {}).get('genre', [])])}  
**レビュー:** {item.get('review', {}).get('average', '不明')}点（{item.get('review', {}).get('count', 0)}件）  
**メーカー:** {item.get('maker', [{}])[0].get('name', '')}  
**発売日:** {item.get('date', '')}  
**出演:** {', '.join([a['name'] for a in item.get('iteminfo', {}).get('actress', [])]) if item.get('iteminfo', {}).get('actress') else '該当なし'}  
**監督:** {', '.join([d['name'] for d in item.get('iteminfo', {}).get('director', [])]) if item.get('iteminfo', {}).get('director') else '該当なし'}

---

## 💬 一言感想
{content.get('auto_comment', '')}

## 📝 概要
{content.get('auto_summary', '')}

## ⭐ 買いたくなるポイント
{content.get('auto_point', '')}
"""

#--- テスト用データ ---
test_item = {
    "title": "ももか先生の誘惑レッスン",
    "iteminfo": {
        "genre": [{"name": "教師"}, {"name": "コスプレ"}],
        "actress": [{"name": "相川ももか"}],
        "director": [{"name": "山田太郎"}]
    },
    "review": {"average": 4.5, "count": 28},
    "maker": [{"name": "FANZAオリジナル"}],
    "date": "2024-11-01",
    "category_name": "AV",
    "html_summary": "真面目な教師・ももか先生が、生徒との距離を縮めるために大胆な一歩を踏み出す――そんなドキドキの展開が待つ物語。"
}

#--- 実行 ---
if __name__ == "__main__":
    print("🔍 OpenAI接続テスト開始...")
    result = generate_content(test_item)
    print(result)
    markdown = format_markdown(test_item, result)
    print(markdown)
