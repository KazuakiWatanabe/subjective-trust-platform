# SubjectiveProfile 設計書 v1
## subjective-trust-platform / Phase 2 準備

© 2026 Kazuaki Watanabe / 渡邉和明 — Licensed under CC BY-NC 4.0

---

## 1. 位置づけと制約

### 1.1 本書の位置づけ

SubjectiveProfile は、顧客ごとの主観的傾向（Trait / State / Meta）を継続的に蓄積・更新し、
接客前のコンテキスト提供や AI 解釈の精度向上に活用するための仕組みである。

設計書 v1（§2.2）で定義した三層モデルの「顧客レベルへの実装」として位置づける。

| 層 | 設計書 v1 での定義 | SubjectiveProfile での実装 |
|---|---|---|
| Trait | 長期的な価値観・選好。来店をまたいで安定 | `trait_summary`：AI が複数来店から抽出した傾向要約 |
| State | 来店時の短期的状態。来店ごとに変わりうる | `latest_state`：直近来店の目的・状態（Visit から取得） |
| Meta | 違和感・修正の履歴。信頼毀損の伏線 | `meta_log`：過去の不満・違和感イベントの履歴 |

### 1.2 Phase 1 との関係

Phase 1 では TrustEvent の `trait_signal` / `state_signal` / `meta_signal` フィールドに
AI が抽出した手がかりを文字列として保存している。

SubjectiveProfile はこの手がかりを**顧客単位に集約・構造化**したものである。

### 1.3 設計書 v1 との差分

設計書 v1 §4.3 では Customer テーブルに `trait_summary TEXT` カラムを追加する設計としている。
本書ではこれを **独立テーブル（subjective_profiles）** に格上げして設計する。

理由は以下の3点。

1. `trait_summary` 単体では Meta 履歴・State・is_reliable などの管理に限界がある
2. Customer テーブルへの直接追加はマイグレーションコストが高く、将来の拡張が困難になる
3. Phase 3 の接客前コンテキスト API（§5.3）に対して独立テーブルの方が参照設計が明快になる

Customer テーブルの `trait_summary` カラムは **追加しない**。
代わりに `subjective_profiles.profile_id` を Customer から参照する設計とする。

```sql
-- Customer テーブルへの追加カラム（設計書 v1 §4.3 の変更点）
ALTER TABLE customers
  ADD COLUMN IF NOT EXISTS subjective_profile_id UUID
    REFERENCES subjective_profiles(profile_id);
  -- trait_summary は subjective_profiles テーブルで管理するため Customer には追加しない
```

```
Phase 1（手がかりの蓄積）
  TrustEvent.trait_signal = "品質重視の傾向"
  TrustEvent.state_signal = "ギフト選びで慎重"
  TrustEvent.meta_signal  = "前回の欠品対応に不満が残っている"

         ↓ Phase 2 で集約・構造化

SubjectiveProfile（顧客単位の主観モデル）
  trait_summary = "品質重視・押し売りを嫌う傾向。高単価商品への関心が高い"
  latest_state  = {purpose: "gift", budget_sensitivity: "low"}
  meta_log      = [{type: "out_of_stock", date: ..., resolved: false}, ...]
```

### 1.4 設計上の制約

- **Phase 1 では構築しない**：シグナルの蓄積量が不足しているため
- **AI 推定結果はすべて仮説**：Profile の内容は確定事実ではなく推定であることを UI 上で明示する（設計書 v1 §8.3 の方針を踏襲）
- **個人情報保護法への対応**：`trait_summary` 等は「個人関連情報」に該当しうるため、
  構築・利用前に法務確認を必須とする（**設計書 v1 §8.1 に明示されている必須要件**）
- **スタッフ向けに限定**：Profile の内容は接客前の参考情報としてのみ使用し、
  人事評価・個人査定の材料にしない（設計書 v1 §8.2 の方針を踏襲）
- **スタッフ別集計は行わない**：Phase 1 では禁止。Phase 2 以降も本人フィードバック用途に限定する

---

## 2. データモデル設計

### 2.1 エンティティ構成

```
Customer (1) ──< (1) SubjectiveProfile
SubjectiveProfile (1) ──< (N) MetaLogEntry
SubjectiveProfile (1) ──< (N) TraitSignalHistory
```

### 2.2 subjective_profiles テーブル

