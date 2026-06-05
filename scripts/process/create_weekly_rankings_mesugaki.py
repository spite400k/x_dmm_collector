import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

"""
メスガキサイト用: 週間ランキングを作成する。

接続先はメスガキ用 Supabase Postgres（MESUGAKI_DB_* または MESUGAKI_SUPABASE_URL からホストを導出）。
環境変数:
  - MESUGAKI_DB_PASSWORD: 必須（メスガキ DB の postgres パスワード）
  - MESUGAKI_DB_HOST: 任意（省略時は MESUGAKI_SUPABASE_URL から db.{ref}.supabase.co を生成）
  - MESUGAKI_DB_NAME / MESUGAKI_DB_USER / MESUGAKI_DB_PORT: 任意
"""
from datetime import date, timedelta
import os
from urllib.parse import urlparse
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
import logging
from openai import OpenAI

from utils.logger import setup_logger

DEFAULT_MESUGAKI_SUPABASE_URL = "https://xootrpeprhlgzajbcnus.supabase.co"

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

# ----------------------------------------------------
# 設定
# ----------------------------------------------------
setup_logger("main_create_weekly_rankings_mesugaki.log")


def _mesugaki_db_host() -> str:
    explicit = os.getenv("MESUGAKI_DB_HOST")
    if explicit:
        return explicit
    url = os.getenv("MESUGAKI_SUPABASE_URL", DEFAULT_MESUGAKI_SUPABASE_URL)
    ref = urlparse(url).hostname.split(".")[0]
    return f"db.{ref}.supabase.co"


def get_connection():
    password = os.getenv("MESUGAKI_DB_PASSWORD")
    if not password:
        raise RuntimeError(
            "MESUGAKI_DB_PASSWORD が未設定です。"
            "メスガキ用 Supabase の Database password を .env に設定してください。"
        )
    try:
        conn = psycopg2.connect(
            host=_mesugaki_db_host(),
            dbname=os.getenv("MESUGAKI_DB_NAME", "postgres"),
            user=os.getenv("MESUGAKI_DB_USER", "postgres"),
            password=password,
            port=os.getenv("MESUGAKI_DB_PORT", 5432),
            sslmode="require",
        )
        conn.autocommit = False
        return conn
    except Exception:
        logging.exception("DB接続失敗（メスガキ）")
        raise


# ----------------------------------------------------
# ユーティリティ関数
# ----------------------------------------------------
def get_year_week(target_date=None):
    if target_date is None:
        target_date = date.today()
    iso = target_date.isocalendar()
    return iso.year, iso.week


def get_previous_year_week(target_date=None):
    if target_date is None:
        target_date = date.today()
    prev_date = target_date - timedelta(days=7)
    iso = prev_date.isocalendar()
    return iso.year, iso.week


def generate_ai_summary(service, floor, year, week, rows):
    try:
        ranking_text = []

        for row in rows[:10]:
            change = ""
            if row["is_new"]:
                change = "（初登場）"
            elif row["rank_diff"] is not None:
                if row["rank_diff"] > 0:
                    change = f"（先週比 +{row['rank_diff']}）"
                elif row["rank_diff"] < 0:
                    change = f"（先週比 {row['rank_diff']}）"
                else:
                    change = "（順位変動なし）"

            ranking_text.append(
                f"{row['rank']}位: {row['title']} "
                f"レビュー{row['review_count']}件 "
                f"平均評価{row['avg_rating']} "
                f"{change}"
            )

        prompt = f"""
あなたは日本の電子書籍市場に詳しいSEOライターです。

{year}年第{week}週の{service}/{floor}ジャンル人気ランキングTOP20の総評を書いてください。

▼ランキング上位データ
{chr(10).join(ranking_text)}

▼条件
・300〜500文字
・自然で読みやすい日本語
・順位変動や初登場作品を分析
・レビュー数や評価傾向も分析
・市場トレンド視点を含める
・SEOを意識
・過激な表現は避け、一般向けに読みやすい表現にする
"""

        response = client.chat.completions.create(
            model="gpt-5.4-nano",
            messages=[
                {"role": "system", "content": "あなたはプロのランキング分析ライターです。"},
                {"role": "user", "content": prompt},
            ],
        )

        return response.choices[0].message.content.strip()

    except Exception:
        logging.exception("AI summary generation failed")
        return None


