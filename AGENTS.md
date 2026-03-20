# AGENTS.md
# subjective-trust-platform — Agent 向け作業ガイド

本ドキュメントは、AI エージェント（Claude Code 等）および人間が本リポジトリで作業する際の
最上位ルールを定義する。README・設計書・他のドキュメントより **AGENTS.md を優先**すること。
**作業開始前に必ず全セクションを読むこと。**

---

## アーキテクチャ方針（フェーズ別言語戦略）

本プロジェクトは以下のフェーズ別言語戦略を採用する。
**作業前に現在の対象フェーズを確認し、該当する制約に従うこと。**

| Phase | 期間 | 言語構成 | 優先事項 |
|---|---|---|---|
| **Phase 1** | 3ヶ月 | **Python 単独** | PoC 速度・AI 解釈の安定稼働 |
| **Phase 2** | +3ヶ月 | **Python（AI ワーカー）+ C#（業務本体）導入開始** | 疎結合設計・インターフェース整備 |
| **Phase 3** | +6ヶ月〜 | **Python AI ワーカー + C# 業務本体（本格稼働）** | 責務分離・Agent 構成・Trust API |

### Phase 1（現在）— Python 単独

- バックエンド全体を Python で実装する
- **Phase 2 移行を見据えた疎結合設計を Phase 1 から徹底する**
  - AI 解釈クライアントは抽象基底クラスで包み、呼び出し先（Anthropic 直接 / Bedrock）を設定で切り替え可能にする
  - サービス層のインターフェースを明確に定義し、C# への責務移管が容易な構造にする
  - `TrustEvent` 生成・スコア算出・REST API の各責務を独立したモジュールに分離する
- **`src/csharp/` への書き込みは禁止**

### Phase 2/3 — Python + C# 混成

- **C# 担当領域**（ASP.NET Core / .NET 8 on Linux コンテナ）
  - REST API・業務ルール・DB 操作・認証・認可・監査ログ
- **Python 担当領域**（継続）
  - Claude API / Bedrock による AI 解釈パイプライン・TrustEvent 生成バッチ・集計分析
- **サービス間連携**
  - SQS（AWS）または Cloud Pub/Sub（GCP）経由のキューで非同期連携
  - DB スキーマの正は Alembic（Python）で管理し、C# EF Core はマイグレーションを使用しない

Phase 2 移管予定のコンポーネントには、Phase 1 実装時に以下のコメントを残すこと。

```python
# TODO(phase2): C# 移管予定 — スコア算出サービス
```

---

## 技術スタック

### Python（Phase 1 全体 / Phase 2 以降は AI ワーカー）

| 用途 | ライブラリ |
|---|---|
| Web フレームワーク | FastAPI |
| ORM / DB | SQLAlchemy 2.x + psycopg2 |
| バリデーション | pydantic v2 |
| AI 解釈 | `anthropic` SDK または `boto3`（Bedrock） |
| データ集計 | polars |
| テスト | pytest + pytest-asyncio |
| 型チェック | mypy（strict モード） |
| フォーマッタ | ruff |

### C#（Phase 2 以降・業務本体）

| 用途 | ライブラリ |
|---|---|
| Web フレームワーク | ASP.NET Core Minimal API (.NET 8) |
| ORM | Entity Framework Core 8 |
| バリデーション | FluentValidation |
| キュー連携 | AWSSDK.SQS または Google.Cloud.PubSub |
| テスト | xUnit + Moq |
| コンテナ | `mcr.microsoft.com/dotnet/aspnet:8.0`（Linux） |

---

## ディレクトリ構成（変更禁止）