```sql
CREATE TABLE subjective_profiles (
    profile_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id       UUID NOT NULL REFERENCES customers(customer_id) UNIQUE,

    -- Trait層
    trait_summary     TEXT,
        -- AI が複数来店から抽出した長期的傾向の要約（自然言語）
        -- 例: "品質重視・押し売りを嫌う傾向。ギフト購入が多い"
    trait_tags        VARCHAR(50)[],
        -- 構造化されたTraitタグ（フィルタ・検索用）
        -- 例: ["品質重視", "押し売り嫌い", "ギフト購入多"]
    trait_confidence  NUMERIC(3,2),
        -- Trait推定の確信度（0.0〜1.0）
    trait_updated_at  TIMESTAMPTZ,

    -- State層（直近来店の状態）
    latest_state      JSONB,
        -- 直近来店時のState情報（Visit.visit_purposeと連動）
        -- 例: {"purpose": "gift", "urgency": "low", "budget_sensitivity": "high"}
    latest_visit_id   UUID REFERENCES visits(visit_id),
    state_updated_at  TIMESTAMPTZ,

    -- Meta層（サマリー）
    meta_risk_level   VARCHAR(10) DEFAULT 'none',
        -- none / low / medium / high
        -- 未解決の信頼毀損が蓄積している度合い
    unresolved_meta_count INTEGER DEFAULT 0,
        -- 未解決のネガティブMetaイベント件数
    last_negative_meta_at TIMESTAMPTZ,
        -- 直近のネガティブMetaイベント発生日時

    -- 管理
    is_reliable       BOOLEAN DEFAULT false,
        -- 算出に使ったTrustEventが閾値（10件）以上でtrue
    source_event_count INTEGER DEFAULT 0,
        -- Profile算出に使ったTrustEvent件数
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_subjective_profiles_customer
    ON subjective_profiles(customer_id);
CREATE INDEX idx_subjective_profiles_meta_risk
    ON subjective_profiles(meta_risk_level)
    WHERE meta_risk_level != 'none';
```

### 2.3 meta_log_entries テーブル

Meta 層の詳細履歴を保持する。`subjective_profiles.meta_risk_level` はここから集計する。

```sql
CREATE TABLE meta_log_entries (
    entry_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id        UUID NOT NULL REFERENCES subjective_profiles(profile_id),
    trust_event_id    UUID REFERENCES trust_events(trust_event_id),

    meta_type         VARCHAR(50) NOT NULL,
        -- out_of_stock_dissatisfaction / pushy_sales_experience /
        -- explanation_insufficient / staff_mismatch / price_dissatisfaction / other
    description       TEXT NOT NULL,
        -- TrustEvent.meta_signal の内容
    sentiment         VARCHAR(10) NOT NULL DEFAULT 'negative',
    severity          SMALLINT CHECK (severity BETWEEN 1 AND 3),
    occurred_at       TIMESTAMPTZ NOT NULL,
    resolved          BOOLEAN DEFAULT false,
        -- フォロー対応済みかどうか
    resolved_at       TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_meta_log_profile_unresolved
    ON meta_log_entries(profile_id, resolved)
    WHERE resolved = false;
```

### 2.4 trait_signal_history テーブル

Trait の推定履歴を保持する。推定精度の検証と将来のモデル改善に使用する。