# ----------------------------------------------------
# 週次ランキング生成
# ----------------------------------------------------
def generate_weekly_ranking(conn, service, floor):
    year, week = get_year_week()

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            slug = f"{service}-{floor}-{year}-week{week:02d}"

            cur.execute(
                """
                SELECT 1
                FROM dmm_weekly_rankings
                WHERE slug = %s
                LIMIT 1
            """,
                (slug,),
            )

            if cur.fetchone():
                logging.info(f"Already exists: {service}/{floor}")
                return

            cur.execute(
                "SELECT MAX(snapshot_date) AS snapshot_date FROM trn_dmm_score_history"
            )
            snapshot_row = cur.fetchone()

            if not snapshot_row["snapshot_date"]:
                logging.warning("snapshot_dateが存在しません")
                return

            snapshot_date = snapshot_row["snapshot_date"]
            if snapshot_date is None:
                snapshot_date = date.today()

            release_date = (date.today() - timedelta(days=31)).isoformat()

            cur.execute(
                """
                SELECT
                    c.content_id,
                    c.title,
                    s.final_score,
                    s.review_count,
                    s.avg_rating
                FROM trn_dmm_items c
                JOIN LATERAL (
                    SELECT *
                    FROM trn_dmm_score_history s
                    WHERE s.content_id = c.content_id
                        AND c.release_date >= %s
                    ORDER BY s.snapshot_date DESC
                    LIMIT 1
                ) s ON true
                WHERE c.service = %s
                AND c.floor = %s
                AND s.final_score IS NOT NULL
                ORDER BY s.final_score DESC
                LIMIT 20
            """,
                (release_date, service, floor),
            )

            rows = cur.fetchall()

            if not rows:
                logging.warning(f"No ranking data for {service}/{floor}")
                return

            prev_year, prev_week = get_previous_year_week()

            cur.execute(
                """
                SELECT content_id, rank
                FROM dmm_weekly_rankings
                WHERE service = %s
                AND floor = %s
                AND year = %s
                AND week = %s
            """,
                (service, floor, prev_year, prev_week),
            )

            prev_rows = cur.fetchall()
            prev_rank_map = {r["content_id"]: r["rank"] for r in prev_rows}
            for idx, row in enumerate(rows):
                current_rank = idx + 1
                prev_rank = prev_rank_map.get(row["content_id"])

                if prev_rank:
                    rank_diff = prev_rank - current_rank
                else:
                    rank_diff = None

                row["rank"] = current_rank
                row["prev_rank"] = prev_rank
                row["rank_diff"] = rank_diff
                row["is_new"] = prev_rank is None

            summary_text = generate_ai_summary(service, floor, year, week, rows)

            if summary_text:
                cur.execute(
                    """
                    INSERT INTO dmm_weekly_ranking_pages
                    (slug, service, floor, year, week, summary)
                    VALUES (%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (slug) DO NOTHING
                """,
                    (slug, service, floor, year, week, summary_text),
                )

            for idx, row in enumerate(rows):
                rank = idx + 1

                cur.execute(
                    """
                    INSERT INTO dmm_weekly_rankings
                    (slug, service, floor, year, week, rank,
                    content_id, final_score,
                    review_count, avg_rating,
                    snapshot_date)
                    VALUES (%s,%s,%s,%s,%s,%s,
                            %s,%s,
                            %s,%s,
                            %s)
                """,
                    (
                        slug,
                        service,
                        floor,
                        year,
                        week,
                        rank,
                        row["content_id"],
                        row["final_score"],
                        row["review_count"],
                        row["avg_rating"],
                        snapshot_date,
                    ),
                )

            logging.info(f"Generated: {service}/{floor}")

    except Exception:
        logging.exception("Ranking generation failed")
        raise


def run_all_rankings(conn):
    categories = [
        ("ebook", "comic"),
        ("doujin", "digital_doujin"),
    ]
    for service, floor in categories:
        generate_weekly_ranking(conn, service, floor)


# ----------------------------------------------------
# メイン
# ----------------------------------------------------
def main():
    logging.info("=== メスガキ: 週次ランキング生成開始 ===")

    conn = None
    try:
        conn = get_connection()
        run_all_rankings(conn)
        conn.commit()
        logging.info("=== メスガキ: 週次ランキング生成完了 ===")

    except Exception:
        if conn:
            conn.rollback()
        logging.exception("メスガキ: 週次ランキング生成失敗")

    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    main()
