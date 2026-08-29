# 実装プロンプト: FANZA Portal BEAF/AIDMA コピー生成 + A/B テスト

他リポジトリ向けに、そのまま AI エージェントまたは開発者へ渡して実行できる実装指示書です。

---

## ミッション

作品レビュー／紹介文を生成する AI パイプラインに、**BEAF法** と **AIDMA法** の Portal 向けコピーを **1回の API 呼び出しで両方** 生成させ、DB に保存し、**content_id ベースの安定 50/50 割当** で A/B テストできるようにする。

---

## 背景

| フレームワーク | 順序 | 用途 |
|---------------|------|------|
| **BEAF** | Benefit → Evidence → Advantage → Feature | 比較検討・説明向き |
| **AIDMA** | Attention → Interest → Desire → Memory → Action | 発見・クリック・購入後押し向き |

FANZA Portal（紹介・ランキングサイト）では **`portal_copy`** を表示する。`review_digest` は分析・スコア用として残す。

---

## 実装チェックリスト

- [ ] 1. BEAF/AIDMA 用モジュールを追加（A/B 割当・DB 付与）
- [ ] 2. AI 生成プロンプト（system / user）に `portal_copy_beaf` / `portal_copy_aidma` を追加
- [ ] 3. 作品メタ（タイトル・ジャンル・価格・出演等）を user プロンプトへ渡す
- [ ] 4. DB に4カラム追加 + `prompt_version` 更新
- [ ] 5. 保存処理で両バリアント保存 + アクティブコピー割当
- [ ] 6. Portal フロントは `portal_copy` を表示
- [ ] 7. ユニットテスト追加

---

## 1. 定数

```python
PROMPT_VERSION = "v4_beaf_aidma_ab"
```

---

## 2. System プロンプト（追記・統合用）

既存のレビュー生成 system プロンプトに、以下を **そのまま追記** する。
採点ロジックがある場合は `review_digest` と Portal コピーを分離すること。

```
あなたはエンタメ作品のレビュー編集者兼スコアアナリストです。

【採点フィールド】（既存がある場合は維持）
content_score, emotion_score, attraction_score, genre_axis1_score, genre_axis2_score
・各項目100点満点の整数（0〜100）のみ出力
・あらすじとレビューの内容のみを根拠に、客観的かつ厳しめに採点

【テキストフィールド】review_digest, portal_copy_beaf, portal_copy_aidma, reader_types, warning_points
review_digest: 350〜450文字。作品の魅力を感情豊かに要約する（分析・スコア用。Portal A/B とは別）。
  体言止め・評論調・論文調は禁止。「あなた」と語りかけてよい（「読者」は使わない）。
portal_copy_beaf / portal_copy_aidma: FANZA Portal 向け紹介文（各280〜380文字）。下記 BEAF/AIDMA ルールを適用。
reader_types: この作品に合う読者像を2〜3件、具体的な短文で列挙する。
warning_points: 購入前に知っておくべき注意点を1〜3件、具体的な短文で列挙する。

【FANZA Portal 向けコピー（A/B テスト用・両方必須）】
あらすじ・レビュー・作品情報のみを根拠に、次の2形式を**両方**生成する。

■ portal_copy_beaf（BEAF法: Benefit→Evidence→Advantage→Feature）
・280〜380文字
・便益（誰向け・何が得か）→ 根拠（レビュー傾向・具体魅力）→ 差別化 → スペック（価格・出演・ジャンル）
・比較検討向きの説明的トーン

■ portal_copy_aidma（AIDMA法: Attention→Interest→Desire→Memory→Action）
・280〜380文字
・冒頭フック → 興味 → 欲求 → 覚えやすい一言 → FANZA公式で確認を促すCTA
・ランキング・発見・クリック向きトーン

【Portal コピー共通禁止】
・過度に露骨な描写、創作・推測、レビューにない事実の追加
・「本作」「この作品」などのテンプレ導入、SEOキーワード羅列

【共通禁止】
・レビュー原文の出力・引用
・JSONオブジェクト以外の出力
・登場人物はすべて18歳以上の成人として扱う
```

