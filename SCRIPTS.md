# x_dmm_collector — プロジェクト定義

DMM Affiliate API から作品・キャンペーン情報を収集し、Supabase に保存したうえで AI テキスト・レビュー・ランキングを生成する Python バッチ群。

**収集フロー**: `collect` は API + DB 登録のみ（Chrome なし）。立ち読み URL は DB に保存し、画像は `backfill_tachiyomi`（推奨 00:30）で後埋めする。

**実行定義の正本**は [`tasks.yaml`](tasks.yaml)。`run.py` / bat / GitHub Actions はすべてこれを参照する。

---

## フォルダ階層

```
x_dmm_collector/
├── run.py                  … tasks.yaml に基づく一括実行エントリ
├── tasks.yaml              … フェーズ・スクリプト・ログの定義
├── requirements.txt
│
├── run_*.bat               … Windows 定期実行用（後述）
│
├── scripts/                … バッチスクリプト本体
│   ├── collect/            … DMM から取得して DB 登録（定期）
│   ├── process/            … 取得済みデータの AI 加工・ランキング（定期 / 手動）
│   ├── manual/             … 手動実行・メンテ用
│   ├── _bootstrap.py       … ルートを sys.path に追加
│   └── README.md           … 各スクリプトの説明・CLI オプション
│
├── dmm/                    … DMM API クライアント・女優情報取得
├── db/                     … Supabase 接続・リポジトリ・DDL
│   └── DDL/                … スキーマ定義 SQL
├── openai_api/             … OpenAI によるテキスト生成
├── utils/                  … ログ・画像・スクレイピング等の共通処理
├── tests/                  … pytest
├── logs/                   … タスク実行ログ（git 管理外）
│
├── .github/workflows/      … CI（GitHub Actions）
└── .vscode/                … エディタ設定
```

### 各ディレクトリの役割

| パス | 役割 |
|------|------|
| `scripts/collect/` | DMM API で作品・キャンペーンを取得し Supabase に登録 |
| `scripts/process/` | AI テキスト更新、レビュー生成、週次ランキングなど |
| `scripts/manual/` | マスタ同期、個別検索、Storage 移行など必要時のみ実行 |
| `dmm/` | DMM Affiliate API、女優 API、キャンペーン API |
| `db/` | Supabase クライアント、各テーブル用リポジトリ、Storage 操作 |
| `openai_api/` | 作品・女優向け AI コンテンツ生成 |
| `utils/` | ロガー、画像処理、DMM レビュースクレイピング等 |
| `logs/` | `run.py` 実行時の `task_run_*.log`（各 bat からも同経路） |

スクリプト個別の説明・実行例・CLI オプションは [`scripts/README.md`](scripts/README.md) を参照。

---

## 実行の流れ

```
tasks.yaml  →  run.py  →  scripts/**/*.py
                ↑
         bat / GitHub Actions
```

| 手段 | 用途 |
|------|------|
| `run.py` | 開発・CI。フェーズ単位または単一スクリプト実行 |
| `run_*.bat` | Windows タスクスケジューラからの定期実行 |
| `.github/workflows/main.yml` | GitHub Actions による collect フェーズの定期実行 |

```bash
# 登録スクリプト一覧
python run.py --list

# フェーズ単位
python run.py --phase collect
python run.py --phase process              # 全系統直列（互換）
python run.py --phase process_main         # 通常系統のみ
python run.py --phase process_actress      # 女優系統のみ
python run.py --phase process_mesugaki     # メスガキ系統のみ
python run.py --phase process_main_weekly  # 通常系統の旧作更新（週次）
python run.py --phase process_mesugaki_weekly  # メスガキ系統の旧作更新（週次）
python run.py --phase manual
python run.py --phase all                  # collect + process

# 単一スクリプト
python run.py --script scripts/collect/default.py

# エラーがあっても続行（定期バッチ向け）
python run.py --phase all --continue-on-error
```

---

## bat ファイル

プロジェクトルートに配置。いずれも `cd` で作業ディレクトリを移動したうえで `run.py` を呼び出す。

