import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor

from db.postgres_connect import connect_from_env

load_dotenv()

year, week = date.today().isocalendar().year, date.today().isocalendar().week
today = date.today().isoformat()
release_min = (date.today() - timedelta(days=31)).isoformat()
slug = f"digital-videoa-{year}-week{week:02d}"

conn = connect_from_env("DB")
with conn.cursor(cursor_factory=RealDictCursor) as cur:
    cur.execute(
        """
        SELECT r.rank, r.content_id, r.final_score, r.review_count, r.avg_rating,
               i.title, i.release_date
        FROM dmm_weekly_rankings r
        JOIN trn_dmm_items i ON i.content_id = r.content_id
        WHERE r.slug = %s
        ORDER BY r.rank
        """,
        (slug,),
    )
    rows = cur.fetchall()
    print(f"=== videoa week35 ranking ({len(rows)} items) ===")
    for row in rows:
        future = " [FUTURE]" if row["release_date"] > today else ""
        title = (row["title"] or "")[:50]
        print(
            f"{row['rank']:2d}. score={row['final_score']} reviews={row['review_count']} "
            f"release={row['release_date']}{future} | {title}"
        )

    cur.execute(
        """
        SELECT COUNT(*) AS cnt FROM trn_dmm_items c
        JOIN LATERAL (
            SELECT * FROM trn_dmm_score_history s
            WHERE s.content_id = c.content_id ORDER BY s.snapshot_date DESC LIMIT 1
        ) s ON true
        WHERE c.service='digital' AND c.floor='videoa'
          AND c.release_date >= %s AND c.release_date <= %s
          AND s.final_score > 0 AND s.review_count > 0
        """,
        (release_min, today),
    )
    print(f"\nEligible released pool: {cur.fetchone()['cnt']} items")

    cur.execute(
        """
        SELECT COUNT(*) AS cnt FROM trn_dmm_items c
        JOIN LATERAL (
            SELECT * FROM trn_dmm_score_history s
            WHERE s.content_id = c.content_id ORDER BY s.snapshot_date DESC LIMIT 1
        ) s ON true
        WHERE c.service='digital' AND c.floor='videoa'
          AND c.release_date > %s
        """,
        (today,),
    )
    print(f"Future pool: {cur.fetchone()['cnt']} items")

conn.close()
