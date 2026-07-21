# scripts 詳細仕様

各スクリプトが **どのテーブルから読み、どのテーブルを更新するか** を記載します。  
一覧・実行方法は [`README.md`](README.md) を参照。

凡例:

- **READ**: SELECT 相当
- **WRITE**: INSERT / UPDATE / UPSERT
- **Storage**: Supabase Storage または S3/Storj（DB テーブル以外）

---

## DB 接続先

| 接続 | クライアント | 環境変数 |
|------|-------------|----------|
| 通常 | `db.supabase_client.supabase` | `SUPABASE_URL`, `SUPABASE_KEY` |
| BL/TL | `db.supabase_client.supabase2` | `SUPABASE_URL2`, `SUPABASE_KEY2` |
| メスガキ収集 | `db.supabase_client.supabase3` | `SUPABASE_URL3`, `SUPABASE_KEY3` |
| メスガキ加工 | `db.supabase_client_mesugaki.supabase` | `MESUGAKI_SUPABASE_URL`, `MESUGAKI_SUPABASE_SERVICE_ROLE_KEY` 等 |
| 通常 Postgres | `psycopg2`（`db.postgres_connect`） | `DB_URL`（GHA 推奨: Session pooler）または `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_PORT` |
| メスガキ Postgres | `psycopg2`（`db.postgres_connect`） | `MESUGAKI_DB_URL`（GHA 推奨）または `MESUGAKI_DB_*` |

> **GHA 注意**: `db.*.supabase.co` 直結は IPv6 専用。Actions では Session pooler URI を `DB_URL` / `MESUGAKI_DB_URL` に設定する（`SCRIPTS.md` 参照）。

---

## collect/

### `collect/default.py`

| 種別 | 対象 |
|------|------|
| **READ** | `trn_dmm_items` — `content_id` 重複チェック |
| **WRITE** | `trn_dmm_items` — 新規 INSERT（未登録 `content_id` のみ） |
| **Storage** | S3 — 立ち読み画像アップロード |
| **外部 API** | DMM Affiliate API `ItemList`、OpenAI（`generate_content`）、DMM 商品ページ（Selenium） |

**処理概要**: 複数 sort で DMM 商品を取得し、未登録作品を `trn_dmm_items` に登録。立ち読み画像・AI 生成文（`auto_comment`, `auto_summary`, `auto_point`）を付与。

**主な INSERT カラム**: `content_id`, `title`, `item_url`, `service`, `floor`, 画像 URL, 価格, ジャンル, 出演者, `auto_*`, `raw_json` 等

---

### `collect/bltl.py`

| 種別 | 対象 |
|------|------|
| **READ** | `trn_dmm_items`（`supabase2`）— 重複チェック |
| **WRITE** | `trn_dmm_items`（`supabase2`）— INSERT |
| **Storage** | S3 |
| **外部 API** | DMM `ItemList`、OpenAI、Selenium |

**処理概要**: BL/TL 向けフロアの作品を `supabase2` 環境の `trn_dmm_items` に登録。`default.py` と同型。

---

### `collect/mesugaki.py`

| 種別 | 対象 |
|------|------|
| **READ** | `trn_dmm_items`（`supabase3`）— 重複チェック |
| **WRITE** | `trn_dmm_items`（`supabase3`）— INSERT |
| **Storage** | S3（bucket3） |
| **外部 API** | DMM `ItemList`（`keyword=メスガキ`）、OpenAI、Selenium |

**処理概要**: メスガキキーワードで絞った作品を `supabase3` に登録。

---

### `collect/campaign.py`

| 種別 | 対象 |
|------|------|
| **READ** | `trn_campaigns` — `feature_url` 既存有無 |
| **WRITE** | `trn_campaigns` — 存在時 UPDATE / 未存在時 INSERT |
| **外部 API** | DMM/FANZA HTML スクレイピング、DMM CDS lite API |

**処理概要**: 各種キャンペーンページから情報を収集し、`feature_url` をキーに `trn_campaigns` を同期。

**更新カラム**: `title`, `description`, `feature_url`, `picture_url`, `type`, `service`, `floor`, `priority`, `is_active`, `start_at`, `end_at`, `updated_at`

---

## process/ — 定期

### `process/update_items.py`

| 種別 | 対象 |
|------|------|
| **READ** | `trn_dmm_items` — 全件 `content_id`, `auto_summary`, `auto_point` |
| **WRITE** | `trn_dmm_items` — UPDATE |
| **WRITE（定義のみ・未使用）** | `mst_actress`, `mst_genre`, `mst_genre_sort`, `mst_director` — upsert 関数はコメントアウト |
| **外部 API** | DMM `ItemList`（cid 指定）、OpenAI（Safe 化要約） |

**処理概要**: 登録済み全作品を DMM API で再取得し、レビュー・価格・出演者等を更新。`auto_summary` / `auto_point` を OpenAI で Safe 化して上書き。