```
subjective-trust-platform/
├── AGENTS.md                              # 本ファイル（最上位ルール）
├── CLAUDE.md                              # Claude Code 向け実装ガイド
├── README.md
├── task/
│   └── task-phase1.md                     # Phase 1 実装タスクリスト
├── docs/
│   ├── whitepaper-brand-trust.md
│   ├── trust-observation-system-v1.md
│   ├── architecture-overview.md
│   ├── summary-and-mermaid.md
│   └── language-selection.md
├── src/
│   ├── python/                            # Phase 1: 全体 / Phase 2+: AI ワーカー
│   │   ├── api/
│   │   │   ├── routers/
│   │   │   │   ├── visits.py
│   │   │   │   ├── feedback.py
│   │   │   │   └── scores.py
│   │   │   └── main.py
│   │   ├── domain/
│   │   │   ├── models/
│   │   │   ├── schemas/
│   │   │   └── services/
│   │   ├── interpretation/
│   │   │   ├── client.py                  # 抽象クライアント（Anthropic / Bedrock 切替）
│   │   │   ├── prompts.py
│   │   │   ├── pipeline.py
│   │   │   └── schemas.py
│   │   ├── scoring/
│   │   │   ├── calculator.py
│   │   │   └── weights.py
│   │   ├── db/
│   │   │   ├── session.py
│   │   │   └── migrations/                # Alembic（DB スキーマの正）
│   │   └── config.py
│   └── csharp/                            # Phase 2 以降に追加（Phase 1 は書き込み禁止）
│       ├── TrustPlatform.Api/
│       ├── TrustPlatform.Domain/
│       ├── TrustPlatform.Infrastructure/
│       └── TrustPlatform.Tests/
├── tests/
│   ├── python/
│   │   ├── unit/
│   │   ├── integration/
│   │   ├── fixtures/
│   │   └── evidence/                      # pytest -v の出力結果（コミット対象）
│   └── csharp/                            # Phase 2 以降
├── infra/
├── scripts/
├── pyproject.toml
└── .env.example
```

---

## コーディング規約

### Python

- **型アノテーション必須** — すべての関数引数・戻り値に型を付ける。`Any` は原則禁止
- **mypy strict** — `mypy --strict src/python/` がエラーゼロであること
- **ruff** — `ruff check` と `ruff format` をコミット前に実行
- **docstring** — Python ファイル先頭に「概要・入出力・制約・Note」を含む日本語 docstring を記述する。関数・メソッドは `Args / Returns / Raises / Note` を明示し、分岐意図が読み取りづらい処理には 1〜2 行の補助コメントを追加する
- **非同期** — I/O 処理（DB・AI API 呼び出し）はすべて `async/await` で実装する

### C#（Phase 2 以降）

- **.NET 8 / C# 12** を使用する
- **Nullable 参照型を有効化** — `<Nullable>enable</Nullable>`
- **Minimal API スタイル** を優先する（Controller クラスは使わない）
- **ドメインモデルはイミュータブル** — `record` 型を積極的に使用する
- **EF Core マイグレーションは作成しない** — スキーマの正は Alembic（Python）

### 共通

- コメントは日本語で書いてよい
- `TODO` は `# TODO(phase2): C# 移管予定` のようにフェーズ番号を付ける

---

## AI 解釈パイプライン — 実装制約

設計書（`docs/trust-observation-system-v1.md` §3.3）に基づく制約。

### 出力スキーマ（変更禁止）

```python
class TrustInterpretation(BaseModel):
    trust_dimension: Literal["service", "product", "proposal", "operation", "story"]
    sentiment: Literal["positive", "negative", "neutral"]
    severity: Literal[1, 2, 3]
    theme_tags: list[str]
    summary: str
    interpretation: str
    subjective_hints: SubjectiveHints
    confidence: float  # 0.0〜1.0
```

### 必須ルール

- `confidence < 0.6` の場合は `needs_review = True` を自動でセットする
- AI クライアントは `BaseInterpretationClient` 抽象クラスを実装し、Anthropic 直接と Bedrock を設定で切り替え可能にする
- プロンプトは `prompts.py` に集約し、`PROMPT_VERSION` 定数でバージョン管理する
- AI 解釈結果を `TrustEvent` に書き込む際、`generated_by = "ai"` を記録する

---

## データベース — 実装制約

- **スキーマ変更は Alembic マイグレーションで管理する**（C# EF Core は参照のみ）
- `TrustEvent` に `(store_id, trust_dimension, detected_at)` の複合インデックスを必ず作成する
- `TrustScoreSnapshot` に `(target_type, target_id, snapshot_date)` のユニーク制約を設定する
- `Visit.visit_purpose` は State 情報として扱う — カラムの意味を変えてはならない

---

## テスト規約

### 基本原則

