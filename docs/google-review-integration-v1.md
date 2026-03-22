# Google口コミ連携設計書 v1
## subjective-trust-platform / Phase 1周辺開発

© 2026 Kazuaki Watanabe / 渡邉和明 — Licensed under CC BY-NC 4.0

---

## 1. 設計方針

### 1.1 既存パイプラインとの関係

Google口コミは接客タグ・アンケートと以下の点で異なる。

| 項目 | 接客タグ・アンケート | Google口コミ |
|---|---|---|
| 書き手 | スタッフ / 来店直後の顧客 | 不特定（来店後任意のタイミング） |
| 書き方 | 短文・構造化・特定体験 | 長文・複数次元混在・感情表現強 |
| 視点 | 単一接点 | 複数来店体験の総括になりやすい |
| 競合比較 | なし | 含む場合がある |
| PII（個人情報） | スタッフメモに含む可能性あり | 含む可能性あり（氏名言及など） |

この差異を踏まえ、以下の設計判断とする。

- **専用バッチ**：既存の日次AI解釈バッチとは独立した別バッチとして実装する
- **専用プロンプト**：外部レビュー専用プロンプトを新規作成する
- **Claude API経路**：AWS Bedrock経由（boto3）で統一する

### 1.2 Phase 1でのスコープ

| 対象 | 内容 |
|---|---|
| 対象店舗 | 1店舗（API検証・精度確認後に全店展開） |
| 取得頻度 | 日次（前日分の新規レビューを取得） |
| 対象レビュー | Googleビジネスプロフィールの新規レビュー |
| AI解釈 | trust_dimension分類・感情分析・Trait/State/Meta手がかり抽出 |
| 除外 | リアルタイム取得・返信機能・レビュー削除検知 |

---

## 2. アーキテクチャ

### 2.1 全体フロー

```
Google Business Profile API
  │  日次取得（前日分の新規レビュー）
  ▼
review_fetcher.py
  │  正規化・PII マスキング・重複チェック
  ▼
review_events テーブル（raw 保存）
  │
  ▼
review_interpreter.py
  │  AWS Bedrock（Claude）で解釈
  │  専用プロンプト適用
  ▼
trust_events テーブル（source_type='review'）
  │
  ▼
既存スコア算出バッチ（変更なし）
```

### 2.2 バッチ実行スケジュール

```
毎日 03:00  Google口コミ取得バッチ（review_fetcher）
  ↓ 完了後
毎日 03:30  Google口コミ解釈バッチ（review_interpreter）
  ↓ 完了後
毎日 04:00  既存スコア算出バッチ（変更なし）
  ↓ 完了後
毎日 08:30  既存監視バッチ（変更なし）
```

取得と解釈を分離する理由：APIエラー時にリトライが取得だけで済む。解釈バッチは取得済みデータを再利用できる。

---

## 3. データ設計

### 3.1 review_external テーブルの確認

設計書v1 §4.3で定義済みのテーブルをそのまま使用する。

```sql
-- 既存テーブル（変更なし）
-- review_external
--   review_id, store_id, platform, rating, review_text,
--   reviewer_name, review_date, fetched_at
```

追加が必要なカラムを確認する。

```sql
-- マイグレーション: add_review_external_columns
ALTER TABLE review_external
  ADD COLUMN IF NOT EXISTS google_review_id VARCHAR(255) UNIQUE,
    -- Google側のレビューID（重複取得防止）
  ADD COLUMN IF NOT EXISTS processed_flag BOOLEAN NOT NULL DEFAULT false,
    -- 解釈バッチ処理済みフラグ
  ADD COLUMN IF NOT EXISTS processed_at   TIMESTAMPTZ;
    -- 解釈完了日時

CREATE INDEX IF NOT EXISTS idx_review_external_processed
  ON review_external(processed_flag, store_id);
```

### 3.2 TrustEventへの接続

既存の多態的参照をそのまま使用する。

```
trust_events.source_type = 'review'
trust_events.source_id   = review_external.review_id
```

---

