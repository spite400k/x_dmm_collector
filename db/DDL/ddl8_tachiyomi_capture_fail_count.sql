-- 立ち読みキャプチャ連続失敗回数（閾値到達で後埋め対象外）
-- 適用先: DB_* / MESUGAKI_DB_*
-- （旧 BL/TL 用 DB2_* はサービス停止済み）
-- ddl7_tachiyomi_page_count.sql のあとに適用すること

alter table public.trn_dmm_items
  add column if not exists tachiyomi_capture_fail_count integer null default 0;

comment on column public.trn_dmm_items.tachiyomi_capture_fail_count is
  '立ち読みキャプチャの連続失敗回数。NULL/0=未失敗、>=3=後埋め対象外';

create index if not exists trn_dmm_items_tachiyomi_capture_fail_count_idx
  on public.trn_dmm_items (tachiyomi_capture_fail_count)
  where tachiyomi_url is not null
    and coalesce(tachiyomi_page_count, 0) = 0;
