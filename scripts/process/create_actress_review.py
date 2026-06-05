import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# main_create_actress_ai.py

import argparse
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
あなたはAV作品を長年見てきた熱心なファン兼レビュアーです。
「この女優、どんな人で、なぜ好かれるのか」を、読者の心が動く語り口で書いてください。

【事実の扱い】
・提供された情報だけを根拠に書く（推測・創作・架空の経歴は禁止）
・情報が少ない場合は、わかる範囲を温かく紹介する
・「情報が限定的」「照合すると」「二次情報」など、データ分析の前置きは書かない

【文章スタイル】
・一人称・二人称を交えた、レビュアーが語りかける口調
・読者の感情が動く、読み応えのある文章
・体言止め・評論調・論文調・マーケティング調は禁止
・「あなた」で語りかけてよい（「読者」という語は使わない）
・誹謗中傷禁止

【絶対に書かないこと】
・SEO、検索、キーワード、コンテンツ整備、購入行動、プロモーション戦略
・記事作成・サイト運営・データ分析の話
・AI生成の説明、開発者向けの解説
・「〜が重要な参照ポイント」「客観的に把握」「分析の鍵」などの調査レポート表現

【各フィールドの書き方】（各200〜350文字、3項目合計で800〜1000文字）

ai_summary:
  第一印象・外見の特徴・雰囲気・プロフィールから伝わる人柄を、ファン目線で紹介する。

ai_career:
  デビューからの歩み・作品数・活動期間・ジャンルの広がりを、キャリアの物語として語る。
  調査手順や分析方法ではなく、「どんな作品を重ねてきた女優か」を伝える。

ai_appeal:
  ファンが惹かれる理由を、演技・表情・役柄との相性・作品での見せ方など具体的な魅力で語る。
  人気の根拠を感情豊かに伝え、最後までレビュー本文のトーンを保つ。

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
"ai_summary": "女優の特徴・第一印象",
"ai_career": "キャリアの歩みと出演傾向",
"ai_appeal": "ファンが惹かれる理由"
}}
"""

    try:

        response = client.chat.completions.create(
            model="gpt-5.4-nano",
            messages=[
                {
                    "role": "system",
                    "content": """
あなたはAV作品レビューサイトで活動する、経験豊富なレビュアーです。
作品を愛するファンの気持ちを代弁し、情感のあるレビュー本文だけを書きます。

禁止: SEO・検索・キーワード・マーケティング・記事運営・データ分析・AI言及・調査レポート調
文体: 自然な日本語、語りかける口調、体言止め・評論調・論文調は禁止
分量: 3フィールド合計800〜1000文字
出力: JSONのみ
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

def get_actresses_without_ai():

    response = supabase.table("mst_actress") \
        .select("*") \
        .is_("ai_summary", "null") \
        .limit(BATCH_SIZE) \
        .execute()

    return response.data or []


def get_actresses_by_ids(actress_ids):

    response = supabase.table("mst_actress") \
        .select("*") \
        .in_("actress_id", actress_ids) \
        .execute()

    return response.data or []


def get_actress_by_name(name):

    response = supabase.table("mst_actress") \
        .select("*") \
        .eq("name", name) \
        .limit(1) \
        .execute()

    rows = response.data or []
    return rows[0] if rows else None


def get_target_actresses(*, actress_ids=None, name=None):

    if actress_ids:
        return get_actresses_by_ids(actress_ids)
    if name:
        actress = get_actress_by_name(name)
        return [actress] if actress else []
    return get_actresses_without_ai()


# =================================
# メイン処理
# =================================

def process_actresses(actresses, *, regenerate=False):

    if not actresses:
        logging.info("対象女優なし")
        return

    total = len(actresses)

    for i, actress in enumerate(actresses, start=1):

        actress_id = actress["actress_id"]
        name = actress["name"]
        mode = "再生成" if regenerate else "新規生成"

        logging.info(f"[{i}/{total}] AI{mode}: {name} (actress_id={actress_id})")

        ai = generate_actress_ai_profile(actress)

        if not ai:
            logging.warning("AI生成失敗: actress_id=%s", actress_id)
            continue

        save_actress_ai(actress_id, ai)

        time.sleep(SLEEP_TIME)


def parse_args(argv=None):

    parser = argparse.ArgumentParser(
        description="女優 AI レビュー生成バッチ",
    )
    parser.add_argument(
        "--actress-id",
        type=int,
        action="append",
        dest="actress_ids",
        metavar="ID",
        help="指定した actress_id を再生成（既存レビューを上書き。複数指定可）",
    )
    parser.add_argument(
        "--name",
        type=str,
        help="指定した名前の女優を再生成（既存レビューを上書き）",
    )
    return parser.parse_args(argv)


def main(argv=None):

    args = parse_args(argv)
    regenerate = bool(args.actress_ids or args.name)

    if regenerate:
        logging.info("=== 女優AI解説 再生成開始 ===")
    else:
        logging.info("=== 女優AI解説生成開始 ===")

    if args.actress_ids and args.name:
        logging.error("--actress-id と --name は同時に指定できません")
        sys.exit(1)

    actresses = get_target_actresses(
        actress_ids=args.actress_ids,
        name=args.name,
    )

    if regenerate and args.actress_ids:
        found_ids = {a["actress_id"] for a in actresses}
        missing_ids = [aid for aid in args.actress_ids if aid not in found_ids]
        if missing_ids:
            logging.warning("見つからない actress_id: %s", ", ".join(map(str, missing_ids)))

    if regenerate and args.name and not actresses:
        logging.warning("名前に一致する女優が見つかりません: %s", args.name)

    process_actresses(actresses, regenerate=regenerate)

    logging.info("🎉 女優AI解説生成完了")


if __name__ == "__main__":
    main()