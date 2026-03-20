# Phase 1 実装タスクリスト
# subjective-trust-platform
# 格納パス: task/task-phase1.md

フェーズ: **Phase 1（Python 単独 / 3ヶ月 PoC）**
対象: 直営5店舗・AI解釈パイプライン・信頼スコア算出・店舗ダッシュボード API

---

## 実行環境方針

```
ローカル開発  →  Docker Compose で完結
クラウド展開  →  ローカルで動作確認済みのイメージをそのまま使用
```

- **開発・検証はすべてローカル Docker で完結させてからクラウドへ上げる**
- ローカルと本番で同一イメージを使用し、「手元では動くが本番で動かない」を排除する
- クラウド固有の設定（DB 接続先・AI バックエンド切替等）は環境変数のみで切り替える

---

## タスク一覧

| ID | カテゴリ | タスク名 | 依存 | 優先度 |
|---|---|---|---|---|
| T-00 | **Docker** | **ローカル Docker 環境構築** | — | 🔴 最高 |
| T-01 | 基盤 | プロジェクト初期セットアップ | T-00 | 🔴 最高 |
| T-02 | 基盤 | DB スキーマ定義・マイグレーション | T-01 | 🔴 最高 |
| T-03 | AI解釈 | AI 解釈クライアント抽象実装 | T-01 | 🔴 最高 |
| T-04 | AI解釈 | AI 解釈プロンプト定義 | T-03 | 🔴 最高 |
| T-05 | AI解釈 | AI 解釈パイプライン（日次バッチ） | T-02, T-04 | 🔴 最高 |
| T-06 | スコア算出 | 重みテーブル定義 | T-02 | 🔴 最高 |
| T-07 | スコア算出 | 信頼スコア算出ロジック | T-06 | 🔴 最高 |
| T-08 | API | 接客タグ入力エンドポイント | T-02 | 🔴 最高 |
| T-09 | API | アンケート受信エンドポイント | T-02 | 🔴 最高 |
| T-10 | API | スコア参照エンドポイント | T-07 | 🟠 高 |
| T-11 | バッチ | POS 日次連携バッチ | T-02 | 🟠 高 |
| T-12 | バッチ | TrustEvent 自動生成（ルールベース） | T-02 | 🟠 高 |
| T-13 | バッチ | 週次レポート自動生成 | T-07, T-10 | 🟡 中 |
| T-14 | バッチ | アラート生成バッチ | T-07 | 🟡 中 |
| T-15 | 運用 | コールドスタート対応（スコア表示制御） | T-07 | 🟡 中 |

---

## T-00: ローカル Docker 環境構築

> **全タスクの前提。これが完成してから T-01 以降に着手すること。**

```yaml
target_files:
  - "Dockerfile"
  - "docker-compose.yml"
source_spec: "AGENTS.md"
ac_ids:
  - "AC-01: docker compose up 一発でAPI・DB・バッチワーカーが起動する"
  - "AC-02: ローカルの Claude API キー（または Bedrock モック）で AI 解釈が動作する"
  - "AC-03: docker compose up 後に pytest が全件 PASS する"
  - "AC-04: 環境変数のみでローカル／クラウドを切り替えられる（コード変更不要）"
  - "AC-05: DB マイグレーションがコンテナ起動時に自動適用される"
task_constraints:
  max_test_cases: 5
  min_test_cases: 2
  coverage_threshold: 70
test_scope:
  include: "コンテナ起動・ヘルスチェック・DB 接続確認"
  exclude: "パフォーマンス・セキュリティスキャン"
```

### 成果物