- **テストファースト** — 実装の前にテストを書き、RED を確認してから実装に入ること
- **仕様の証明** — テストは「コードが動く」ことではなく「仕様を満たしている」ことを証明するものとして書くこと
- **独立性の確保** — 各テストは他のテストに依存せず、単独で実行可能であること
- **スコープの厳守** — 指定された `target_files` / `target_functions` 以外のコードには原則触れないこと
- **テストの削除・スキップによる PASS は禁止**

### テストタスクの設定項目

テストコードを生成・追加するタスクでは、以下の項目を必ず明示してから作業を開始すること。

```yaml
target_files:        # 対象ファイルパス（最大2ファイル/タスク）
target_functions:    # 対象クラス/関数/APIエンドポイント（最大2つ/タスク）
test_scope:
  include:           # 今回追加すべきテストの範囲
  exclude:           # 今回は対象外にする観点
source_spec:         # 仕様書ファイルパス（例: docs/trust-observation-system-v1.md#3.3）
ac_ids:              # 受け入れ条件 ID と内容
coverage_threshold:  # 目標カバレッジ %
task_constraints:
  max_test_cases: 12
  min_test_cases: 5
```

### テスト観点チェックリスト

**Phase 0（必須）— すべてのタスクで対応**
- 正常系：代表的な入力値での期待動作
- 主要な異常系：不正入力・必須欠落・例外スロー
- 副作用：DB・外部ストアの状態が正しく変化すること

**Phase 1（原則対応）**
- 境界値：最大・最小・空・null・0・false
- エラーメッセージの内容が仕様通りであること
- 外部 API 呼び出しの引数・回数が正しいこと（モック検証）

**Phase 2（`test_scope.include` に明示された場合のみ）**
- 冪等性・並行実行耐性・パフォーマンス上限

### テストコードの記述ルール

各テストケースには `ac_ids` から対応する ID を必ずコメントで明記すること。
AC ID が存在しない観点のテストは追加しないこと（コメント捏造禁止）。

```python
# AC-01: confidence < 0.6 の場合は needs_review = True をセットする
def test_低信頼度の解釈結果はレビューフラグが立つ():
    ...
```

### モック・スタブの使用方針

| 依存の種類 | 方針 |
|---|---|
| Claude API / Bedrock クライアント | モック化（呼び出し引数・回数を検証） |
| リポジトリ層（DB） | インメモリ偽実装を使用 |
| SQS / Pub/Sub | モック化 |
| 時刻・乱数 | 固定値に差し替え |
| 同一サービス内の別クラス | 原則モックしない |

### エビデンス保存（タスク完了の条件）

```bash
pytest tests/python/unit/        -v > tests/python/evidence/unit_result.txt
pytest tests/python/integration/ -v > tests/python/evidence/integration_result.txt
```

- `tests/python/evidence/` の `.txt` ファイルはコミット対象とする（証跡として残す）
- タスク完了の定義は **pytest が全件 PASS** かつ **evidence ファイルが保存されている** こと

### 自己検証ステップ（実装後に必ず実行）

```
Step 1. テストが PASS であることを確認する
Step 2. 実装の核となるロジックを意図的に壊し、テストが FAIL になることを確認する
Step 3. 壊した実装を元に戻し、再度 PASS になることを確認する
Step 4. Step 2 で FAIL にならなかったテストは検証内容を見直して修正する
```

> ⚠️ Step 2 で FAIL にならない場合、そのテストは仕様を証明していないと見なす

---

## セキュリティルール（サプライチェーン攻撃対策）

> **背景**
> AI は「既存コードで使われているパッケージ」を既知・安全なものとして扱い、
> 悪意あるコードをそのまま新しいファイルへ踏襲する場合がある（攻撃成功率100%の事例あり）。
> CLAUDE.md への直接的なバックドア指示は防がれるが、既存コードのパターンは精査されない。
> このセクションはその盲点を補う多重防御として機能する。

### AI・人間の双方が遵守するルール

