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

import httpx
from openai import OpenAI
from db.supabase_client import supabase
from utils.logger import setup_logger
from utils.supabase_retry import execute_with_retry

setup_logger("create_actress_ai.log")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

BATCH_SIZE = 1000
SLEEP_TIME = 1

ACTRESS_SYSTEM_PROMPT = """
あなたはAV作品レビューサイトで活動する、経験豊富なレビュアーです。
作品を愛するファンの気持ちを代弁し、情感のあるレビュー本文を書きます。

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

【禁止事項】
・SEO、検索、キーワード、コンテンツ整備、購入行動、プロモーション戦略
・記事作成・サイト運営・データ分析の話
・AI生成の説明、開発者向けの解説
・「〜が重要な参照ポイント」「客観的に把握」「分析の鍵」などの調査レポート表現

【出力】
・JSONオブジェクトのみ出力
・ai_summary / ai_career / ai_appeal は各200〜350文字、3項目合計800〜1000文字
"""


def _format_actress_info(actress: dict) -> str:
    """空・null のフィールドを除いて女優情報ブロックを組み立てる。"""
    lines = []

    scalar_fields = [
        ("名前", actress.get("name")),
        ("身長", actress.get("height")),
        ("バスト", actress.get("bust")),
        ("カップ", actress.get("cup")),
        ("ウエスト", actress.get("waist")),
        ("ヒップ", actress.get("hip")),
        ("出身", actress.get("prefectures")),
        ("趣味", actress.get("hobby")),
        ("デビュー日", actress.get("debut_date")),
        ("FANZA活動", actress.get("fanza_activity")),
        ("作品数", actress.get("works_count")),
        ("お気に入り数", actress.get("favorite_count")),
    ]
    for label, value in scalar_fields:
        if value is not None and value != "":
            lines.append(f"{label}: {value}")

    for label, key in (
        ("プロフィール", "profile"),
        ("経歴", "career_text"),
        ("受賞", "awards"),
    ):
        value = actress.get(key)
        if value:
            lines.append(f"\n{label}:\n{value}")

    return "\n".join(lines) if lines else "（情報なし）"


# =================================
# AI解説生成
# =================================

def generate_actress_ai_profile(actress):

    actress_info = _format_actress_info(actress)

    prompt = f"""
以下の女優情報をもとに JSON を出力してください。

【各フィールドの内容】
- ai_summary: 第一印象・外見の特徴・雰囲気・プロフィールから伝わる人柄を、ファン目線で紹介
- ai_career: デビューからの歩み・作品数・活動期間・ジャンルの広がりを、キャリアの物語として語る
- ai_appeal: ファンが惹かれる理由を、演技・表情・役柄との相性・作品での見せ方など具体的な魅力で語る

【女優情報】
{actress_info}

【出力スキーマ】
{{
  "ai_summary": "...",
  "ai_career": "...",
  "ai_appeal": "..."
}}
"""

    try:

        response = client.chat.completions.create(
            model="gpt-5.4-nano",
            messages=[
                {"role": "system", "content": ACTRESS_SYSTEM_PROMPT},
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

    execute_with_retry(
        lambda: supabase.table("mst_actress")
        .update(data)
        .eq("actress_id", actress_id)
    )

    logging.info(f"AI解説保存: {actress_id}")


# =================================
# 女優取得
# =================================

def get_actresses_without_ai():

    response = execute_with_retry(
        lambda: supabase.table("mst_actress")
        .select("*")
        .is_("ai_summary", "null")
        .limit(BATCH_SIZE)
    )

    return response.data or []


def get_actresses_by_ids(actress_ids):

    response = execute_with_retry(
        lambda: supabase.table("mst_actress")
        .select("*")
        .in_("actress_id", actress_ids)
    )

    return response.data or []


def get_actress_by_name(name):

    response = execute_with_retry(
        lambda: supabase.table("mst_actress")
        .select("*")
        .eq("name", name)
        .limit(1)
    )

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

    try:
        actresses = get_target_actresses(
            actress_ids=args.actress_ids,
            name=args.name,
        )
    except httpx.ConnectError as exc:
        logging.error(
            "Supabase への接続に失敗しました。ネットワーク/DNS を確認してください: %s",
            exc,
        )
        sys.exit(1)

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