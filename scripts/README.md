# scripts スクリプト一覧

`scripts/` 配下のバッチスクリプト一覧です。  
**テーブルの読み書き・更新カラムなどの詳細仕様**は [`SPEC.md`](SPEC.md) を参照してください。

- **実行定義の正本**: [`tasks.yaml`](../tasks.yaml)
- **run.py / bat の使い方**: [`SCRIPTS.md`](../SCRIPTS.md)

## ディレクトリ構成

| ディレクトリ | 役割 |
|-------------|------|
| [`collect/`](collect/) | DMM から取得して DB 登録（定期） |
| [`process/`](process/) | 取得済みデータの加工・AI 生成（定期 / 手動） |
| [`manual/`](manual/) | 手動実行・メンテ |

## 共通事項

- **実行場所**: プロジェクトルートから `python scripts/...`
- **一括実行**: `python run.py --list` / `python run.py --phase collect|process|manual`
- **ログ**: タスク実行時は `logs/task_run_*.log`（`tasks.yaml` 参照）

---

## collect/（定期）

| スクリプト | 説明 | DB 接続 | 実行 |
|-----------|------|---------|------|
| [`default.py`](collect/default.py) | 通常サイト向け作品収集 | 通常 (`supabase`) | `python scripts/collect/default.py` |
| [`mesugaki.py`](collect/mesugaki.py) | メスガキ向け作品収集 | メスガキ収集用 (`supabase3`) | `python scripts/collect/mesugaki.py` |
| [`bltl.py`](collect/bltl.py) | BL/TL 向け作品収集 | BL/TL 用 (`supabase2`) | `python scripts/collect/bltl.py` |
| [`campaign.py`](collect/campaign.py) | キャンペーン情報収集 | 通常 (`supabase`) | `python scripts/collect/campaign.py` |

---

## process/

### 定期（`tasks.yaml` → process）

| スクリプト | 説明 | DB 接続 | 実行 |
|-----------|------|---------|------|
| [`update_items.py`](process/update_items.py) | 作品情報・AI テキスト更新 | 通常 | `python scripts/process/update_items.py` |
| [`create_ai_review.py`](process/create_ai_review.py) | 作品 AI レビュー生成 | 通常 | `python scripts/process/create_ai_review.py` |
| [`create_weekly_rankings.py`](process/create_weekly_rankings.py) | 週次ランキング生成 | 通常（Postgres 直結） | `python scripts/process/create_weekly_rankings.py` |
| [`create_weekly_rankings_mesugaki.py`](process/create_weekly_rankings_mesugaki.py) | メスガキ週次ランキング | メスガキ（Postgres 直結） | `python scripts/process/create_weekly_rankings_mesugaki.py` |

### 手動（`tasks.yaml` → manual）

| スクリプト | 説明 | DB 接続 | 実行 |
|-----------|------|---------|------|
| [`update_mesugaki.py`](process/update_mesugaki.py) | メスガキ DB の作品情報更新 | メスガキ | `python scripts/process/update_mesugaki.py` |
| [`update_actress.py`](process/update_actress.py) | 女優プロフィール（osusume スクレイピング）更新 | 通常 | `python scripts/process/update_actress.py` |
| [`enrich_actress.py`](process/enrich_actress.py) | 女優情報 enrich（DMM API 等） | 通常 | `python scripts/process/enrich_actress.py` |
| [`create_actress_review.py`](process/create_actress_review.py) | 女優 AI レビュー生成 | 通常 | 下記 |
| [`create_ai_review_mesugaki.py`](process/create_ai_review_mesugaki.py) | メスガキ AI レビュー | メスガキ | 下記 |

#### create_actress_review.py

```bash
python scripts/process/create_actress_review.py                          # 未生成のみ
python scripts/process/create_actress_review.py --name "つばさ舞"          # 名前で再生成
python scripts/process/create_actress_review.py --actress-id 12345         # ID で再生成
```

#### create_ai_review_mesugaki.py

```bash
python scripts/process/create_ai_review_mesugaki.py
python scripts/process/create_ai_review_mesugaki.py --raw-only   # 生レビュー保存のみ
```

---

## manual/（手動）

| スクリプト | 説明 | DB 接続 | 実行 |
|-----------|------|---------|------|
| [`check_campaign.py`](manual/check_campaign.py) | キャンペーン有無の確認（検証用） | 通常 | `python scripts/manual/check_campaign.py` |
| [`create_master.py`](manual/create_master.py) | DMM マスタ同期 | 通常 | `python scripts/manual/create_master.py` |
| [`individual_search.py`](manual/individual_search.py) | キーワード検索の試験実行 | なし | `python scripts/manual/individual_search.py` |
| [`supabase2storj.py`](manual/supabase2storj.py) | Storage → Storj 画像移行 | Storage のみ | `python scripts/manual/supabase2storj.py` |

---

## DB 接続の対応

| 接続名 | 設定 | 主な利用スクリプト |
|--------|------|-------------------|
| 通常 | `SUPABASE_URL`, `SUPABASE_KEY` | `default.py`, `update_items.py`, `create_ai_review.py` 等 |
| BL/TL | `SUPABASE_URL2`, `SUPABASE_KEY2` | `bltl.py` |
| メスガキ収集 | `SUPABASE_URL3`, `SUPABASE_KEY3` | `mesugaki.py` |
| メスガキ加工 | `MESUGAKI_SUPABASE_*` | `update_mesugaki.py`, `create_ai_review_mesugaki.py` 等 |
| Postgres 直結 | `DB_*` / `MESUGAKI_DB_*` | `create_weekly_rankings*.py` |

---

## 旧 main_*.py との対応

[`SCRIPTS.md` の「旧 main_*.py との対応」](../SCRIPTS.md#旧-main_py-との対応) を参照。