## 4. Google Business Profile API 設計

### 4.1 APIクォータと取得設計

Google Business Profile API（旧 My Business API）のクォータ制限を踏まえた設計。

| 項目 | 制限値 | 設計上の対応 |
|---|---|---|
| 読み取りリクエスト | 5,000回/日 | 日次1回の差分取得のみ |
| レビュー一覧取得 | ページネーション対応 | pageSize=50で取得 |
| 1店舗あたりのリクエスト数 | 数回/日 | 問題なし |

Phase 1（1店舗）では制限に当たらない。全直営店展開前に実測値を計測する。

### 4.2 認証フロー

```python
# OAuth 2.0 サービスアカウント認証
# Google Cloud プロジェクトのサービスアカウントを使用

from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/business.manage"]

credentials = service_account.Credentials.from_service_account_file(
    settings.GOOGLE_SERVICE_ACCOUNT_KEY_PATH,
    scopes=SCOPES
)
service = build("mybusiness", "v4", credentials=credentials)
```

サービスアカウントキーは Secret Manager で管理する。ローカル開発時は環境変数 `GOOGLE_SERVICE_ACCOUNT_KEY_PATH` で参照する。

### 4.3 レビュー取得クエリ

```python
# 前日分の新規レビューを取得（差分取得）
def fetch_new_reviews(location_name: str, since: datetime) -> list[dict]:
    """
    location_name: "accounts/{accountId}/locations/{locationId}"
    since: 前回取得日時（batch_job_logsから取得）
    """
    reviews = []
    page_token = None

    while True:
        request = service.accounts().locations().reviews().list(
            parent=location_name,
            pageSize=50,
            pageToken=page_token
        )
        response = request.execute()

        for review in response.get("reviews", []):
            # updateTime が since より新しいものだけを対象にする
            update_time = datetime.fromisoformat(
                review["updateTime"].replace("Z", "+00:00")
            )
            if update_time > since:
                reviews.append(review)

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return reviews
```

### 4.4 環境変数

```bash
# Secret Manager に追加
GOOGLE_SERVICE_ACCOUNT_KEY_PATH   # サービスアカウントキーのパス
GOOGLE_LOCATION_ID_STORE_A        # 1店舗目のlocationId（Phase 1）
```

---

## 5. PII マスキング設計

### 5.1 マスキング対象

Google口コミには以下が含まれる可能性がある。

| 項目 | 例 | 対応 |
|---|---|---|
| スタッフ氏名 | 「○○さんが対応してくれた」 | マスキング（→「スタッフ」） |
| 顧客自身の氏名 | レビュー本文中の自己言及 | マスキング |
| 電話番号 | 稀だが含む場合あり | マスキング |

既存の接客タグ・アンケート用PIIマスキングモジュールを外部レビュー向けに拡張する。

### 5.2 マスキング実装方針

```python
# 既存モジュールの拡張
# src/python/batch/pii_masker.py に add_review_masking() を追加

import re

STAFF_NAME_PATTERN = re.compile(
    r'([ぁ-ん]{1,4}[さ様さん]{1,3}|[ァ-ン]{2,4}[さ様]{1,2})',
    re.UNICODE
)
PHONE_PATTERN = re.compile(r'0\d{1,4}-\d{1,4}-\d{4}')

def mask_review_text(text: str) -> str:
    text = STAFF_NAME_PATTERN.sub("スタッフ", text)
    text = PHONE_PATTERN.sub("[電話番号]", text)
    return text
```

完全なPIIマスキングはLLMベースの処理（Phase 2以降）で精度向上を図る。Phase 1では正規表現ベースで最低限の処理を行う。

---

## 6. AI解釈プロンプト設計

### 6.1 既存プロンプトとの差異

既存の接客タグ・アンケート用プロンプトは「単一接点の解釈」を前提としている。Google口コミは以下の点で異なる。

- 複数の信頼次元が1テキスト内に混在する
- 「また来たい」「他店と比べて」等の総括表現が多い
- 評価点（星1〜5）と本文の感情が一致しない場合がある（星3でも内容はポジティブ等）
- 競合比較・地域比較が含まれる場合がある