**`Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]"

COPY src/ ./src/
COPY tests/ ./tests/
COPY alembic.ini .

ENV PYTHONPATH=/app/src/python
ENV PORT=8080

CMD ["uvicorn", "src.python.api.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

**`docker-compose.yml`**

```yaml
services:

  db:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: trust_platform
      POSTGRES_USER: trust_user
      POSTGRES_PASSWORD: trust_pass
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U trust_user -d trust_platform"]
      interval: 5s
      timeout: 5s
      retries: 5

  api:
    build: .
    ports:
      - "8080:8080"
    volumes:
      - ./src:/app/src        # ホットリロード用
      - ./tests:/app/tests
    environment:
      - DATABASE_URL=postgresql+asyncpg://trust_user:trust_pass@db:5432/trust_platform
      - AI_BACKEND=${AI_BACKEND:-mock}          # mock | anthropic | bedrock
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-}
      - ENVIRONMENT=local
    depends_on:
      db:
        condition: service_healthy
    command: >
      sh -c "alembic upgrade head &&
             uvicorn src.python.api.main:app
             --host 0.0.0.0 --port 8080 --reload"

  worker:
    build: .
    volumes:
      - ./src:/app/src
    environment:
      - DATABASE_URL=postgresql+asyncpg://trust_user:trust_pass@db:5432/trust_platform
      - AI_BACKEND=${AI_BACKEND:-mock}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-}
      - ENVIRONMENT=local
    depends_on:
      db:
        condition: service_healthy
    command: python -m src.python.interpretation.pipeline --watch

volumes:
  postgres_data:
```

**`.env.local`（git 管理対象外）**

```env
AI_BACKEND=mock                        # ローカルはモックで動作
ANTHROPIC_API_KEY=sk-ant-xxxxx         # 実 API を使う場合のみ設定
DATABASE_URL=postgresql+asyncpg://trust_user:trust_pass@localhost:5432/trust_platform
ENVIRONMENT=local
```

**`.env.example`（git 管理対象）**

```env
AI_BACKEND=mock            # mock | anthropic | bedrock
ANTHROPIC_API_KEY=
DATABASE_URL=
ENVIRONMENT=local
```

### AI_BACKEND=mock の設計指針

ローカル開発では実 API キーなしで AI 解釈を動作させるため、
`BaseInterpretationClient` の mock 実装を T-03 で必ず作成すること。

```python
class MockInterpretationClient(BaseInterpretationClient):
    """ローカル開発・テスト用モック。固定レスポンスを返す。"""
    async def interpret(self, text: str) -> TrustInterpretation:
        # fixtures/mock_interpretation.json から読み込む
        ...
```

### ローカル操作コマンド

```bash
# 起動
docker compose up --build

# テスト実行（コンテナ内）
docker compose exec api pytest tests/python/ -v

# エビデンス保存
docker compose exec api pytest tests/python/unit/ -v \
  > tests/python/evidence/unit_result.txt

# マイグレーション（手動実行）
docker compose exec api alembic upgrade head

# AI 解釈バッチを手動実行
docker compose exec worker \
  python -m src.python.interpretation.pipeline --date=2026-03-20

# ログ確認
docker compose logs -f api
docker compose logs -f worker

# 停止・データ削除
docker compose down
docker compose down -v   # DB データも削除
```

### ローカル → クラウド移行時の差分

| 項目 | ローカル | クラウド（AWS） |
|---|---|---|
| `AI_BACKEND` | `mock` または `anthropic` | `bedrock` |
| `DATABASE_URL` | `db:5432`（Compose 内） | RDS エンドポイント |
| コンテナ実行 | `docker compose up` | ECS Fargate |
| バッチ実行 | `docker compose exec worker` | Lambda + EventBridge |
| 環境変数管理 | `.env.local` | AWS Secrets Manager |

---

## T-01: プロジェクト初期セットアップ

```yaml
target_files:
  - "pyproject.toml"
  - "src/python/config.py"
source_spec: "AGENTS.md"
ac_ids:
  - "AC-01: mypy strict / ruff / pytest が pyproject.toml で設定されている"
  - "AC-02: 環境変数は config.py の pydantic Settings で一元管理される"
  - "AC-03: AI_BACKEND=mock のとき MockInterpretationClient が自動選択される"
  - "AC-04: .env.example に必要な変数がすべて記載されている"
task_constraints:
  max_test_cases: 5
  min_test_cases: 2
  coverage_threshold: 80
