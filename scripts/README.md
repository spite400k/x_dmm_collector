# scripts 配下スクリプト

DMM データの収集・加工・手動メンテ用バッチ群です。

- **実行定義の正本**: ルートの [`tasks.yaml`](../tasks.yaml)（`run.py` / bat / CI が参照）
- **一覧・run.py / bat の詳細**: ルートの [`SCRIPTS.md`](../SCRIPTS.md)

## ディレクトリ構成

```
scripts/
  collect/    … DMM API から取得して DB 登録（定期）
  process/    … 取得済みデータの AI 加工・ランキング生成（定期 / 手動）
  manual/     … 手動実行・メンテ用
  _bootstrap.py … プロジェクトルートを sys.path に追加（各スクリプトは同等処理を内蔵）
```

## 共通事項

- **実行場所**: プロジェクトルート（`x_dmm_collector/`）から実行する
- **直接実行**: 各 `.py` は起動時にルートを `sys.path` に追加するため、`python scripts/...` で動く
- **一括実行**: `python run.py --list` / `python run.py --phase collect` など（詳細は `SCRIPTS.md`）
- **ログ**: タスク実行時は `logs/task_run_*.log`、スクリプト単体実行時は各ファイル内 `setup_logger` のファイル名

### 主な環境変数

| 変数 | 用途 |
|------|------|
| `DMM_API_ID`, `DMM_AFFILIATE_ID` | DMM Affiliate API |
| `SUPABASE_URL`, `SUPABASE_KEY` | 通常 DB |
| `OPENAI_API_KEY` | AI レビュー・テキスト生成 |
| `MESUGAKI_DB_PASSWORD` 等 | メスガキ用 DB（`supabase_client_mesugaki.py`） |
| `ACTRESS_ENRICH_BATCH_SIZE` | 女優 enrich の1回あたり件数（省略時 1000） |

---

## collect/ — 収集フェーズ（定期）

| スクリプト | 説明 | 実行例 |
|-----------|------|--------|
| [`collect/default.py`](collect/default.py) | 通常サイト向け作品収集 | `python scripts/collect/default.py` |
| [`collect/mesugaki.py`](collect/mesugaki.py) | メスガキサイト向け作品収集 | `python scripts/collect/mesugaki.py` |
| [`collect/bltl.py`](collect/bltl.py) | BL/TL 向け収集 | `python scripts/collect/bltl.py` |
| [`collect/campaign.py`](collect/campaign.py) | キャンペーン対象の収集 | `python scripts/collect/campaign.py` |

いずれも DMM API で作品を取得し、Supabase に登録する。CLI オプションなし。

---

## process/ — 加工フェーズ

### 定期（`tasks.yaml` の process フェーズ）

| スクリプト | 説明 | 実行例 |
|-----------|------|--------|
| [`process/update_items.py`](process/update_items.py) | 作品の AI テキスト更新 | `python scripts/process/update_items.py` |
| [`process/create_ai_review.py`](process/create_ai_review.py) | 作品 AI レビュー生成 | `python scripts/process/create_ai_review.py` |
| [`process/create_weekly_rankings.py`](process/create_weekly_rankings.py) | 週次ランキング生成 | `python scripts/process/create_weekly_rankings.py` |
| [`process/create_weekly_rankings_mesugaki.py`](process/create_weekly_rankings_mesugaki.py) | メスガキ週次ランキング | `python scripts/process/create_weekly_rankings_mesugaki.py` |

### 手動（`tasks.yaml` の manual フェーズに分類）

| スクリプト | 説明 | 実行例 |
|-----------|------|--------|
| [`process/update_mesugaki.py`](process/update_mesugaki.py) | メスガキ DB の AI 更新 | `python scripts/process/update_mesugaki.py` |
| [`process/update_actress.py`](process/update_actress.py) | 女優プロフィールをスクレイピングで更新 | `python scripts/process/update_actress.py` |
| [`process/enrich_actress.py`](process/enrich_actress.py) | DMM API / osusume から女優情報を enrich | `python scripts/process/enrich_actress.py` |
| [`process/create_actress_review.py`](process/create_actress_review.py) | 女優 AI レビュー（summary / career / appeal）生成 | 下記参照 |
| [`process/create_ai_review_mesugaki.py`](process/create_ai_review_mesugaki.py) | メスガキ向け AI レビュー | 下記参照 |

#### create_actress_review.py

`mst_actress` の `ai_summary` / `ai_career` / `ai_appeal` を OpenAI で生成する。

```bash
# 未生成の女優のみ（ai_summary IS NULL）
python scripts/process/create_actress_review.py

# 名前で再生成（既存を上書き）
python scripts/process/create_actress_review.py --name "つばさ舞"

# actress_id で再生成（複数可）
python scripts/process/create_actress_review.py --actress-id 12345
python scripts/process/create_actress_review.py --actress-id 123 --actress-id 456
```

`--actress-id` と `--name` は同時指定不可。要 `OPENAI_API_KEY`。

#### create_ai_review_mesugaki.py

メスガキ用 Supabase に対して AI レビューを生成する。

```bash
# 通常（AI レビュー + あらすじ等）
python scripts/process/create_ai_review_mesugaki.py

# 生レビュー（dmm_raw_reviews）の保存のみ
python scripts/process/create_ai_review_mesugaki.py --raw-only
```

要 `MESUGAKI_DB_PASSWORD`。AI 生成時は `OPENAI_API_KEY` も必要。

---

## manual/ — 手動メンテ

| スクリプト | 説明 | 実行例 |
|-----------|------|--------|
| [`manual/check_campaign.py`](manual/check_campaign.py) | キャンペーン対象の確認・更新 | `python scripts/manual/check_campaign.py` |
| [`manual/create_master.py`](manual/create_master.py) | DMM floorList 等からマスタ同期 | `python scripts/manual/create_master.py` |
| [`manual/individual_search.py`](manual/individual_search.py) | キーワード指定の個別作品取得 | `python scripts/manual/individual_search.py` |
| [`manual/supabase2storj.py`](manual/supabase2storj.py) | Supabase Storage → Storj へ画像移行 | `python scripts/manual/supabase2storj.py` |

`individual_search.py` はスクリプ内の `targets` / キーワードを編集してから実行する想定。

---

## 旧 main_*.py との対応

リポジトリ整理前のエントリポイント名との対応は [`SCRIPTS.md` の「旧 main_*.py との対応」](../SCRIPTS.md#旧-main_py-との対応) を参照。
