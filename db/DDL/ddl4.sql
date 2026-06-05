create table if not exists public.trn_campaigns (
  id uuid not null default gen_random_uuid (),
  title text not null,
  description text null,
  feature_url text not null,
  picture_url text null,
  type text not null default 'all'::text,
  service text not null default 'all'::text,
  floor text not null default 'all'::text,
  priority integer not null default 100,
  is_active boolean not null default true,
  start_at timestamp with time zone not null default now(),
  end_at timestamp with time zone not null default now(),
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),
  constraint trn_campaigns_pkey primary key (id)
) TABLESPACE pg_default;

-- 重複判定用の正規化 URL（lurl がある場合はデコードした実 URL）
-- af_id は .env の DMM_AFFILIATE_ID に合わせて置き換えてください
-- feature_url の重複を削除（同一キャンペーンの直 URL / アフィリエイト URL を統合）
delete from public.trn_campaigns
where id in (
  select id
  from (
    select
      id,
      row_number() over (
        partition by
          case
            when feature_url ~ 'lurl='
              then replace(
                replace(
                  replace(
                    replace(
                      (regexp_match(feature_url, 'lurl=([^&]+)'))[1],
                      '%3A', ':'
                    ),
                    '%2F', '/'
                  ),
                  '%3F', '?'
                ),
                '%26', '&'
              )
            else feature_url
          end
        order by updated_at desc, created_at desc
      ) as rn
    from public.trn_campaigns
  ) ranked
  where rn > 1
);

create unique index if not exists trn_campaigns_feature_url_key
  on public.trn_campaigns (feature_url);

-- RLS（trn_dmm_items と同様に service_role / anon からの書き込みを許可）
alter table public.trn_campaigns enable row level security;

drop policy if exists "Allow anon insert on trn_campaigns" on public.trn_campaigns;
create policy "Allow anon insert on trn_campaigns"
  on public.trn_campaigns for insert
  to anon, authenticated
  with check (true);

drop policy if exists "Allow anon update on trn_campaigns" on public.trn_campaigns;
create policy "Allow anon update on trn_campaigns"
  on public.trn_campaigns for update
  to anon, authenticated
  using (true)
  with check (true);

drop policy if exists "Allow anon select on trn_campaigns" on public.trn_campaigns;
create policy "Allow anon select on trn_campaigns"
  on public.trn_campaigns for select
  to anon, authenticated
  using (true);
