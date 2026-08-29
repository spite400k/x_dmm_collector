-- FANZA Portal BEAF / AIDMA A/B テスト用カラム
-- Supabase SQL Editor 等で dmm_ai_review_summaries に適用

alter table public.dmm_ai_review_summaries
  add column if not exists portal_copy_beaf text,
  add column if not exists portal_copy_aidma text,
  add column if not exists portal_copy text,
  add column if not exists copy_framework text;

comment on column public.dmm_ai_review_summaries.portal_copy_beaf is
  'FANZA Portal 掲載用 BEAF 法コピー（Benefit→Evidence→Advantage→Feature）';

comment on column public.dmm_ai_review_summaries.portal_copy_aidma is
  'FANZA Portal 掲載用 AIDMA 法コピー（Attention→Interest→Desire→Memory→Action）';

comment on column public.dmm_ai_review_summaries.portal_copy is
  'A/B 割当後に Portal へ掲載するアクティブコピー';

comment on column public.dmm_ai_review_summaries.copy_framework is
  'アクティブコピーのフレームワーク: beaf または aidma';

create index if not exists dmm_ai_review_summaries_copy_framework_idx
  on public.dmm_ai_review_summaries (copy_framework);