```

**作業内容**
- `pyproject.toml` に依存ライブラリ・mypy・ruff・pytest 設定を記述する
- `src/python/config.py` に pydantic `Settings` を定義する
  - `AI_BACKEND`（`mock` | `anthropic` | `bedrock`）、`DATABASE_URL`、`ENVIRONMENT` 等
- `.env.example` を作成する（実値を含めない）
- `src/python/db/session.py` に SQLAlchemy 非同期セッションを実装する

```python
# TODO(phase2): C# 移管予定 — DB セッション管理は EF Core に移行する
```

---

## T-02: DB スキーマ定義・マイグレーション

```yaml
target_files:
  - "src/python/domain/models/"
  - "src/python/db/migrations/"
source_spec: "docs/trust-observation-system-v1.md#4"
ac_ids:
  - "AC-01: 設計書 §4.2 の全テーブルが定義されている"
  - "AC-02: TrustEvent に (store_id, trust_dimension, detected_at) の複合インデックスがある"
  - "AC-03: TrustScoreSnapshot に (target_type, target_id, snapshot_date) のユニーク制約がある"
  - "AC-04: docker compose up 時に alembic upgrade head が自動実行される"
  - "AC-05: ローカル DB（postgres:15-alpine）でマイグレーションが正常完了する"
task_constraints:
  max_test_cases: 10
  min_test_cases: 5
  coverage_threshold: 80
test_scope:
  exclude: "パフォーマンス・並行性"
```

**作業内容**
- SQLAlchemy モデルを実装する（`Store`・`Staff`・`Customer`・`Visit`・`Feedback`・`TrustEvent`・`TrustScoreSnapshot`・`Purchase`・`ComplaintInquiry`・`ReviewExternal`）
- Alembic 初期マイグレーションを生成・ローカル DB に適用して動作確認する
- `docker compose up` 後に `psql` で全テーブルとインデックスを目視確認してからコミットする

---

## T-03: AI 解釈クライアント抽象実装

```yaml
target_files:
  - "src/python/interpretation/client.py"
source_spec: "docs/trust-observation-system-v1.md#3.2"
ac_ids:
  - "AC-01: BaseInterpretationClient 抽象クラスが定義されている"
  - "AC-02: MockInterpretationClient が実装されており AI_BACKEND=mock で動作する"
  - "AC-03: AnthropicClient と BedrockClient が実装されている"
  - "AC-04: AI_BACKEND 環境変数で呼び出し先を切り替えられる"
  - "AC-05: ローカルで AI_BACKEND=mock のとき実 API を一切呼び出さない"
task_constraints:
  max_test_cases: 10
  min_test_cases: 5
  coverage_threshold: 85
test_scope:
  exclude: "実際の API 呼び出し（モック必須）"
```

**作業内容**

```python
class BaseInterpretationClient(ABC):
    @abstractmethod
    async def interpret(self, text: str) -> TrustInterpretation: ...

class MockInterpretationClient(BaseInterpretationClient):
    """AI_BACKEND=mock 用。tests/fixtures/mock_interpretation.json を返す。"""
    async def interpret(self, text: str) -> TrustInterpretation: ...

class AnthropicClient(BaseInterpretationClient): ...
class BedrockClient(BaseInterpretationClient): ...

def get_interpretation_client() -> BaseInterpretationClient:
    backend = settings.AI_BACKEND
    if backend == "mock":   return MockInterpretationClient()
    if backend == "anthropic": return AnthropicClient()
    if backend == "bedrock":   return BedrockClient()
    raise ValueError(f"Unknown AI_BACKEND: {backend}")
    # TODO(phase2): C# から SQS 経由で呼び出す構成に変更予定
```

- `tests/fixtures/mock_interpretation.json` に代表的なモックレスポンスを用意する
- ローカルで `docker compose up` → `AI_BACKEND=mock` で API が正常起動することを確認してからコミットする

---

## T-04: AI 解釈プロンプト定義

```yaml
target_files:
  - "src/python/interpretation/prompts.py"
  - "src/python/interpretation/schemas.py"