| bat | 実行内容 | 呼び出し元 |
|-----|----------|------------|
| [`run_collect.bat`](run_collect.bat) | 収集フェーズ 3 本（API + DB のみ。立ち読みなし） | — |
| [`run_backfill_tachiyomi.bat`](run_backfill_tachiyomi.bat) | 立ち読み後埋め（default / supabase3） | 収集後 |
| [`run_process_main.bat`](run_process_main.bat) | 加工・通常系統 3 本 | 定期（並列推奨） |
| [`run_process_actress.bat`](run_process_actress.bat) | 加工・女優系統 2 本 | 定期（並列推奨） |
| [`run_process_mesugaki.bat`](run_process_mesugaki.bat) | 加工・メスガキ系統 3 本 | 定期（並列推奨） |
| [`run_process_main_weekly.bat`](run_process_main_weekly.bat) | 通常系統の旧作 API 更新 | 週次 |
| [`run_process_mesugaki_weekly.bat`](run_process_mesugaki_weekly.bat) | メスガキ系統の旧作 API 更新 | 週次 |
| [`run_process.bat`](run_process.bat) | 加工フェーズ全本を直列 | 互換用 |
| [`run_all.bat`](run_all.bat) | 収集 → 加工（直列） | — |
| [`run_x_dmm_collector.bat`](run_x_dmm_collector.bat) | `run_all.bat` と同じ | 後方互換エイリアス |
| [`run_x_dmm_collector_process.bat`](run_x_dmm_collector_process.bat) | `run_process.bat` と同じ | 後方互換エイリアス |

### 加工フェーズの並列実行

