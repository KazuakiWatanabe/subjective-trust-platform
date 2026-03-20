# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**作業を開始する前に必ずこのファイルと AGENTS.md を読むこと。**
**AGENTS.md が最上位ルールであり、本ファイルはその補足である。**

---

## プロジェクト概要

実店舗向けブランド信頼観測システム。顧客主観（Trait / State / Meta）を構造的に観測・AI解釈し、
5次元の信頼スコア（商品・接客・提案・運営・物語）を算出して改善ループを回す。

### アーキテクチャ（6層構造）

```
観測層 → 解釈層 → 信頼状態層 → 判断層 → 介入層 → 学習層
(Phase 1 で実装)                (Phase 3 以降)
```

- **観測層**: POS連携・接客タグ入力・ミニアンケートで接点データを収集
- **解釈層**: Claude API/Bedrock で自由記述を解釈し、5次元×sentiment×severity に構造化
- **信頼状態層**: TrustEvent を集計し、recency_decay 付きで次元別スコアを算出

### データフロー

```
接客タグ/アンケート → Visit/Feedback → AI解釈パイプライン → TrustEvent → スコア算出 → TrustScoreSnapshot
```

AI解釈は日次バッチで実行。`confidence < 0.6` の結果は `needs_review = True` で人間レビューに回す。

---

## 現在のフェーズ：Phase 1（Python 単独）

**`src/csharp/` への書き込みは禁止。** 実装はすべて Python で行う。

Phase 2 移管予定のコンポーネントには `# TODO(phase2): C# 移管予定 — 〇〇` コメントを残すこと。

Python に残る処理: AI 解釈・バッチ集計・分析スクリプト
Phase 2 で C# へ移管: REST API・業務ロジック・スコア算出・DB 操作

### 実装タスク順序

`task/task-phase1.md` に T-00〜T-15 のタスク一覧がある。T-00（Docker環境構築）が全タスクの前提。

---

## ドキュメント参照表

| ドキュメント | 参照すべきタイミング |
|---|---|
| `task/task-phase1.md` | 実装タスク一覧・AC・作業手順の確認 |
| `docs/trust-observation-system-v1.md` | データモデル・AI解釈・スコア算出・KPI の実装時 |
| `docs/whitepaper-brand-trust.md` | 信頼の概念・5次元・Trait/State/Meta の理解が必要な時 |
| `docs/language_selection_report.md` | 言語・技術選定の判断根拠を確認したい時 |
| `docs/architecture-overview.md` | Phase 3 以降の全体構造・Agent 構成の確認 |
| `AGENTS.md` | コーディング規約・テスト規約・セキュリティ規約・禁止事項の確認 |

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

# 単一テストファイル / 単一テスト関数の実行
pytest tests/python/unit/test_scoring.py -v
pytest tests/python/unit/test_scoring.py::test_関数名 -v

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

## 作業開始時のチェックリスト

- [ ] `AGENTS.md` のセキュリティルール・禁止事項を確認した
- [ ] 対象タスクの `ac_ids` と `source_spec` を `task/task-phase1.md` で確認した
- [ ] 現在 Phase 1 であることを確認した（`src/csharp/` は触らない）
- [ ] テストタスクの場合、`target_files` と `target_functions` が 2 つ以内であることを確認した
- [ ] AI 解釈に関わるタスクの場合、`confidence` チェックと `needs_review` の実装を含めた
- [ ] 新規 `import` を追加する場合、`pyproject.toml` 記載済みであることを確認した
- [ ] **auto-accept モードをオフにして作業していることを確認した**

---

## よく参照する仕様（詳細は設計書を参照）

### 信頼スコア算出式（設計書 §2.4）

```
dimension_score = base_score(50)
  + Σ(positive_event_weight × recency_decay)
  - Σ(negative_event_weight × severity × recency_decay)

recency_decay: 直近4週=1.0 / 5〜8週=0.7 / 9〜12週=0.4 / それ以前=0.1
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

**Q. AI の解釈結果を DB に書いてよいか？**
→ `generated_by = "ai"` を必ず記録し、`confidence < 0.6` なら `needs_review = True` をセット。確定事実として扱うコードは書かない。

**Q. 個人を特定できる情報を Claude API / Bedrock に送ってよいか？**
→ 禁止。自由記述テキストのみ送信し、氏名・電話番号等は AI 前処理でマスキングする（設計書 §8.3）。

**Q. テストで実際の Claude API / Bedrock を叩いてよいか？**
→ 禁止。`BaseInterpretationClient` のモックを使用すること。

**Q. 既存コードで使われている `import` をそのまま新しいファイルで使ってよいか？**
→ 禁止。`AGENTS.md` のセキュリティチェック手順を必ず実施。パッケージ本体・SDK ラッパーの実装まで確認すること。

**Q. 外部 API への通信を実装してよいか？**
→ `AGENTS.md` の allowlist に登録されているドメインのみ許可。未登録の場合は allowlist を更新してからコードに反映。

**Q. タスクが完了したとはいつ言えるか？**
→ pytest が全件 PASS、かつ `tests/python/evidence/` に結果ファイルが保存されていること。