source_spec: "docs/trust-observation-system-v1.md#3.3"
ac_ids:
  - "AC-01: TrustInterpretation が設計書 §3.3 のスキーマと完全に一致する"
  - "AC-02: confidence < 0.6 のとき needs_review = True になる"
  - "AC-03: PROMPT_VERSION 定数でプロンプトのバージョンが管理されている"
  - "AC-04: AI_BACKEND=mock でパイプライン全体がローカル実行できる"
task_constraints:
  max_test_cases: 8
  min_test_cases: 5
  coverage_threshold: 85
test_scope:
  exclude: "実際の API 呼び出し"
```

---

## T-05: AI 解釈パイプライン（日次バッチ）

```yaml
target_files:
  - "src/python/interpretation/pipeline.py"
source_spec: "docs/trust-observation-system-v1.md#3.2"
ac_ids:
  - "AC-01: Feedback.free_comment と ReviewExternal のテキストを対象に実行される"
  - "AC-02: AI 解釈結果が TrustEvent テーブルに書き込まれる"
  - "AC-03: confidence < 0.6 の TrustEvent には needs_review = True がセットされる"
  - "AC-04: generated_by = 'ai' が TrustEvent に記録される"
  - "AC-05: 個人識別情報が Claude API / Bedrock に送信されない"
  - "AC-06: AI_BACKEND=mock でローカル Docker 上でバッチが完走する"
task_constraints:
  max_test_cases: 12
  min_test_cases: 6
  coverage_threshold: 85
test_scope:
  exclude: "実際の API 呼び出し・パフォーマンス"
```

**作業内容**
- 個人識別情報のマスキング前処理を実装する
- `asyncio.gather` で並行処理し、API レート制限を考慮したスロットリングを実装する
- ローカルで `docker compose exec worker python -m src.python.interpretation.pipeline --date=2026-03-20` が完走することを確認してからコミットする

---

## T-06: 重みテーブル定義

```yaml
target_files:
  - "src/python/scoring/weights.py"
source_spec: "docs/trust-observation-system-v1.md#2.4"
ac_ids:
  - "AC-01: 設計書 §2.4 の重みテーブルが5次元すべてに定義されている"
  - "AC-02: recency_decay が 4段階（1.0 / 0.7 / 0.4 / 0.1）で定義されている"
  - "AC-03: 重みテーブルは外部から変更可能な構造になっている（四半期レビュー対応）"
task_constraints:
  max_test_cases: 8
  min_test_cases: 5
  coverage_threshold: 90
```

```python
# TODO(phase2): C# 移管予定 — 重みテーブルは C# ドメインサービスに移行する
```

---

## T-07: 信頼スコア算出ロジック

```yaml
target_files:
  - "src/python/scoring/calculator.py"
source_spec: "docs/trust-observation-system-v1.md#2.4"
ac_ids:
  - "AC-01: dimension_score = base_score + Σ(positive × decay) - Σ(negative × severity × decay) が正しく実装されている"
  - "AC-02: base_score = 50 でデータ不足時に回帰する"
  - "AC-03: TrustScoreSnapshot に週次スナップショットが保存される"
  - "AC-04: event_count < 20 の次元は is_reliable = False になる"
  - "AC-05: ローカル Docker 上で算出バッチが正常完走する"
task_constraints:
  max_test_cases: 12
  min_test_cases: 6
  coverage_threshold: 90
test_scope:
  exclude: "パフォーマンス"
```

```python
# TODO(phase2): C# 移管予定 — スコア算出サービスは C# ドメインサービスに移行する
```

---

## T-08: 接客タグ入力エンドポイント

```yaml
target_files:
  - "src/python/api/routers/visits.py"
source_spec: "docs/trust-observation-system-v1.md#5.1"
ac_ids:
  - "AC-01: POST /visits に来店目的・接客結果の必須入力でレコードが作成される"
  - "AC-02: 欠品離脱の場合のみ代替提案フラグを受け付ける"
  - "AC-03: 離脱の場合のみ不安点タグ（複数選択）を受け付ける"
  - "AC-04: ローカルで curl / HTTPie でエンドポイントが正常応答する"