これらを踏まえ、以下の差分を専用プロンプトに反映する。

### 6.2 専用プロンプト（外部レビュー用）

```python
EXTERNAL_REVIEW_PROMPT_TEMPLATE = """
あなたはブランド信頼の分析専門家です。
以下の実店舗に対するGoogle口コミを分析し、指定のJSON形式で出力してください。

## 分析対象レビュー

評価点: {rating}点（5点満点）
投稿日: {review_date}
本文:
{review_text}

## 分析指示

Google口コミは複数の体験をまとめて書かれる場合があります。
本文全体を読み、以下の5つの信頼次元のうち**言及されているすべての次元**を特定し、
それぞれについて感情・重要度・解釈を出力してください。

### 信頼次元の定義
- product  : 商品の品質・価格納得感・期待一致
- service  : 接客の安心感・丁寧さ・不快感の有無
- proposal : 提案の的確さ・自分に合っているか
- operation: 在庫案内・受取・価格表示の正確さ
- story    : ブランドらしさ・世界観の一貫性

### 注意事項
- 評価点（星）と本文の感情が一致しない場合は本文を優先してください
- 競合他社との比較が含まれる場合は、本店舗への評価のみを対象にしてください
- 推測できない次元は出力しないでください

## 出力形式（JSONのみ。前置き・後置き不要）

{{
  "mentions": [
    {{
      "trust_dimension": "service | product | proposal | operation | story",
      "sentiment": "positive | negative | neutral",
      "severity": 1 | 2 | 3,
      "theme_tags": ["タグ1", "タグ2"],
      "summary": "この次元に関する1文の要約",
      "interpretation": "なぜそう感じたと推定されるかの1文解釈",
      "confidence": 0.0〜1.0
    }}
  ],
  "subjective_hints": {{
    "trait_signal": "長期的な価値観・選好の手がかり（なければnull）",
    "state_signal": "来店時の状態・目的の手がかり（なければnull）",
    "meta_signal": "過去体験への言及・繰り返しパターン（なければnull）"
  }},
  "overall_sentiment": "positive | negative | neutral | mixed",
  "review_type": "single_visit | multi_visit | comparison | unknown",
  "contains_competitor_mention": true | false
}}
"""
```

### 6.3 既存プロンプトとの主な差分

| 項目 | 既存プロンプト | 外部レビュー専用 |
|---|---|---|
| 次元の出力 | 単一次元 | 言及されたすべての次元（`mentions`配列） |
| 評価点の扱い | なし | 星との乖離を明示的に考慮 |
| 競合比較 | 想定なし | `contains_competitor_mention`で識別 |
| 来店回数 | 単一来店前提 | `review_type`で複数来店・比較を識別 |
| overall_sentiment | なし | レビュー全体の総合感情を追加 |

### 6.4 TrustEvent生成ルール

`mentions`配列の各要素を1件のTrustEventとして生成する。1件のGoogle口コミから複数のTrustEventが生成される。

```python
def mentions_to_trust_events(
    review: ReviewExternal,
    interpretation_result: dict
) -> list[TrustEvent]:
    events = []
    for mention in interpretation_result["mentions"]:
        events.append(TrustEvent(
            store_id       = review.store_id,
            source_type    = "review",
            source_id      = review.review_id,
            trust_dimension = mention["trust_dimension"],
            sentiment       = mention["sentiment"],
            severity        = mention["severity"],
            theme_tags      = mention["theme_tags"],
            generated_summary = mention["summary"],
            interpretation  = mention["interpretation"],
            trait_signal    = interpretation_result["subjective_hints"]["trait_signal"],
            state_signal    = interpretation_result["subjective_hints"]["state_signal"],
            meta_signal     = interpretation_result["subjective_hints"]["meta_signal"],
            confidence      = mention["confidence"],
            needs_review    = mention["confidence"] < 0.6,
            detected_at     = review.review_date,
        ))
    return events
```

