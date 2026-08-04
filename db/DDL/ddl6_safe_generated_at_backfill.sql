-- 既存で auto_summary がある行だけ Safe 済みにする
-- 空の auto_summary は safe_generated_at = NULL のまま
--
-- 実行例:
--   .venv\Scripts\python.exe scripts/manual/run_sql.py db/DDL/ddl6_safe_generated_at_backfill.sql

update public.trn_dmm_items
set safe_generated_at = coalesce(updated_at, now())
where safe_generated_at is null
  and coalesce(auto_summary, '') <> '';

-- 誤って空行にも日付を入れた場合の修正:
-- update public.trn_dmm_items
-- set safe_generated_at = null
-- where coalesce(auto_summary, '') = '';