task_constraints:
  max_test_cases: 12
  min_test_cases: 6
  coverage_threshold: 85
test_scope:
  exclude: "パフォーマンス・認証"
```

**ローカル動作確認コマンド（AC-04 の確認に使用）**

```bash
curl -X POST http://localhost:8080/visits \
  -H "Content-Type: application/json" \
  -d '{
    "store_id": "...",
    "visit_purpose": "gift",
    "contact_result": "out_of_stock_exit",
    "alternative_proposed": false
  }'
```

```python
# TODO(phase2): C# 移管予定 — REST API は ASP.NET Core Minimal API に移行する
```

---

## T-09: アンケート受信エンドポイント

```yaml
target_files:
  - "src/python/api/routers/feedback.py"
source_spec: "docs/trust-observation-system-v1.md#5.2"
ac_ids:
  - "AC-01: POST /feedback に score_consultation / score_information / score_revisit（1〜5）が保存される"
  - "AC-02: 1来店に対して Feedback は 1件のみ（UNIQUE 制約の確認）"
  - "AC-03: free_comment は任意で保存される"
  - "AC-04: Feedback 保存後に AI 解釈パイプラインへのキュー登録が行われる"
  - "AC-05: ローカルで curl / HTTPie でエンドポイントが正常応答する"
task_constraints:
  max_test_cases: 10
  min_test_cases: 5
  coverage_threshold: 85
test_scope:
  exclude: "LINE 配信連携・認証"
```

---

## T-10: スコア参照エンドポイント

```yaml
target_files:
  - "src/python/api/routers/scores.py"
source_spec: "docs/trust-observation-system-v1.md#6.1"
ac_ids:
  - "AC-01: GET /stores/{store_id}/scores に最新の TrustScoreSnapshot が返却される"
  - "AC-02: is_reliable = False の場合はレスポンスに 'unreliable' フラグが付く"
  - "AC-03: 過去 12 週分の時系列スコアを返却できる"
  - "AC-04: ローカルで curl / HTTPie でエンドポイントが正常応答する"
task_constraints:
  max_test_cases: 8
  min_test_cases: 5
  coverage_threshold: 80
```

---

## T-11: POS 日次連携バッチ

```yaml
target_files:
  - "src/python/domain/services/pos_sync.py"
source_spec: "docs/trust-observation-system-v1.md#5.3"
ac_ids:
  - "AC-01: 購入金額・商品カテゴリ・値引額・返品が日次で取得される"
  - "AC-02: 返品発生時に TrustEvent（商品信頼・ネガティブ）が自動生成される"
  - "AC-03: 冪等性が保証されている（同一日付の再実行でデータが重複しない）"
  - "AC-04: ローカル Docker 上でバッチが正常完走する（POS はモックデータで代替）"
task_constraints:
  max_test_cases: 10
  min_test_cases: 5
  coverage_threshold: 80
test_scope:
  include: "冪等性の検証"
  exclude: "実際の POS システム接続"
```

**ローカル検証用モックデータ**
- `tests/fixtures/pos_mock_data.json` に代表的な POS データを用意する
- 実 POS 接続は allowlist に追記するまで禁止

---

## T-12: TrustEvent 自動生成（ルールベース）

```yaml
target_files:
  - "src/python/domain/services/event_generator.py"
source_spec: "docs/trust-observation-system-v1.md#2.3"
ac_ids:
  - "AC-01: contact_result=欠品離脱 かつ alternative_proposed=False → 提案信頼のネガティブイベントが生成される"
  - "AC-02: score_revisit 1〜2 → 接客信頼のネガティブイベントが生成される"
  - "AC-03: score_revisit 4〜5 → 接客信頼のポジティブイベントが生成される"
  - "AC-04: 同一 source_id から重複イベントが生成されない"
