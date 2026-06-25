-- 女優週次ランキング（ページ総評 + 順位明細）
-- create_weekly_rankings_actress.py が書き込む

create table if not exists public.dmm_actress_weekly_ranking_pages (
  id uuid not null default gen_random_uuid(),
  slug text not null,
  year integer not null,
  week integer not null,
  summary text null,
  created_at timestamp with time zone not null default now(),
  constraint dmm_actress_weekly_ranking_pages_pkey primary key (id),
  constraint dmm_actress_weekly_ranking_pages_slug_key unique (slug)
) tablespace pg_default;

create table if not exists public.dmm_actress_weekly_rankings (
  id uuid not null default gen_random_uuid(),
  slug text not null,
  year integer not null,
  week integer not null,
  rank integer not null,
  actress_id integer not null,
  name text null,
  ranking_score numeric null,
  work_count integer null,
  total_review_count integer null,
  avg_rating numeric null,
  favorite_count integer null,
  works_count integer null,
  snapshot_date date null,
  created_at timestamp with time zone not null default now(),
  constraint dmm_actress_weekly_rankings_pkey primary key (id),
  constraint dmm_actress_weekly_rankings_slug_rank_key unique (slug, rank),
  constraint dmm_actress_weekly_rankings_slug_actress_key unique (slug, actress_id)
) tablespace pg_default;

create index if not exists dmm_actress_weekly_rankings_slug_idx
  on public.dmm_actress_weekly_rankings (slug);

create index if not exists dmm_actress_weekly_rankings_year_week_idx
  on public.dmm_actress_weekly_rankings (year, week);

alter table public.dmm_actress_weekly_ranking_pages enable row level security;
alter table public.dmm_actress_weekly_rankings enable row level security;

drop policy if exists "Allow anon select on dmm_actress_weekly_ranking_pages"
  on public.dmm_actress_weekly_ranking_pages;
create policy "Allow anon select on dmm_actress_weekly_ranking_pages"
  on public.dmm_actress_weekly_ranking_pages for select
  to anon, authenticated
  using (true);

drop policy if exists "Allow anon insert on dmm_actress_weekly_ranking_pages"
  on public.dmm_actress_weekly_ranking_pages;
create policy "Allow anon insert on dmm_actress_weekly_ranking_pages"
  on public.dmm_actress_weekly_ranking_pages for insert
  to anon, authenticated
  with check (true);

drop policy if exists "Allow anon select on dmm_actress_weekly_rankings"
  on public.dmm_actress_weekly_rankings;
create policy "Allow anon select on dmm_actress_weekly_rankings"
  on public.dmm_actress_weekly_rankings for select
  to anon, authenticated
  using (true);

drop policy if exists "Allow anon insert on dmm_actress_weekly_rankings"
  on public.dmm_actress_weekly_rankings;
create policy "Allow anon insert on dmm_actress_weekly_rankings"
  on public.dmm_actress_weekly_rankings for insert
  to anon, authenticated
  with check (true);
