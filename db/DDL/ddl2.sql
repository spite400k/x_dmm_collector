create table public.trn_dmm_items (
  id uuid primary key default gen_random_uuid(),
  title text,
  image_urls text[],           -- サンプル画像（複数）
  affiliate_url text,          -- アフィリエイトURL
  site text,                 -- 例: "FANZA"
  service text,                -- 例: "digital"
  floor text,                  -- 例: "doujin"
  item_id text,                -- DMMの商品ID（重複防止用）
  fetched_at timestamp with time zone default now()
);