task_constraints:
  max_test_cases: 12
  min_test_cases: 6
  coverage_threshold: 90
test_scope:
  include: "冪等性の検証"
```

---

## T-13: 週次レポート自動生成

```yaml
target_files:
  - "src/python/domain/services/weekly_report.py"
source_spec: "docs/trust-observation-system-v1.md#6.3"
ac_ids:
  - "AC-01: 今週増加した不満テーマ上位3件が抽出される"
  - "AC-02: 高評価接客の共通パターンが抽出される"
  - "AC-03: 欠品対応の代替提案実施率の推移が含まれる"
  - "AC-04: AI 生成の改善アクション提案が最大3件含まれる"
  - "AC-05: ローカル Docker 上でレポート生成が正常完走する"
task_constraints:
  max_test_cases: 10
  min_test_cases: 5
  coverage_threshold: 80
test_scope:
  exclude: "Slack / メール配信"
```

---

## T-14: アラート生成バッチ

```yaml
target_files:
  - "src/python/domain/services/alert_generator.py"
source_spec: "docs/trust-observation-system-v1.md#7"
ac_ids:
  - "AC-01: 接客後離脱率が前4週平均×1.5超でアラートが生成される"
  - "AC-02: 押し売り感タグが前4週平均×2.0超でアラートが生成される"
  - "AC-03: 欠品不満が3週連続増加でアラートが生成される"
  - "AC-04: 再来店意向が2週連続0.3pt以上低下でアラートが生成される"
  - "AC-05: アラートには異常検知と確認すべき観点がセットで含まれる"
  - "AC-06: ローカル Docker 上でアラート判定バッチが正常完走する"
task_constraints:
  max_test_cases: 12
  min_test_cases: 6
  coverage_threshold: 85
```

---

## T-15: コールドスタート対応

```yaml
target_files:
  - "src/python/scoring/calculator.py"
  - "src/python/api/routers/scores.py"
source_spec: "docs/trust-observation-system-v1.md#2.5"
ac_ids:
  - "AC-01: 導入〜4週目はスコア算出を行わず、event_count のみ返却される"
  - "AC-02: 5〜12週目は is_reliable = False でスコアが返却される"
  - "AC-03: 週あたりイベント数が次元ごとに20件以上で is_reliable = True になる"
task_constraints:
  max_test_cases: 8
  min_test_cases: 5
  coverage_threshold: 85
```

---

## ローカル → クラウド移行チェックリスト

以下をすべて満たしてからクラウドへデプロイすること。

- [ ] `docker compose up --build` でエラーなく全サービスが起動する
- [ ] `docker compose exec api pytest tests/python/ -v` が全件 PASS する
- [ ] `tests/python/evidence/` に最新の evidence ファイルが保存されている
- [ ] `AI_BACKEND=mock` でパイプライン全体がローカル完走する
- [ ] `AI_BACKEND=anthropic` で実 API を使った解釈が1件以上成功する
- [ ] T-08〜T-10 のエンドポイントが curl で正常応答する
- [ ] `pip-audit` でセキュリティ脆弱性がゼロである
- [ ] allowlist 外のドメインへの通信がないことを確認した

---

## Phase 2 準備タスク（Phase 1 完了・クラウド移行後に開始）

| ID | タスク名 | 内容 |
|---|---|---|
| T-P2-01 | C# プロジェクト初期構成 | `src/csharp/` に .NET 8 ソリューションを作成。`docker-compose.yml` に `csharp-api` サービスを追加 |
| T-P2-02 | SQS / Pub/Sub キュー設計 | Python ↔ C# サービス間連携の I/F 定義。ローカルは LocalStack で代替 |
| T-P2-03 | REST API 移管（C#） | T-08・T-09・T-10 を ASP.NET Core Minimal API に移植 |
| T-P2-04 | スコア算出移管（C#） | T-07 を C# ドメインサービスに移植 |
| T-P2-05 | EF Core モデル定義 | Alembic スキーマを参照して C# モデルを定義（EF Core マイグレーションは使わない） |
