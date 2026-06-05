import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# main_create_actress_ai.py

import json
import os
import time
import logging
from datetime import datetime

from openai import OpenAI
from db.supabase_client import supabase
from utils.logger import setup_logger

setup_logger("create_actress_ai.log")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

BATCH_SIZE = 1000
SLEEP_TIME = 1


# =================================
# AI解説生成
# =================================

def generate_actress_ai_profile(actress):

    name = actress.get("name")
    height = actress.get("height")
    bust = actress.get("bust")
    cup = actress.get("cup")
    waist = actress.get("waist")
    hip = actress.get("hip")
    prefectures = actress.get("prefectures")
    hobby = actress.get("hobby")

    profile = actress.get("profile")
    career_text = actress.get("career_text")
    awards = actress.get("awards")

    favorite_count = actress.get("favorite_count")
    works_count = actress.get("works_count")
    debut_date = actress.get("debut_date")
    fanza_activity = actress.get("fanza_activity")

    prompt = f"""
あなたはAV作品を探しているユーザー向けの
レビューサイトのライターです。

訪問者が
「この女優はどんな魅力があるのか」
を理解できる解説を書いてください。

【重要ルール】

・事実が不明な内容は推測しない
・架空の経歴を作らない
・公開情報が少ない場合は
  「公開情報は多くありませんが〜」
  のように説明する

【文章ルール】

・自然な日本語
・レビュー記事本文
・誹謗中傷禁止
・800〜1000文字

【解説観点】

・外見の特徴
・出演作品の傾向
・ジャンル傾向
・ファンから支持される理由

【女優情報】

名前: {name}

スタイル
身長: {height}
バスト: {bust}
カップ: {cup}
ウエスト: {waist}
ヒップ: {hip}

出身: {prefectures}
趣味: {hobby}

デビュー日: {debut_date}
FANZA活動: {fanza_activity}

作品数: {works_count}
お気に入り数: {favorite_count}

プロフィール:
{profile}

経歴:
{career_text}

受賞:
{awards}

【出力(JSON)】

{{
"ai_summary": "女優の特徴",
"ai_career": "出演作品の傾向",
"ai_appeal": "人気の理由"
}}
"""

    try:

        response = client.chat.completions.create(
            model="gpt-5.4-nano",
            messages=[
                {
                    "role": "system",
                    "content": """
あなたはAV作品レビューサイトの編集ライターです。

禁止事項
・SEOの話
・記事作成の説明
・AI生成の説明
・開発者向け解説

文章ルール
・自然な日本語
・解説記事本文
・誹謗中傷禁止
・800〜1000文字

JSONのみ出力
"""
                },
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"}
        )

        content = response.choices[0].message.content

        return json.loads(content)

    except Exception as e:
        logging.error(f"AI生成失敗: {e}")
        return None


# =================================
# DB保存
# =================================

def save_actress_ai(actress_id, ai):

    data = {
        "ai_summary": ai.get("ai_summary"),
        "ai_career": ai.get("ai_career"),
        "ai_appeal": ai.get("ai_appeal"),
        "ai_generated_at": datetime.utcnow().isoformat()
    }

    supabase.table("mst_actress") \
        .update(data) \
        .eq("actress_id", actress_id) \
        .execute()

    logging.info(f"AI解説保存: {actress_id}")


# =================================
# 女優取得
# =================================

def get_target_actresses():

    response = supabase.table("mst_actress") \
        .select("*") \
        .is_("ai_summary", "null") \
        .limit(BATCH_SIZE) \
        .execute()

    return response.data or []


# =================================
# メイン処理
# =================================

def main():

    logging.info("=== 女優AI解説生成開始 ===")

    actresses = get_target_actresses()

    if not actresses:
        logging.info("対象女優なし")
        return

    total = len(actresses)

    for i, actress in enumerate(actresses, start=1):

        actress_id = actress["actress_id"]
        name = actress["name"]

        logging.info(f"[{i}/{total}] AI生成: {name}")

        ai = generate_actress_ai_profile(actress)

        if not ai:
            logging.warning("AI生成失敗")
            continue

        save_actress_ai(actress_id, ai)

        time.sleep(SLEEP_TIME)

    logging.info("🎉 女優AI解説生成完了")


if __name__ == "__main__":
    main()