タスクスケジューラでは **すべて `\fanza\` フォルダ配下** に次を登録する（ルート直下・`\self\` の同名タスクは登録時に削除）。`run_process.bat`（直列）の代わりに加工 3 系統を **1 時間ずらして** 登録する（OpenAI レート制限対策）。ロック・待機・収集後の追加ずらしの詳細は [run.py の相手ジョブ待ち・加工ずらし](#runpy-の相手ジョブ待ち加工ずらし) を参照。

| タスク名 | bat | 開始時刻 |
|----------|-----|----------|
| `\fanza\x-dmm-collector-collect` | `run_collect.bat` | 23:00 |
| `\fanza\x-dmm-collector-backfill-tachiyomi` | `run_backfill_tachiyomi.bat` | 00:30 |
| `\fanza\x-dmm-collector-process-main` | `run_process_main.bat` | 01:00 |
| `\fanza\x-dmm-collector-process-actress` | `run_process_actress.bat` | 02:00 |
| `\fanza\x-dmm-collector-process-mesugaki` | `run_process_mesugaki.bat` | 03:00 |
| `\fanza\x-dmm-collector-process-main-weekly` | `run_process_main_weekly.bat` | 日曜 12:00 |
| `\fanza\x-dmm-collector-process-mesugaki-weekly` | `run_process_mesugaki_weekly.bat` | 日曜 13:00 |

収集・後埋め・加工はいずれも **`\fanza\` 配下** に登録する。

再登録（収集 + 後埋め → `\fanza\`）: `powershell -ExecutionPolicy Bypass -File scripts/manual/register_collect_backfill_tasks.ps1`  
再登録（加工 → `\fanza\`）: `powershell -ExecutionPolicy Bypass -File scripts/manual/register_process_tasks.ps1`

系統ごとに別ロック（`logs/run_process_*.lock`）。`--phase process` / `all` は全系統ロックを取るため分割 bat と同時には動かない。

---

## run.py の相手ジョブ待ち・加工ずらし

収集（Chrome / 立ち読み）と加工が同時に走るとブラウザが衝突するため、`run.py` は **ロック取得の前** に相手ジョブの終了を待つ。加工 3 系統同士は従来どおり並列可。同じ系統の二重起動は待たず **即 exit 2**（従来どおり）。

### ロックファイル

| ファイル | 保持者 |
|----------|--------|
| `logs/run.lock` | 収集フェーズ（`--phase collect`）、`SCRIPT_PIPELINE` 外の単体スクリプト |
| `logs/run_process_main.lock` | `process_main` / `process_main_weekly` |
| `logs/run_process_actress.lock` | `process_actress` |
| `logs/run_process_mesugaki.lock` | `process_mesugaki` / `process_mesugaki_weekly` |

### 誰が誰を待つか

| 起動側 | 待つロック（空くまでポーリング） |
|--------|----------------------------------|
| 加工（`process_*` / `process`） | `run.lock`（収集） |
| 収集（`collect`） | `run_process_main.lock` + `run_process_actress.lock` + `run_process_mesugaki.lock` |
| 立ち読み後埋め（`backfill_tachiyomi`） | `run.lock`（収集）+ 上記 3 つの `run_process_*.lock` |
| 加工系の単体スクリプト（`SCRIPT_PIPELINE` 登録分） | `run.lock` |
| 収集系の単体スクリプト（`default.py` 等） | 上記 3 つの `run_process_*.lock` |
| `--phase all` | 待たない（従来どおり直列） |

待機ログ例（`logs/run.log`）:

```text
相手ジョブの終了を待機中 (600s): run.lock=12345 2026-09-01 23:00:01
```

### 収集待ち後の加工ずらし（OpenAI 間隔）

スケジューラ上 01:00 / 02:00 / 03:00 に起動しても、**収集を待った場合のみ** 追加でスリープする（`run.py` 内）。

| フェーズ | 追加待機 |
|----------|----------|
| `process_main` / `process_main_weekly` | 0 秒 |
| `process_actress` | 1 時間（3600 秒） |
| `process_mesugaki` / `process_mesugaki_weekly` | 2 時間（7200 秒） |

例: 収集が 04:00 まで延びた場合、`process_main` は 04:00 頃開始 → `process_actress` は 05:00 頃 → `process_mesugaki` は 06:00 頃。

### 環境変数

| 変数 | 既定 | 意味 |
|------|------|------|
| `X_DMM_PEER_WAIT_TIMEOUT` | `129600`（36 時間） | 相手ジョブ待ちの上限（秒）。超過で exit 2 |
| `X_DMM_PEER_WAIT_POLL` | `30` | ポーリング間隔（秒） |
| `X_DMM_PROCESS_STAGGER_SECONDS` | （有効） | `0` にすると収集待ち後の 1h / 2h ずらしを無効化 |

緊急時のみ `--no-lock`（相手待ちもスキップ。二重起動の恐れあり）。

### 典型スケジュール（タスクスケジューラ）

| 時刻 | タスク | 内容 |
|------|--------|------|
| 23:00 | 収集（`run_collect.bat`） | 加工 3 系統が動いていれば待ってから開始 |
| 01:00 | `process_main` | 収集が残っていれば待つ。待った後は即本体 |
| 02:00 | `process_actress` | 同上。待った後 +1h |
| 03:00 | `process_mesugaki` | 同上。待った後 +2h |

再登録: `powershell -ExecutionPolicy Bypass -File scripts/manual/register_process_tasks.ps1`

旧の `x-dmm-collector-modify`（`run_process.bat` 直列。`\self\` 等に残っている場合あり）は登録スクリプト実行時に無効化する。

---

#### run_collect.bat

- **コマンド**: `run.py --phase collect --continue-on-error`
- **対象**: `tasks.yaml` の collect フェーズ（通常 / メスガキ / キャンペーン収集）

#### run_process_main.bat / run_process_actress.bat / run_process_mesugaki.bat

- **コマンド**: `run.py --phase process_{main|actress|mesugaki} --continue-on-error`
- **Python**: `venv\Scripts\python.exe`
- **用途**: 日次加工の並列実行（推奨）

#### run_process_main_weekly.bat / run_process_mesugaki_weekly.bat

- **コマンド**: `run.py --phase process_{main|mesugaki}_weekly --continue-on-error`
- **対象**: `update_items` / `update_mesugaki` の `--mode weekly`（全件フル更新: 価格・campaign 等）
- **ロック**: 日次の同系統と共有（同時実行しない）
- **用途**: 週次のカタログ遅延更新

#### run_process.bat

- **コマンド**: `run.py --phase process --continue-on-error`
- **対象**: `tasks.yaml` の process フェーズ全本を直列
- **用途**: 互換・手動での一括実行。定期は上記 3 本を推奨
- **Python**: `venv\Scripts\python.exe` を使用（他 bat はシステム Python）

#### run_all.bat

- **コマンド**: `run.py --phase all --continue-on-error`
- **順序**: collect 完了後に process を実行
- **用途**: 日次のメインバッチ（加工は直列）

#### run_x_dmm_collector.bat / run_x_dmm_collector_process.bat

- それぞれ `run_all.bat` / `run_process.bat` を `call` するだけのラッパー
- 旧タスクスケジューラ設定との互換用

### bat 内の環境設定

各 bat 先頭で以下を定義している（環境に合わせて編集する）。

| 変数 | 例 |
|------|-----|
| `WORK_DIR` | `C:\Users\kazuk\python\x_dmm_collector` |
| `PYTHON_EXE` | システム Python または `venv\Scripts\python.exe` |

`.env` や OS 環境変数（`DMM_API_ID`、`SUPABASE_URL`、`OPENAI_API_KEY`、`OPENAI_MODEL` 等）は bat では設定せず、実行環境側で用意する。

---

## 旧 main_*.py との対応

リポジトリ整理前のエントリポイント名との対応:

| 旧ファイル | 新パス |
|-----------|--------|
| `main_collect.py` | `scripts/collect/default.py` |
| `main_collect_mesugaki.py` | `scripts/collect/mesugaki.py` |
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