**主な UPDATE カラム**: `review_count`, `review_average`, `price`, `list_price`, `auto_summary`, `auto_point`, `campaign`, `actress_ids`, `actress`, `director_*`, `genre_*`, `delivery`, `sample_images`, `raw_json`, `updated_at`

---

### `process/create_ai_review.py`

| 種別 | 対象 |
|------|------|
| **READ** | `trn_dmm_items` — 直近 31 日・対象 service/floor の `content_id`, `item_url`, `service`, `floor` |
| **READ** | `dmm_raw_reviews` — 既存 `review_id`（差分判定） |
| **READ** | `dmm_ai_review_summaries` — 既存 `summary_text`（あらすじ再利用） |
| **WRITE** | `dmm_raw_reviews` — UPSERT（`content_id`, `review_id`） |
| **WRITE** | `dmm_ai_review_summaries` — UPSERT（`content_id`） |
| **WRITE** | `trn_dmm_score_history` — UPSERT（`content_id`, `snapshot_date`） |
| **外部 API** | OpenAI、DMM 商品ページ（レビュー・あらすじ、Selenium） |

**処理概要**: 対象作品のレビューを取得 → raw 保存 → AI 5 軸分析 → サマリー保存 → 日次スコア保存。

**`dmm_ai_review_summaries` 更新カラム**: `review_digest`, `content_score`, `emotion_score`, `attraction_score`, `genre_axis1_score`, `genre_axis2_score`, `reader_types`, `warning_points`, `review_count`, `avg_rating`, `summary_text`, `ai_model`, `prompt_version`, `updated_at`

**`trn_dmm_score_history` 更新カラム**: `final_score`, `review_count`, `avg_rating`, `snapshot_date`

---

### `process/create_weekly_rankings.py`

| 種別 | 対象 |
|------|------|
| **READ** | `trn_dmm_items` + `trn_dmm_score_history` — JOIN（直近 31 日 release、最新 snapshot の TOP20） |
| **READ** | `dmm_weekly_rankings` — 前週順位（順位変動計算） |
| **WRITE** | `dmm_weekly_ranking_pages` — INSERT（`slug` 衝突時 DO NOTHING） |
| **WRITE** | `dmm_weekly_rankings` — INSERT（週次明細） |
| **外部 API** | OpenAI（週次総評テキスト） |

**処理概要**: カテゴリ別 TOP20 を算出し、前週比較付きでランキング表に保存。OpenAI 生成の総評を `dmm_weekly_ranking_pages` に保存。

---

### `process/create_weekly_rankings_mesugaki.py`

| 種別 | 対象 |
|------|------|
| **READ/WRITE** | 上記と同型（接続先がメスガキ Postgres） |
| **外部 API** | OpenAI |

**処理概要**: メスガキ DB 向け週次ランキング。対象 service/floor はメスガキ用に限定。

---

## process/ — 手動

### `process/update_mesugaki.py`

| 種別 | 対象 |
|------|------|
| **READ** | `trn_dmm_items`（メスガキ DB）— `content_id`, `auto_summary`, `auto_point` |
| **WRITE** | `trn_dmm_items` — UPDATE |
| **WRITE（定義のみ・未使用）** | `mst_actress`, `mst_genre`, `mst_genre_sort`, `mst_director` |
| **外部 API** | DMM `ItemList`, `ActressSearch`（OpenAI Safe 化はコメントアウト） |

**処理概要**: `update_items.py` のメスガキ DB 版。DMM API 再同期で作品メタデータを更新。

---

### `process/update_actress.py`

| 種別 | 対象 |
|------|------|
| **READ** | `mst_actress` — 更新対象（`actress_id`, `name`） |
| **WRITE** | `mst_actress` — UPDATE（プロフィール項目） |
| **外部 API** | DMM `ActressSearch`、osusume プロフィールページ（スクレイピング） |

**処理概要**: 女優一覧を走査し、osusume 等から取得したプロフィールを `mst_actress` に反映。`enrich_actress.py` と役割が一部重複するため、運用方針に応じて使い分け。

---

### `process/enrich_actress.py`

| 種別 | 対象 |
|------|------|
| **READ** | `mst_actress` — `updated_at` が古い順（`fetch_actresses_to_enrich`） |
| **WRITE** | `mst_actress` — UPDATE（enrich 結果）または `updated_at` のみ（スキップ時） |
| **Storage** | S3 — 女優画像 |
| **外部 API** | DMM `ActressSearch` / `ItemList`、osusume スクレイピング、Wikidata、Wikipedia、minnano-av |

**処理概要**: 複数ソースで女優プロフィールを補完し `mst_actress` を更新。

**更新可能フィールド**（`db/mst_actress_repository.py` の `UPDATABLE_FIELDS`）:  
`name`, `name_kana`, `name_en`, `image_url`, `bust`, `cup`, `waist`, `hip`, `height`, `birthday`, `blood_type`, `hobby`, `prefectures`, `x_account`, `profile`, `career_text`, `fanza_activity`, `awards`, `favorite_count`, `debut_date`, `works_count`, `alias`

