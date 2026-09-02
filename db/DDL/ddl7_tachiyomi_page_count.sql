-- 立ち読み画像の取得枚数（フォールバック後の再埋め判定に使用）
-- 適用先:
--   通常   … DB_*
--   メスガキ … MESUGAKI_DB_*
-- （旧 BL/TL 用 DB2_* はサービス停止済み。データは Supabase 上に残存）

alter table public.trn_dmm_items
  add column if not exists tachiyomi_page_count integer null;

comment on column public.trn_dmm_items.tachiyomi_page_count is
  '立ち読み画像の S3 登録枚数。NULL=対象外または未移行、0=URLあり未取得（後埋め対象）、>=1=取得済み';

create index if not exists trn_dmm_items_tachiyomi_page_count_idx
  on public.trn_dmm_items (tachiyomi_page_count)
  where tachiyomi_url is not null;