---

## 3. User プロンプト（テンプレート）

プレースホルダ `{...}` を実行時に埋める。`response_format: json_object` を使う。

```
以下の作品情報を分析し、JSON を出力してください。

【各フィールドの内容】
- review_digest: 作品の魅力を要約（テキストフィールドのルールを適用）
- portal_copy_beaf: BEAF法の Portal 紹介文（280〜380文字）
- portal_copy_aidma: AIDMA法の Portal 紹介文（280〜380文字）
- content_score: 内容力（採点ルールを適用）
- emotion_score: 感情インパクト（採点ルールを適用）
- attraction_score: 魅力（採点ルールを適用）
- genre_axis1_score: {axis1}（{score_type}型のジャンル特性を反映して採点）
- genre_axis2_score: {axis2}（{score_type}型のジャンル特性を反映して採点）
- reader_types: この作品に合う読者像を2〜3件
- warning_points: 購入前の注意点を1〜3件

【作品メタ（Portal コピー用）】
- タイトル: {title}
- 出演/サークル: {actress_or_circle}
- ジャンル: {genres}
- カテゴリ: {category}
- 価格: {price}
- シリーズ: {series}
- メーカー: {maker}
- ランキング: {ranking_label}

【分析コンテキスト】
ジャンル: {genre_type}（評価タイプ: {score_type}）
レビュー平均: {review_avg} / 件数: {review_count}

【あらすじ】
{html_summary}

【レビュー】
{review_text_block}

【出力スキーマ】
{
  "review_digest": "...",
  "portal_copy_beaf": "...",
  "portal_copy_aidma": "...",
  "content_score": 0,
  "emotion_score": 0,
  "attraction_score": 0,
  "genre_axis1_score": 0,
  "genre_axis2_score": 0,
  "reader_types": ["...", "..."],
  "warning_points": ["..."]
}
```

**API 設定の目安**
- `response_format: {"type": "json_object"}`
- `max_completion_tokens`: 1200 → **2000** に増やす（2バリアント分）

---

## 4. A/B 割当ロジック（必須）

```python
import hashlib
from typing import Any, Mapping

PROMPT_VERSION = "v4_beaf_aidma_ab"


def assign_copy_framework(content_id: str) -> str:
    """content_id から安定した 50/50 割当（beaf / aidma）。"""
    digest = hashlib.md5(content_id.encode("utf-8")).hexdigest()
    return "beaf" if int(digest, 16) % 2 == 0 else "aidma"


def pick_portal_copy(insight: Mapping[str, Any], content_id: str) -> tuple[str, str]:
    """(copy_framework, portal_copy) を返す。"""
    beaf = (insight.get("portal_copy_beaf") or "").strip()
    aidma = (insight.get("portal_copy_aidma") or "").strip()
    framework = assign_copy_framework(content_id)

    if not beaf and not aidma:
        return framework, (insight.get("review_digest") or "").strip()

    if framework == "beaf":
        return ("beaf", beaf) if beaf else ("aidma", aidma)
    return ("aidma", aidma) if aidma else ("beaf", beaf)


def enrich_ai_summary_for_ab(
    summary: dict[str, Any],
    insight: Mapping[str, Any],
    content_id: str,
) -> dict[str, Any]:
    framework, portal_copy = pick_portal_copy(insight, content_id)
    summary["portal_copy_beaf"] = insight.get("portal_copy_beaf")
    summary["portal_copy_aidma"] = insight.get("portal_copy_aidma")
    summary["copy_framework"] = framework
    summary["portal_copy"] = portal_copy or None
    summary["prompt_version"] = PROMPT_VERSION
    return summary
```

**保存直前の呼び出し例**

```python
summary = {
    "content_id": content_id,
    "review_digest": insight.get("review_digest"),
    # ... 既存スコアフィールド ...
}
enrich_ai_summary_for_ab(summary, insight, content_id)
# → upsert
```

---

## 5. DB マイグレーション

テーブル名 `{review_summaries_table}` を各リポジトリの実名に置換（例: `dmm_ai_review_summaries`）。

