# x_dmm_collector — プロジェクト定義

DMM Affiliate API から作品・キャンペーン情報を収集し、Supabase に保存したうえで AI テキスト・レビュー・ランキングを生成する Python バッチ群。

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
python run.py --phase process
python run.py --phase manual
python run.py --phase all          # collect + process

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
| [`run_collect.bat`](run_collect.bat) | 収集フェーズ 4 本 | — |
| [`run_process.bat`](run_process.bat) | 加工フェーズ全本 | — |
| [`run_all.bat`](run_all.bat) | 収集 → 加工 | — |
| [`run_x_dmm_collector.bat`](run_x_dmm_collector.bat) | `run_all.bat` と同じ | 後方互換エイリアス |
| [`run_x_dmm_collector_process.bat`](run_x_dmm_collector_process.bat) | `run_process.bat` と同じ | 後方互換エイリアス |
| [`run_x_dmm_collector_btlt.bat`](run_x_dmm_collector_btlt.bat) | BL/TL 収集のみ | — |

### 各 bat の詳細

#### run_collect.bat

- **コマンド**: `run.py --phase collect --continue-on-error`
- **対象**: `tasks.yaml` の collect フェーズ（通常 / メスガキ / BL・TL / キャンペーン収集）

#### run_process.bat

- **コマンド**: `run.py --phase process --continue-on-error`
- **対象**: `tasks.yaml` の process フェーズ（AI 更新・レビュー・ランキング等）
- **Python**: `venv\Scripts\python.exe` を使用（他 bat はシステム Python）

#### run_all.bat

- **コマンド**: `run.py --phase all --continue-on-error`
- **順序**: collect 完了後に process を実行
- **用途**: 日次のメインバッチ

#### run_x_dmm_collector.bat / run_x_dmm_collector_process.bat

- それぞれ `run_all.bat` / `run_process.bat` を `call` するだけのラッパー
- 旧タスクスケジューラ設定との互換用

#### run_x_dmm_collector_btlt.bat

- **コマンド**: `run.py --script scripts/collect/bltl.py`
- **用途**: BL/TL 収集だけを単独で回す

### bat 内の環境設定

各 bat 先頭で以下を定義している（環境に合わせて編集する）。

| 変数 | 例 |
|------|-----|
| `WORK_DIR` | `C:\Users\kazuk\python\x_dmm_collector` |
| `PYTHON_EXE` | システム Python または `venv\Scripts\python.exe` |

`.env` や OS 環境変数（`DMM_API_ID`、`SUPABASE_URL`、`OPENAI_API_KEY` 等）は bat では設定せず、実行環境側で用意する。

---

## 旧 main_*.py との対応

リポジトリ整理前のエントリポイント名との対応:

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
