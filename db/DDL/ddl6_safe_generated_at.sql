-- Safe 化完了時刻（update_items.py が AI Safe 化スキップ判定に使用）
-- Supabase SQL Editor などで各環境の trn_dmm_items に適用する

alter table public.trn_dmm_items
  add column if not exists safe_generated_at timestamp with time zone null;

comment on column public.trn_dmm_items.safe_generated_at is
  'auto_summary / auto_point の Safe 化（OpenAI）完了日時。NULL のとき未実施';

create index if not exists trn_dmm_items_safe_generated_at_idx
  on public.trn_dmm_items (safe_generated_at);

-- 任意: 既存であらすじがある行を Safe 済み扱いにする（必要な環境だけ実行）
-- update public.trn_dmm_items
-- set safe_generated_at = coalesce(updated_at, now())
-- where safe_generated_at is null
--   and coalesce(auto_summary, '') <> '';