```sql
alter table public.{review_summaries_table}
  add column if not exists portal_copy_beaf text,
  add column if not exists portal_copy_aidma text,
  add column if not exists portal_copy text,
  add column if not exists copy_framework text;

comment on column public.{review_summaries_table}.portal_copy_beaf is
  'Portal BEAF 法コピー（Benefit→Evidence→Advantage→Feature）';
comment on column public.{review_summaries_table}.portal_copy_aidma is
  'Portal AIDMA 法コピー（Attention→Interest→Desire→Memory→Action）';
comment on column public.{review_summaries_table}.portal_copy is
  'A/B 割当後の掲載用アクティブコピー';
comment on column public.{review_summaries_table}.copy_framework is
  'beaf または aidma';

create index if not exists {review_summaries_table}_copy_framework_idx
  on public.{review_summaries_table} (copy_framework);
```

---

## 6. 作品メタの渡し方

AI 生成関数に `product_context: dict | None` を追加し、DB 行から組み立てる。

```python
def build_product_context_from_row(row, service_code, floor_code):
    # actress / maker / title / genres / price / series から
    # actress_or_circle, category=f"{service_code}/{floor_code}" 等を構築
    ...
```

**SELECT に追加するカラム例**

```
title, genres, price, actress, series, maker
```

---

## 7. Portal フロントエンド

| 用途 | 参照カラム |
|------|-----------|
| 掲載テキスト | **`portal_copy`** |
| A/B 分析 | `copy_framework`, `portal_copy_beaf`, `portal_copy_aidma` |
| 分析・スコア | `review_digest`（従来どおり） |

---

## 8. A/B 分析 SQL

```sql
SELECT copy_framework, COUNT(*) AS n
FROM {review_summaries_table}
WHERE prompt_version = 'v4_beaf_aidma_ab'
GROUP BY copy_framework;
```

GA4 等と `content_id` + `copy_framework` を突合して CTR / CVR を比較する。

---

## 9. テスト要件

最低限以下を追加する。

1. `assign_copy_framework("同じid")` が常に同じ結果
2. `pick_portal_copy` が割当側を優先、空なら反対側にフォールバック
3. `enrich_ai_summary_for_ab` が4フィールド + `prompt_version` を付与
4. AI 呼び出しモックで user プロンプトに `portal_copy_beaf` / `portal_copy_aidma` が含まれる

---

## 10. エージェント向け実行指示（コピペ用）

```
以下を実装してください。

1. 作品 AI レビュー生成パイプラインに BEAF/AIDMA Portal コピーを追加する
2. 1回の OpenAI 呼び出しで portal_copy_beaf と portal_copy_aidma の両方を JSON 出力する
3. system プロンプトに prompts/fanza-portal-beaf-aidma-ab-test.md の「2. System プロンプト」を統合する
4. user プロンプトに作品メタ（タイトル・ジャンル・価格・出演・カテゴリ）を渡す
5. copy_framework_ab 相当のモジュールを追加し、content_id MD5 で beaf/aidma を 50/50 安定割当する
6. DB に portal_copy_beaf, portal_copy_aidma, portal_copy, copy_framework を追加する
7. 保存時 enrich_ai_summary_for_ab() を呼び、prompt_version = v4_beaf_aidma_ab にする
8. max_completion_tokens を 2000 に増やす
9. ユニットテストを追加する
10. Portal 表示は portal_copy を使う（review_digest は分析用のまま）

リポジトリの既存命名・ディレクトリ構成に合わせてパスは調整すること。
採点ロジックが無い場合は review_digest + portal_copy_beaf + portal_copy_aidma + reader_types + warning_points のみでよい。
```

---

## 参考実装（x_dmm_collector）

| ファイル | 役割 |
|---------|------|
| `utils/copy_framework_ab.py` | A/B 割当・DB 付与 |
| `utils/content_generator_review.py` | プロンプト拡張 |
| `scripts/process/create_ai_review.py` | 保存パイプライン |
| `db/DDL/ddl10_portal_copy_ab.sql` | マイグレーション |
| `tests/test_copy_framework_ab.py` | ユニットテスト |