| ルール | 詳細 |
|---|---|
| **既存 import の盲信禁止** | 既存コードに含まれる `import` / `from ... import` であっても、初めて別ファイルで使う際は下記チェックを必ず実施する |
| **差分確認だけで安全と判断しない** | 新規追加コードの差分だけでなく、そのコードが参照する既存モジュール・依存パッケージ本体・SDK ラッパーの実装まで確認すること |
| **依存パッケージ本体の重点監査** | ログ・HTTP・認証・設定読込・監査・telemetry・monitoring・analytics・SDK ラッパー系ライブラリは優先的に実装を目視確認する |
| **環境変数の外部送信禁止** | `os.environ` / `os.getenv` の値を外部 URL へ送信するコードを一切書かない |
| **許可リスト外パッケージの使用禁止** | `pyproject.toml` / `requirements.txt` に記載のないパッケージを追加する場合は、PyPI 公式ページ・ソースコードを確認してからのみ追加可とする |
| **外部通信先の allowlist 管理** | 外部通信先は下記 allowlist に登録されたドメインのみ許可する。未登録先への通信実装は禁止する。"internal-monitoring" 等のそれらしい名称であっても例外なし |
| **auto-accept モードの使用禁止** | Claude Code を auto-accept で運用しない。生成コードは必ず確認してから適用する |

### 外部通信先 allowlist

本リポジトリで許可する通信先ドメインを以下に限定する。
追加する場合はこのリストを更新したうえでレビューを受けること。

```
# AI 解釈（直接呼び出し）
api.anthropic.com               # Anthropic Claude API

# AI 解釈（AWS Bedrock 経由）
bedrock-runtime.*.amazonaws.com # Amazon Bedrock
bedrock.*.amazonaws.com

# AWS インフラ
sqs.*.amazonaws.com             # Amazon SQS
rds.*.amazonaws.com             # Amazon RDS
lambda.*.amazonaws.com          # AWS Lambda
*.execute-api.*.amazonaws.com   # API Gateway

# GCP インフラ（GCP 構成の場合）
*.googleapis.com                # Cloud Run / Cloud SQL / Pub/Sub 等
*.google.com                    # Google Cloud SDK

# パッケージ取得
pypi.org
files.pythonhosted.org
nuget.org                       # C# パッケージ（Phase 2 以降）
```

> **Note**
> Phase 2 以降で LINE / CRM 等の外部サービスを接続する際は、
> そのエンドポイントを必ずここに追記してからコードに反映すること。
> allowlist 未追記のまま通信実装を進めることは禁止。

### セキュリティチェック手順（パッケージ追加・変更時）

```bash
# Python
pip install pip-audit
pip-audit > tests/python/evidence/security_audit.txt

# C#（Phase 2 以降）
dotnet list package --vulnerable > tests/csharp/evidence/security_audit.txt
```

目視確認ポイント（新規パッケージのソースコードを確認する）:

- `httpx` / `requests` / `urllib` 等による外部通信
- `os.environ` / `os.getenv` の参照と外部送信
- `subprocess` / `eval` / `exec` の使用
- `logging` / `telemetry` / `monitoring` / `analytics` 系の内部実装（外部送信が隠れていないか）
- hook / plugin 的な拡張ポイントの存在

### コードレビューチェックリスト（PR 時）

- [ ] 新規 `import` 文はすべて `pyproject.toml` 記載のパッケージか
- [ ] **差分コードだけでなく、そのコードが参照する既存モジュール・依存パッケージ本体を確認したか**
- [ ] ログ・HTTP・認証・設定読込・監査・SDK ラッパー系パッケージの実装を目視したか
- [ ] 環境変数（`os.environ` / `os.getenv`）を外部へ送信していないか
- [ ] 外部 HTTP リクエストの送信先がすべて allowlist 内のドメインか
- [ ] `logging` / `telemetry` / `monitoring` 系ライブラリが裏で外部送信していないか
- [ ] 既存パッケージのパターンを踏襲する際に、そのパッケージ本体が安全であることを確認したか
- [ ] `tests/python/evidence/` にエビデンスファイルが含まれているか

---

## 禁止事項まとめ

- `Any` 型の多用（やむを得ない場合は `# type: ignore` にコメントを付ける）
- AI 解釈結果を確定事実として扱うコード
- `confidence` チェックを省略した `TrustEvent` の生成
- Alembic を使わないスキーマ変更
- Phase 1 段階での `src/csharp/` への書き込み
- スタッフ個人を特定できる集計クエリの実装（設計書 §8.2）
- Claude API / Bedrock への個人識別情報の混入（設計書 §8.3）
- allowlist 未登録ドメインへの外部通信実装
- auto-accept モードでの Claude Code 運用
- 既存 `import` の無確認踏襲
- テストの削除・スキップによる PASS
- evidence ファイルなしのタスク完了
