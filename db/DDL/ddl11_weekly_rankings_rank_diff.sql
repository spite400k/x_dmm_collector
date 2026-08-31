-- 週次ランキング明細に初登場・順位変動を保存
-- create_weekly_rankings*.py が書き込む
-- Supabase SQL Editor などで各環境に適用する

alter table public.dmm_weekly_rankings
  add column if not exists is_new boolean not null default false,
  add column if not exists rank_diff integer null;

comment on column public.dmm_weekly_rankings.is_new is
  '前週ランキングに未登場の作品なら true';
comment on column public.dmm_weekly_rankings.rank_diff is
  '前週順位 - 今週順位（正=順位上昇）。初登場は NULL';

alter table public.dmm_actress_weekly_rankings
  add column if not exists is_new boolean not null default false,
  add column if not exists rank_diff integer null;

comment on column public.dmm_actress_weekly_rankings.is_new is
  '前週ランキングに未登場の女優なら true';
comment on column public.dmm_actress_weekly_rankings.rank_diff is
  '前週順位 - 今週順位（正=順位上昇）。初登場は NULL';
