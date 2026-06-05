# スクリプト一覧

`tasks.yaml` が実行定義の正本です。`run.py` / bat / GitHub Actions はすべてこれを参照します。

## ディレクトリ構成（案 B）

```
scripts/
  collect/    … DMM から取得して DB 登録
  process/    … 取得済みデータの加工・生成
  manual/     … 手動実行・メンテ用
```

## 命名規則（案 A）

| 接頭辞 | 意味 | 例 |
|--------|------|-----|
| `scripts/collect/` | 収集フェーズ | `default.py`, `mesugaki.py` |
| `scripts/process/` | 加工フェーズ | `update_items.py`, `create_ai_review.py` |
| `scripts/manual/` | 手動実行 | `check_campaign.py` |

旧 `main_*.py` との対応:

| 旧ファイル | 新パス |
|-----------|--------|
| `main_collect.py` | `scripts/collect/default.py` |
| `main_collect_mesugaki.py` | `scripts/collect/mesugaki.py` |
| `main_bltl.py` | `scripts/collect/bltl.py` |
| `main_campaign.py` | `scripts/collect/campaign.py` |
| `main_update_items.py` | `scripts/process/update_items.py` |
| `main_create_ai_review.py` | `scripts/process/create_ai_review.py` |
| `main_create_weekly_rankings.py` | `scripts/process/create_weekly_rankings.py` |
| `main_create_weekly_rankings_mesugaki.py` | `scripts/process/create_weekly_rankings_mesugaki.py` |
| `main_update_mesugaki.py` | `scripts/process/update_mesugaki.py` |
| `main_update_actress.py` | `scripts/process/update_actress.py` |
| `main_actress.py` | `scripts/process/enrich_actress.py` |
| `main_create_actress_review.py` | `scripts/process/create_actress_review.py` |
| `main_create_ai_review_mesugaki.py` | `scripts/process/create_ai_review_mesugaki.py` |
| `main_check_campiagn.py` | `scripts/manual/check_campaign.py` |
| `main_create_master.py` | `scripts/manual/create_master.py` |
| `main_individual_search.py` | `scripts/manual/individual_search.py` |
| `main_supabase2storj.py` | `scripts/manual/supabase2storj.py` |

---

## フェーズ別一覧

### 収集フェーズ（定期）

| スクリプト | 説明 | ログ |
|-----------|------|------|
| `scripts/collect/default.py` | 通常収集 | `logs/task_run.log` |
| `scripts/collect/mesugaki.py` | メスガキ収集 | `logs/task_run_mesugaki.log` |
| `scripts/collect/bltl.py` | BL/TL 収集 | `logs/task_run_bltl.log` |
| `scripts/collect/campaign.py` | キャンペーン収集 | `logs/task_run_campaign.log` |

### 加工フェーズ（定期）

| スクリプト | 説明 | ログ |
|-----------|------|------|
| `scripts/process/update_items.py` | AI テキスト更新 | `logs/task_run_update_items.log` |
| `scripts/process/create_ai_review.py` | AI レビュー生成 | `logs/task_run_create_ai_review.log` |
| `scripts/process/create_weekly_rankings.py` | 週次ランキング | `logs/task_run_create_weekly_rankings.log` |
| `scripts/process/create_weekly_rankings_mesugaki.py` | メスガキ週次ランキング | `logs/task_run_create_weekly_rankings_mesugaki.log` |

### 手動実行

| スクリプト | 説明 | ログ |
|-----------|------|------|
| `scripts/process/update_mesugaki.py` | メスガキ AI 更新 | `logs/task_run_update_mesugaki.log` |
| `scripts/process/update_actress.py` | 女優プロフィール更新 | `logs/task_run_update_actress.log` |
| `scripts/process/enrich_actress.py` | 女優情報 enrich（DMM API） | `logs/task_run_enrich_actress.log` |
| `scripts/process/create_actress_review.py` | 女優 AI レビュー生成 | `logs/task_run_create_actress_review.log` |
| `scripts/process/create_ai_review_mesugaki.py` | メスガキ AI レビュー生成 | `logs/task_run_create_ai_review_mesugaki.log` |
| `scripts/manual/check_campaign.py` | キャンペーンチェック | `logs/task_run_check_campaign.log` |
| `scripts/manual/create_master.py` | マスタ作成 | `logs/task_run_create_master.log` |
| `scripts/manual/individual_search.py` | 個別検索 | `logs/task_run_individual_search.log` |
| `scripts/manual/supabase2storj.py` | Supabase → Storj 移行 | `logs/task_run_supabase2storj.log` |

---

## 実行方法

### run.py（案 C）

```bash
# 一覧表示
python run.py --list

# フェーズ単位
python run.py --phase collect
python run.py --phase process
python run.py --phase manual
python run.py --phase all          # collect + process

# 単一スクリプト
python run.py --script scripts/collect/default.py

# エラーがあっても続行（定期バッチ向け）
python run.py --phase all --continue-on-error
```

### bat ファイル（案 D）

| bat | 内容 |
|-----|------|
| `run_collect.bat` | 収集フェーズ 4 本 |
| `run_process.bat` | 加工フェーズ 4 本 |
| `run_all.bat` | 収集 → 加工 |
| `run_x_dmm_collector.bat` | `run_all.bat` のエイリアス（後方互換） |
| `run_x_dmm_collector_process.bat` | `run_process.bat` のエイリアス |
| `run_x_dmm_collector_btlt.bat` | BL/TL 収集のみ |

---

## 直接実行

プロジェクトルートで:

```bash
python scripts/collect/default.py
```

`scripts/` 配下の各ファイルは起動時にプロジェクトルートを `sys.path` に追加するため、ルートから実行してください。