**環境変数**: `ACTRESS_ENRICH_BATCH_SIZE`（省略時 1000）

---

### `process/create_actress_review.py`

| 種別 | 対象 |
|------|------|
| **READ** | `mst_actress` — 全カラム（対象抽出） |
| **WRITE** | `mst_actress` — UPDATE |
| **外部 API** | OpenAI |

**対象抽出条件**:

| モード | 条件 |
|--------|------|
| 通常 | `ai_summary IS NULL` |
| `--actress-id` | 指定 ID（既存レビュー上書き） |
| `--name` | 名前一致（既存レビュー上書き） |

**UPDATE カラム**: `ai_summary`, `ai_career`, `ai_appeal`, `ai_generated_at`

---

### `process/create_ai_review_mesugaki.py`

| 種別 | 対象 |
|------|------|
| **READ** | `trn_dmm_items`, `dmm_raw_reviews`, `dmm_ai_review_summaries`（メスガキ DB） |
| **WRITE** | `dmm_raw_reviews` — UPSERT（常時） |
| **WRITE** | `dmm_ai_review_summaries`, `trn_dmm_score_history` — UPSERT（`--raw-only` 時はスキップ） |
| **外部 API** | OpenAI、DMM ページ（Selenium） |

**処理概要**: `create_ai_review.py` のメスガキ DB 版。`--raw-only` 指定時は生レビュー保存のみ。

---

## manual/

### `manual/create_master.py`

| 種別 | 対象 |
|------|------|
| **WRITE** | `mst_site` — UPSERT |
| **WRITE** | `mst_service` — UPSERT |
| **WRITE** | `mst_floor` — UPSERT |
| **WRITE（関数あり・main 未使用）** | `mst_genre` — `sync_genre_master` はコメントアウト |
| **外部 API** | DMM `floorList`, `FloorList`, `GenreSearch` |

**処理概要**: DMM マスタ API からサイト・サービス・フロアを同期。

---

### `manual/check_campaign.py`

| 種別 | 対象 |
|------|------|
| **READ** | `trn_dmm_items` — 更新候補の取得 |
| **WRITE** | **実行経路上はなし**（`trn_dmm_items` UPDATE およびマスタ upsert はコメントアウト） |
| **外部 API** | DMM `ItemList`, `ActressSearch` |

**処理概要**: キャンペーン情報の有無を DMM API で確認しログ出力する検証用スクリプト。DB 反映は行わない。

---

### `manual/individual_search.py`

| 種別 | 対象 |
|------|------|
| **READ/WRITE** | なし（`insert_dmm_item` 呼び出しはコメントアウト） |
| **外部 API** | DMM `ItemList`（キーワード検索） |

**処理概要**: スクリプト内 `targets` / キーワードで DMM 検索し、結果をログ出力。DB 登録はしない。

---

### `manual/supabase2storj.py`

| 種別 | 対象 |
|------|------|
| **READ** | Supabase Storage（`SUPABASE_BUCKET`、既定 `dmm-images2`）— オブジェクト一覧・ダウンロード |
| **WRITE** | Storj S3 互換 bucket — アップロード |
| **DB テーブル** | なし |

**処理概要**: Supabase Storage から Storj へ未転送オブジェクトのみ差分コピー。

---

## テーブル × スクリプト 早見表

| テーブル | 主に触るスクリプト |
|----------|-------------------|
| `trn_dmm_items` | `collect/default`, `bltl`, `mesugaki`（INSERT） / `update_items`, `update_mesugaki`（UPDATE） / `create_ai_review*`（READ） / `check_campaign`（READ のみ） |
| `trn_campaigns` | `collect/campaign` |
| `dmm_raw_reviews` | `create_ai_review`, `create_ai_review_mesugaki` |
| `dmm_ai_review_summaries` | `create_ai_review`, `create_ai_review_mesugaki` |
| `trn_dmm_score_history` | `create_ai_review`, `create_ai_review_mesugaki`（WRITE） / `create_weekly_rankings*`（READ） |
| `dmm_weekly_rankings` | `create_weekly_rankings*` |
| `dmm_weekly_ranking_pages` | `create_weekly_rankings*` |
| `mst_actress` | `enrich_actress`, `update_actress`, `create_actress_review` |
| `mst_site` / `mst_service` / `mst_floor` / `mst_genre` | `manual/create_master` |

---

## データフロー（概要）

```
[DMM API / スクレイピング]
        │
        ▼
  collect/*  ──► trn_dmm_items, trn_campaigns
        │
        ▼
  process/update_items  ──► trn_dmm_items（メタデータ更新）
        │
        ▼
  process/create_ai_review*  ──► dmm_raw_reviews
                              ──► dmm_ai_review_summaries
                              ──► trn_dmm_score_history
        │
        ▼
  process/create_weekly_rankings*  ──► dmm_weekly_rankings
                                   ──► dmm_weekly_ranking_pages

  process/enrich_actress  ──► mst_actress（プロフィール）
  process/create_actress_review  ──► mst_actress（AI レビュー文）
```
