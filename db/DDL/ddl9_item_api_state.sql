-- DMM ItemList の連続失敗による更新休止
-- trn_dmm_items には列を足さず、content_id 単位の別テーブルに持つ
-- 適用先: 通常 DB（DB_*）とメスガキ DB（MESUGAKI_DB_*）の両方
--
-- 例:
--   .venv\Scripts\python.exe scripts/manual/run_sql.py db/DDL/ddl9_item_api_state.sql
--   .venv\Scripts\python.exe scripts/manual/run_sql.py db/DDL/ddl9_item_api_state.sql --prefix MESUGAKI_DB

create table if not exists public.trn_dmm_item_api_state (
  content_id text not null,
  miss_count integer not null default 0,
  last_ok_at timestamp with time zone null,
  skip_until timestamp with time zone null,
  updated_at timestamp with time zone not null default now(),
  constraint trn_dmm_item_api_state_pkey primary key (content_id)
) tablespace pg_default;

comment on table public.trn_dmm_item_api_state is
  'DMM ItemList の連続失敗カウンタ。3回連続で skip_until を 30 日先にする';

comment on column public.trn_dmm_item_api_state.miss_count is
  '連続で ItemList が空／失敗した回数。成功時は 0 に戻す';

comment on column public.trn_dmm_item_api_state.last_ok_at is
  '最後に ItemList が 1 件以上返った日時';

comment on column public.trn_dmm_item_api_state.skip_until is
  'この日時まで update_items / update_mesugaki の対象外。NULL は休止なし';

create index if not exists trn_dmm_item_api_state_skip_until_idx
  on public.trn_dmm_item_api_state (skip_until);