```sql
CREATE TABLE trait_signal_history (
    history_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id        UUID NOT NULL REFERENCES subjective_profiles(profile_id),
    trust_event_id    UUID REFERENCES trust_events(trust_event_id),

    raw_signal        TEXT NOT NULL,
        -- TrustEvent.trait_signal の生テキスト
    extracted_tags    VARCHAR(50)[],
        -- この信号から抽出されたタグ
    confidence        NUMERIC(3,2),
    detected_at       TIMESTAMPTZ NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

## 3. 更新ロジック設計

### 3.1 更新トリガーとタイミング

| トリガー | 更新対象 | タイミング |
|---|---|---|
| 新規 TrustEvent 生成 | meta_log_entries（Meta 層） | TrustEvent 生成後・即時 |
| 新規 Visit 登録 | latest_state（State 層） | Visit 登録後・即時 |
| 週次バッチ | trait_summary / trait_tags（Trait 層） | 毎週日曜深夜 |
| 週次バッチ | meta_risk_level / unresolved_meta_count | 同上 |

**Trait の更新を週次バッチにする理由**：Trait は長期的な傾向であり、毎日更新する必要がない。
また AI による要約生成はコストがかかるため、週次でまとめて処理する。

### 3.2 Trait 算出ロジック（週次バッチ）

```python
async def update_trait_summary(customer_id: UUID):
    """
    直近90日のTrustEventからtrait_signalを収集し、
    AI でTrait要約を生成する
    """
    # 1. 直近90日のtrait_signalを収集
    signals = await get_trait_signals(customer_id, days=90)

    if len(signals) < 3:
        # シグナルが少なすぎる場合は更新しない
        return

    # 2. AI でTrait要約を生成
    prompt = TRAIT_SUMMARY_PROMPT_TEMPLATE.format(
        signals="\n".join(f"- {s.raw_signal}" for s in signals),
        visit_count=len(signals),
    )
    result = await client.interpret(prompt)

    # 3. SubjectiveProfile を更新
    await update_profile_trait(
        customer_id    = customer_id,
        trait_summary  = result["summary"],
        trait_tags     = result["tags"],
        trait_confidence = result["confidence"],
        source_event_count = len(signals),
        is_reliable    = len(signals) >= 10,
    )
```

### 3.3 Meta リスクレベルの算出ロジック

```python
def calculate_meta_risk_level(unresolved_entries: list[MetaLogEntry]) -> str:
    """
    未解決のMetaイベントからリスクレベルを算出する
    """
    if not unresolved_entries:
        return "none"

    # 重み付きスコア（severity × recency_decay）
    score = 0.0
    now = datetime.now(UTC)
    for entry in unresolved_entries:
        days_ago = (now - entry.occurred_at).days
        decay = 1.0 if days_ago <= 30 else (0.7 if days_ago <= 60 else 0.4)
        score += entry.severity * decay

    if score >= 6.0:
        return "high"
    elif score >= 3.0:
        return "medium"
    else:
        return "low"
```

---

## 4. AI プロンプト設計（Trait 要約用）

### 4.1 プロンプトテンプレート

```python
TRAIT_SUMMARY_PROMPT_TEMPLATE = """
あなたはブランド信頼の分析専門家です。
以下は、ある顧客に関して複数の来店・接客体験から抽出された主観的傾向の手がかりです。

## 収集された傾向の手がかり（{visit_count}件の来店から）

{signals}

## 指示

これらの手がかりを統合し、この顧客の長期的な価値観・選好（Trait）を推定してください。

注意事項：
- 単発の出来事ではなく、複数の手がかりに共通するパターンを抽出してください
- 推測が難しいものは含めないでください
- 接客スタッフが参考にできる実用的な表現にしてください

## 出力形式（JSONのみ）

{{
  "summary": "この顧客の傾向を2〜3文で要約した自然言語テキスト",
  "tags": ["タグ1", "タグ2", "タグ3"],
  "confidence": 0.0〜1.0,
  "basis_count": 手がかりのうち要約に使用した件数（整数）
}}
"""
```

### 4.2 Trait タグの標準セット

AI が出力する `tags` は自由形式だが、以下の標準タグへの正規化を推奨する。
正規化はPhase 2 中盤で実施する。

| カテゴリ | 標準タグ例 |
|---|---|
| 品質・価格 | 品質重視, 価格重視, コスパ重視, 高単価許容 |
| 接客スタイル | 押し売り嫌い, 相談好き, 自己判断型, 丁寧対応希望 |
| 購入目的 | ギフト購入多, 自分用メイン, 実用重視, ブランド重視 |
| 来店スタイル | 下見多い, 即決型, 比較検討型, リピーター |
| 情報ニーズ | 詳細説明希望, 簡潔説明希望, 素材・品質情報重視 |

---

## 5. 接客前コンテキスト提供の設計

### 5.1 用途

Phase 3 以降、接客スタッフが顧客対応前に SubjectiveProfile を参照できるようにする。
設計書 v1 §10（Phase 3）の「接客前コンテキスト提供」に対応する。

### 5.2 表示仕様（店舗ダッシュボード連携）

```
┌─────────────────────────────────────┐
│ 顧客プロフィール（参考情報）          │
│ ※ AI推定に基づく仮説です            │
├─────────────────────────────────────┤
│ 傾向                                 │
│ 品質重視・押し売り嫌い・ギフト購入多  │
│                                      │
│ 直近の来店目的                       │
│ ギフト選び（下見）                   │
│                                      │
│ 注意事項                             │
│ ⚠️ 前回の欠品対応で不満が残っている  │
└─────────────────────────────────────┘
```

表示条件：
- `is_reliable=true` の場合のみ表示する
- `meta_risk_level='high'` の場合は注意事項を強調表示する
- `trait_confidence < 0.6` の場合は傾向欄を非表示にする

### 5.3 API 設計（Phase 3 先行設計）

```
GET /api/v1/customers/{customer_id}/subjective-profile

