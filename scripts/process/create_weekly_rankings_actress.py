import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from datetime import date, timedelta
import logging
import os

import psycopg2
from dotenv import load_dotenv
from openai import OpenAI
from psycopg2.extras import RealDictCursor

from utils.logger import setup_logger

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

setup_logger("main_create_weekly_rankings_actress.log")

RELEASE_WINDOW_DAYS = 31
TOP_N = 20


def get_connection():
    try:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST"),
            dbname=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            port=os.getenv("DB_PORT", 5432),
            sslmode="require",
        )
        conn.autocommit = False
        return conn
    except Exception:
        logging.exception("DB接続失敗")
        raise


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


def build_slug(year: int, week: int) -> str:
    return f"actress-{year}-week{week:02d}"


def generate_ai_summary(year: int, week: int, rows: list[dict]) -> str | None:
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
                f"{row['rank']}位: {row['name']} "
                f"スコア{row['ranking_score']} "
                f"対象作品{row['work_count']}本 "
                f"レビュー合計{row['total_review_count']}件 "
                f"平均評価{row['avg_rating']} "
                f"お気に入り{row['favorite_count']} "
                f"{change}"
            )

        prompt = f"""
あなたは日本のAV市場に詳しいSEOライターです。

{year}年第{week}週の女優人気ランキングTOP20の総評を書いてください。

▼ランキング上位データ
{chr(10).join(ranking_text)}

▼条件
・300〜500文字
・自然で読みやすい日本語
・順位変動や初登場の女優を分析
・作品数・レビュー傾向・お気に入り数も分析
・市場トレンド視点を含める
・SEOを意識
・誹謗中傷や過激な表現は避ける
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


def fetch_top_actresses(cur, release_date: str, snapshot_date: date) -> list[dict]:
    cur.execute(
        """
        WITH scored_works AS (
            SELECT
                (actress_id_text.value)::integer AS actress_id,
                s.final_score,
                s.review_count,
                s.avg_rating
            FROM trn_dmm_items c
            JOIN LATERAL (
                SELECT *
                FROM trn_dmm_score_history s
                WHERE s.content_id = c.content_id
                ORDER BY s.snapshot_date DESC
                LIMIT 1
            ) s ON true
            CROSS JOIN LATERAL jsonb_array_elements_text(c.actress_ids::jsonb) AS actress_id_text(value)
            WHERE c.actress_ids IS NOT NULL
              AND btrim(c.actress_ids) NOT IN ('', '[]')
              AND c.release_date >= %s
              AND c.service = 'digital'
              AND c.floor IN ('videoc', 'videoa')
              AND s.final_score IS NOT NULL
              AND actress_id_text.value ~ '^[0-9]+$'
        ),
        actress_scores AS (
            SELECT
                actress_id,
                ROUND(AVG(final_score)::numeric, 2) AS ranking_score,
                COUNT(*)::integer AS work_count,
                COALESCE(SUM(review_count), 0)::integer AS total_review_count,
                ROUND(AVG(avg_rating)::numeric, 2) AS avg_rating
            FROM scored_works
            GROUP BY actress_id
        )
        SELECT
            s.actress_id,
            m.name,
            s.ranking_score,
            s.work_count,
            s.total_review_count,
            s.avg_rating,
            m.favorite_count,
            m.works_count
        FROM actress_scores s
        JOIN mst_actress m ON m.actress_id = s.actress_id
        ORDER BY
            s.ranking_score DESC,
            s.total_review_count DESC,
            m.favorite_count DESC NULLS LAST,
            s.work_count DESC
        LIMIT %s
        """,
        (release_date, TOP_N),
    )
    rows = cur.fetchall()
    for row in rows:
        row["snapshot_date"] = snapshot_date
    return rows


def generate_weekly_ranking(conn) -> None:
    year, week = get_year_week()
    slug = build_slug(year, week)

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT 1
            FROM dmm_actress_weekly_rankings
            WHERE slug = %s
            LIMIT 1
            """,
            (slug,),
        )
        if cur.fetchone():
            logging.info("Already exists: %s", slug)
            return

        cur.execute("SELECT MAX(snapshot_date) AS snapshot_date FROM trn_dmm_score_history")
        snapshot_row = cur.fetchone()
        if not snapshot_row or not snapshot_row["snapshot_date"]:
            logging.warning("snapshot_dateが存在しません")
            return

        snapshot_date = snapshot_row["snapshot_date"]
        release_date = (date.today() - timedelta(days=RELEASE_WINDOW_DAYS)).isoformat()

        rows = fetch_top_actresses(cur, release_date, snapshot_date)
        if not rows:
            logging.warning("女優ランキング対象データがありません")
            return

        prev_year, prev_week = get_previous_year_week()
        cur.execute(
            """
            SELECT actress_id, rank
            FROM dmm_actress_weekly_rankings
            WHERE year = %s AND week = %s
            """,
            (prev_year, prev_week),
        )
        prev_rank_map = {r["actress_id"]: r["rank"] for r in cur.fetchall()}

        for idx, row in enumerate(rows):
            current_rank = idx + 1
            prev_rank = prev_rank_map.get(row["actress_id"])
            row["rank"] = current_rank
            row["prev_rank"] = prev_rank
            row["rank_diff"] = (prev_rank - current_rank) if prev_rank else None
            row["is_new"] = prev_rank is None

        summary_text = generate_ai_summary(year, week, rows)
        if summary_text:
            cur.execute(
                """
                INSERT INTO dmm_actress_weekly_ranking_pages
                (slug, year, week, summary)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (slug) DO NOTHING
                """,
                (slug, year, week, summary_text),
            )

        for row in rows:
            cur.execute(
                """
                INSERT INTO dmm_actress_weekly_rankings
                (slug, year, week, rank, actress_id, name,
                 ranking_score, work_count, total_review_count, avg_rating,
                 favorite_count, works_count, snapshot_date)
                VALUES (%s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s)
                """,
                (
                    slug,
                    year,
                    week,
                    row["rank"],
                    row["actress_id"],
                    row["name"],
                    row["ranking_score"],
                    row["work_count"],
                    row["total_review_count"],
                    row["avg_rating"],
                    row["favorite_count"],
                    row["works_count"],
                    row["snapshot_date"],
                ),
            )

        logging.info("Generated actress weekly ranking: %s (%s件)", slug, len(rows))


def main():
    logging.info("=== 女優週次ランキング生成開始 ===")

    conn = None
    try:
        conn = get_connection()
        generate_weekly_ranking(conn)
        conn.commit()
        logging.info("=== 女優週次ランキング生成完了 ===")
    except Exception:
        if conn:
            conn.rollback()
        logging.exception("女優週次ランキング生成失敗")
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    main()