---

## 7. バッチ実装設計

### 7.1 ファイル構成

```
src/python/batch/
├── （既存バッチ）
├── review_fetcher.py      ← 新規：Google口コミ取得
└── review_interpreter.py  ← 新規：Google口コミAI解釈
```

### 7.2 review_fetcher.py の主要処理

```python
async def run_review_fetch_batch(store_id: UUID, location_name: str):
    log_id = record_job_start(conn, "review_fetch_batch")
    try:
        # 前回取得日時をbatch_job_logsから取得
        last_run = get_last_successful_run("review_fetch_batch")
        since = last_run or datetime.now(UTC) - timedelta(days=1)

        # Google APIからレビュー取得
        raw_reviews = fetch_new_reviews(location_name, since)

        count = 0
        for raw in raw_reviews:
            # 重複チェック（google_review_idで一意性を保証）
            if await review_exists(raw["reviewId"]):
                continue

            # PIIマスキング
            masked_text = mask_review_text(raw.get("comment", ""))

            # review_externalに保存
            await save_review(ReviewExternal(
                store_id        = store_id,
                platform        = "google",
                rating          = parse_rating(raw["starRating"]),
                review_text     = masked_text,
                reviewer_name   = "（匿名）",  # 氏名は保存しない
                review_date     = parse_datetime(raw["createTime"]),
                google_review_id = raw["reviewId"],
                processed_flag  = False,
            ))
            count += 1

        record_job_end(conn, log_id, count)
        run_critical_checks("review_fetch_batch")

    except Exception as e:
        record_job_end(conn, log_id, 0, error=str(e))
        raise
```

### 7.3 review_interpreter.py の主要処理

```python
async def run_review_interpret_batch(store_id: UUID):
    log_id = record_job_start(conn, "review_interpret_batch")
    try:
        # 未処理レビューを取得
        reviews = await get_unprocessed_reviews(store_id)
        count = 0

        for review in reviews:
            prompt = EXTERNAL_REVIEW_PROMPT_TEMPLATE.format(
                rating      = review.rating,
                review_date = review.review_date.strftime("%Y-%m-%d"),
                review_text = review.review_text,
            )

            # AWS Bedrock経由でClaude APIを呼び出す
            result = await call_bedrock_claude(prompt)

            # TrustEventを生成
            events = mentions_to_trust_events(review, result)
            await save_trust_events(events)

            # 処理済みフラグを更新
            await mark_review_processed(review.review_id)
            count += 1

            # スロットリング（既存バッチに準拠）
            await asyncio.sleep(0.5)

        record_job_end(conn, log_id, count)
        run_critical_checks("review_interpret_batch")

    except Exception as e:
        record_job_end(conn, log_id, 0, error=str(e))
        raise
```

### 7.4 AWS Bedrock呼び出しの実装

既存の抽象クライアント（Anthropic/Bedrock/Mock切替）を使用する。

```python
# 既存の ai_client.py の Bedrock クライアントをそのまま使用
# PROMPT_VERSION管理も既存の仕組みに乗る

from src.python.ai.client import get_ai_client

client = get_ai_client()  # 環境変数 AI_CLIENT_TYPE=bedrock で Bedrock が選択される
response = await client.interpret(prompt)
```

---

## 8. エラーハンドリング設計

### 8.1 エラー種別と対応

| エラー種別 | 発生箇所 | 対応 |
|---|---|---|
| Google API認証エラー | review_fetcher | 即時失敗・Slackアラート |
| Google APIクォータ超過 | review_fetcher | 翌日リトライ（差分取得なので重複なし） |
| レビュー本文が空 | review_fetcher | スキップ（review保存・processed_flag=true） |
| Bedrock APIエラー | review_interpreter | 最大3回リトライ後にskip・needs_review=true |
| JSON解析エラー（AI出力） | review_interpreter | needs_review=true・手動レビューキューへ |
| DBデッドロック | 両バッチ | 最大2回リトライ |

### 8.2 リトライ設計

