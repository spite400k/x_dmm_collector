#!/usr/bin/env python3
"""DDL / SQL ファイルを Postgres に実行する。

例:
  .venv\\Scripts\\python.exe scripts/manual/run_sql.py db/DDL/ddl6_safe_generated_at.sql
  .venv\\Scripts\\python.exe scripts/manual/run_sql.py db/DDL/ddl6_safe_generated_at.sql --prefix MESUGAKI_DB
  .venv\\Scripts\\python.exe scripts/manual/run_sql.py db/DDL/ddl7_tachiyomi_page_count.sql --prefix DB2
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dotenv import load_dotenv

from db.postgres_connect import connect_from_env

load_dotenv()

ROOT = Path(__file__).resolve().parents[2]


def run_sql_file(sql_path: Path, *, prefix: str) -> None:
    if not sql_path.is_file():
        raise SystemExit(f"SQL ファイルが見つかりません: {sql_path}")

    sql = sql_path.read_text(encoding="utf-8").strip()
    if not sql:
        raise SystemExit(f"SQL が空です: {sql_path}")

    # connect_from_env は prefix="DB" で DB_URL / DB_HOST を読む
    conn = connect_from_env(prefix, label=prefix)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        print(f"OK: {sql_path} を {prefix} に適用しました")
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="SQL ファイルを Postgres に実行")
    parser.add_argument(
        "sql_file",
        type=Path,
        help="実行する .sql のパス（リポジトリ相対可）",
    )
    parser.add_argument(
        "--prefix",
        default="DB",
        help="接続環境変数プレフィックス（DB / MESUGAKI_DB / DB2 など）。デフォルト: DB",
    )
    args = parser.parse_args()

    sql_path = args.sql_file
    if not sql_path.is_absolute():
        sql_path = (ROOT / sql_path).resolve()

    run_sql_file(sql_path, prefix=args.prefix)


if __name__ == "__main__":
    main()
