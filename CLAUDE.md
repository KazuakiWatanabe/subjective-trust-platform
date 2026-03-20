# CLAUDE.md
# subjective-trust-platform — Claude Code 向け実装ガイド

このファイルは Claude Code がリポジトリを開いたときに自動的に読み込まれる。
**作業を開始する前に必ずこのファイルと AGENTS.md を読むこと。**
**AGENTS.md が最上位ルールであり、本ファイルはその補足である。**

---

## このプロジェクトについて

実店舗向けブランド信頼観測システム。顧客主観（Trait / State / Meta）を構造的に観測・解釈し、
5次元の信頼スコアを算出して改善ループを回す。

詳細な背景・設計は以下を参照すること（作業前に関連する章を必ず読むこと）。

| ドキュメント | 参照すべきタイミング |
|---|---|
| `task/task-phase1.md` | 実装タスク一覧・AC・作業手順の確認 |
| `docs/trust-observation-system-v1.md` | データモデル・AI解釈・スコア算出・KPI の実装時 |
| `docs/whitepaper-brand-trust.md` | 信頼の概念・5次元・Trait/State/Meta の理解が必要な時 |
| `docs/language-selection.md` | 言語・技術選定の判断根拠を確認したい時 |
| `AGENTS.md` | コーディング規約・テスト規約・セキュリティ規約・禁止事項の確認 |

---

## 現在のフェーズ：Phase 1

**Python 単独実装。`src/csharp/` への書き込みは禁止。**

Phase 2 以降で C# 業務本体への移管を予定しているコンポーネントには、
以下のコメントを必ず残すこと。

```python
# TODO(phase2): C# 移管予定 — スコア算出サービス
```

---

## 作業開始時のチェックリスト

新しいタスクに着手する前に以下を確認すること。

- [ ] `AGENTS.md` のセキュリティルール・禁止事項を確認した
- [ ] 対象タスクの `ac_ids` と `source_spec` を確認した
- [ ] 現在 Phase 1 であることを確認した（`src/csharp/` は触らない）
- [ ] テストタスクの場合、`target_files` と `target_functions` が 2 つ以内であることを確認した
- [ ] AI 解釈に関わるタスクの場合、`confidence` チェックと `needs_review` の実装を含めた
- [ ] 新規 `import` を追加する場合、`pyproject.toml` 記載済みであることを確認した
- [ ] **auto-accept モードをオフにして作業していることを確認した**

---

## コマンド早見表

```bash
# 開発環境セットアップ
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 型チェック・フォーマット（コミット前に必ず実行）
mypy --strict src/python/
ruff check src/python/ && ruff format src/python/

# テスト実行
pytest tests/python/unit/                        # ユニットテストのみ
pytest tests/python/ -m integration              # 統合テスト（DB 必要）
pytest tests/python/ --cov=src/python --cov-report=term-missing  # カバレッジ付き

# エビデンス保存（タスク完了時に必ず実行）
pytest tests/python/unit/        -v > tests/python/evidence/unit_result.txt
pytest tests/python/integration/ -v > tests/python/evidence/integration_result.txt

# セキュリティ監査（パッケージ追加・変更時に必ず実行）
pip-audit > tests/python/evidence/security_audit.txt

# DB マイグレーション
alembic upgrade head
alembic revision --autogenerate -m "add_xxx_table"

# ローカル API 起動
uvicorn src.python.api.main:app --reload

# 日次 AI 解釈バッチ（手動実行）
python -m src.python.interpretation.pipeline --date=2026-03-20
```

---

## よく参照する仕様箇所

### AI 解釈出力スキーマ（設計書 §3.3）

```python
# このスキーマは変更禁止
{
    "trust_dimension": "service | product | proposal | operation | story",
    "sentiment": "positive | negative | neutral",
    "severity": 1 | 2 | 3,
    "theme_tags": [...],
    "summary": "1文の要約",
    "interpretation": "なぜそう感じたと推定されるかの1文解釈",
    "subjective_hints": {
        "trait_signal": str | None,
        "state_signal": str | None,
        "meta_signal": str | None
    },
    "confidence": 0.0〜1.0  # < 0.6 → needs_review = True
}
```

### 信頼スコア算出式（設計書 §2.4）

```
dimension_score = base_score(50)
  + Σ(positive_event_weight × recency_decay)
  - Σ(negative_event_weight × severity × recency_decay)

recency_decay: 直近4週=1.0 / 5〜8週=0.7 / 9〜12週=0.4 / それ以前=0.1
```

### 主要テーブルのインデックス（設計書 §4.2）

```sql
-- TrustEvent
CREATE INDEX idx_trust_event_store_dim_date
  ON trust_event (store_id, trust_dimension, detected_at);

-- TrustScoreSnapshot
CREATE UNIQUE INDEX uq_trust_score_snapshot
  ON trust_score_snapshot (target_type, target_id, snapshot_date);
```

### アラート閾値（設計書 §7.1）

| アラート種別 | 閾値 |
|---|---|
| 接客後離脱率上昇 | 前4週平均 × 1.5 |
| 押し売り感タグ急増 | 前4週平均 × 2.0 |
| 欠品不満継続 | 3週連続増加 |
| 再来店意向低下 | 2週連続 0.3pt 以上低下 |

---

## 迷ったときの判断基準

**Q. この処理は Python に残すべきか C# に移管予定か？**
→ AI 解釈・バッチ集計・分析スクリプトは Python。REST API・業務ロジック・スコア算出・DB 操作は Phase 2 で C# へ移管予定。Phase 1 では Python で実装しつつ `# TODO(phase2):` コメントを残す。

**Q. AI の解釈結果を DB に書いてよいか？**
→ `generated_by = "ai"` を必ず記録し、`confidence < 0.6` なら `needs_review = True` をセットすること。確定事実として扱うコードは書かない。

**Q. 個人を特定できる情報を Claude API / Bedrock に送ってよいか？**
→ 禁止。自由記述テキストのみ送信し、氏名・電話番号等は AI 前処理でマスキングする（設計書 §8.3）。

**Q. スタッフ個人の集計クエリを書いてよいか？**
→ Phase 1 では禁止（設計書 §8.2）。

**Q. テストで実際の Claude API / Bedrock を叩いてよいか？**
→ 禁止。`BaseInterpretationClient` のモックを使用すること。

**Q. 既存コードで使われている `import` をそのまま新しいファイルで使ってよいか？**
→ 禁止。必ず `AGENTS.md` のセキュリティチェック手順を実施してから使用すること。
既存コードで使われているからといって安全とは限らない。
差分確認だけで安全と判断してはならない。パッケージ本体・SDK ラッパーの実装まで確認すること。

**Q. 新しいパッケージを追加してよいか？**
→ `pyproject.toml` に記載がない場合は、PyPI 公式ページとソースコードを確認してから追加する。
追加後は必ず `pip-audit` を実行し、evidence ファイルを保存すること。

**Q. 外部 API への通信を実装してよいか？**
→ `AGENTS.md` の allowlist に登録されているドメインのみ許可。未登録の場合は allowlist を更新してからコードに反映すること。

**Q. タスクが完了したとはいつ言えるか？**
→ pytest が全件 PASS、かつ `tests/python/evidence/` に結果ファイルが保存されていること。evidence なしのタスク完了は認めない。