```python
# AWS Bedrock のスロットリングに対するリトライ
import tenacity

@tenacity.retry(
    stop=tenacity.stop_after_attempt(3),
    wait=tenacity.wait_exponential(multiplier=1, min=2, max=10),
    retry=tenacity.retry_if_exception_type(
        (ClientError,)  # boto3のThrottlingException等
    )
)
async def call_bedrock_claude(prompt: str) -> dict:
    ...
```

---

## 9. 精度検証設計

### 9.1 Phase 1での検証方法

1店舗での導入後、以下を週次で確認する。

**定量検証**（既存の監視で対応）

- `source_type='review'`のTrustEvent件数（監視⑤と連動）
- `needs_review=true`の割合（監視③と連動）

**定性検証（週次サンプリング）**

```sql
-- 週次で20件をサンプリングしてAI解釈の精度を確認
SELECT
    re.rating,
    re.review_text,
    te.trust_dimension,
    te.sentiment,
    te.interpretation,
    te.confidence
FROM review_external re
JOIN trust_events te
    ON  te.source_type = 'review'
    AND te.source_id   = re.review_id
WHERE re.store_id = :store_id
  AND re.fetched_at >= CURRENT_DATE - INTERVAL '7 days'
ORDER BY RANDOM()
LIMIT 20;
```

確認観点：

- trust_dimensionの分類は適切か（目標：正答率85%以上）
- 複数次元が混在するレビューで`mentions`が正しく複数生成されているか
- `review_type`の分類（single_visit / multi_visit / comparison）は正確か
- overall_sentimentと評価点（星）の乖離が適切に処理されているか

---

## 10. 実装ファイル一覧

```
src/python/
├── batch/
│   ├── review_fetcher.py          ← 新規
│   └── review_interpreter.py      ← 新規
├── ai/
│   └── prompts/
│       ├── interpretation.py      ← 既存（変更なし）
│       └── review_interpretation.py ← 新規（専用プロンプト）
├── db/
│   └── migrations/versions/
│       └── xxxx_add_review_external_columns.py ← 新規
└── utils/
    └── pii_masker.py              ← 既存を拡張（mask_review_text追加）

tests/python/
├── batch/
│   ├── test_review_fetcher.py     ← 新規
│   └── test_review_interpreter.py ← 新規
└── ai/
    └── test_review_prompt.py      ← 新規（プロンプト出力の単体テスト）
```

---

## 11. 1店舗テスト計画

### Step 1：API接続確認（ローカル）

```bash
# サービスアカウントキーを取得してローカルで疎通確認
export GOOGLE_SERVICE_ACCOUNT_KEY_PATH=/path/to/key.json
export GOOGLE_LOCATION_ID_STORE_A=accounts/xxx/locations/yyy

python scripts/test_google_api.py
# → レビュー一覧が取得できることを確認
# → クォータ消費量を記録する
```

### Step 2：取得バッチの単体実行

```bash
docker compose exec worker python -m batch.review_fetcher --store-id <STORE_A_ID>
# → review_external テーブルにレコードが挿入されることを確認
# → google_review_id の重複が防止されていることを確認（2回実行して件数が変わらないこと）
```

### Step 3：解釈バッチの単体実行

```bash
docker compose exec worker python -m batch.review_interpreter --store-id <STORE_A_ID>
# → trust_events テーブルに source_type='review' のレコードが生成されることを確認
# → 1件のレビューから複数の TrustEvent が生成されるケースを確認
```

### Step 4：精度確認（20件サンプリング）

上記 §9.1 のサンプリングクエリを実行し、AI解釈の精度を目視確認する。

- 正答率85%未満の場合 → プロンプトを修正して再実行
- needs_review=trueの割合が40%超の場合 → confidence閾値の調整を検討

### Step 5：監視との統合確認

```bash
# 取得・解釈バッチ完了後、監視チェックが正常に動くことを確認
python -m monitoring.checks.critical  # Snapshot更新・重複チェック
python -m monitoring.checks.daily     # source_type='review'のゼロ検知が機能するか
```