Response:
{
  "customer_id": "...",
  "is_reliable": true,
  "trait": {
    "summary": "品質重視・押し売りを嫌う傾向。ギフト購入が多い",
    "tags": ["品質重視", "押し売り嫌い", "ギフト購入多"],
    "confidence": 0.82
  },
  "latest_state": {
    "purpose": "gift",
    "visit_date": "2026-03-20"
  },
  "meta": {
    "risk_level": "medium",
    "unresolved_count": 1,
    "latest_entry": {
      "type": "out_of_stock_dissatisfaction",
      "description": "前回の欠品対応で不満が残っている",
      "occurred_at": "2026-03-10"
    }
  }
}
```

---

## 6. 段階的導入計画

### 6.1 Phase 別の実装範囲

| Phase | 実装内容 | 前提条件 |
|---|---|---|
| Phase 1（現在） | TrustEventへの手がかり蓄積のみ | — |
| Phase 2 前半 | DBマイグレーション・Meta層の即時更新 | Phase 1 本稼働4週以上 |
| Phase 2 中盤 | State層の更新・週次Trait算出バッチ | Meta層が安定稼働 |
| Phase 2 後半 | is_reliable判定・精度検証 | Trait算出4週分のデータ |
| Phase 3 | 接客前コンテキスト提供API | is_reliable=trueの顧客が一定数以上 |

### 6.2 Phase 2 前半の着手条件

設計書 v1 §10（Phase 2）では「Trait/State/Meta 手がかりの蓄積と顧客 SubjectiveProfile の**試験構築**」と定義されている。
「試験構築」であるため、全顧客への適用ではなくサンプル顧客での検証から始める。

以下をすべて満たしたタイミングで着手する。

```sql
-- 着手条件の確認クエリ
SELECT
    COUNT(DISTINCT customer_id)                        AS customers_with_signals,
    COUNT(*) FILTER (WHERE trait_signal IS NOT NULL)   AS trait_signal_count,
    COUNT(*) FILTER (WHERE meta_signal  IS NOT NULL)   AS meta_signal_count,
    MIN(detected_at)                                   AS first_event_at,
    MAX(detected_at)                                   AS last_event_at
FROM trust_events
WHERE customer_id IS NOT NULL;
```

目安：
- シグナルを持つ顧客が 20 名以上
- `meta_signal` の件数が 30 件以上
- Phase 1 本稼働から 4 週以上経過

---

## 7. プライバシー・ガバナンス

設計書 v1 §8.1 の方針を具体化する。

**法務確認が必要な項目**（Phase 2 前半着手前に実施）

- `trait_summary` / `trait_tags` は個人情報保護法上の「個人関連情報」に該当しうる
- 第三者提供・外部連携を行う場合は本人同意が必要になる可能性がある
- 保持期間のポリシー策定（暫定：最終来店から2年）

**運用ルール**

- Profile の閲覧権限は接客スタッフに限定する（本部の個人別参照は原則禁止）
- `is_reliable=false` の Profile は接客前表示に使用しない
- Profile の内容が不正確だと顧客から申し出があった場合の修正・削除手順を明文化する

---

## 8. 実装ファイル一覧（Phase 2 前半）

```
src/python/
├── db/
│   └── migrations/versions/
│       └── xxxx_add_subjective_profiles.py   ← 新規
├── models/
│   └── subjective_profile.py                  ← 新規
├── batch/
│   └── profile_updater.py                     ← 新規（週次Trait算出）
├── ai/
│   └── prompts/
│       └── trait_summary.py                   ← 新規
└── api/
    └── routers/
        └── subjective_profile.py              ← 新規（Phase 3）

tests/python/
├── models/
│   └── test_subjective_profile.py             ← 新規
└── batch/
    └── test_profile_updater.py                ← 新規
```
