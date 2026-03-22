# POSデータ連携タスク
## subjective-trust-platform / Phase 1 周辺開発（Phase 2 前）

---

## 作業開始前の必須確認事項

**以下を順番に確認してから作業を開始すること。確認なしの作業着手は禁止。**

- [ ] `AGENTS.md` を全セクション読んだ（最上位ルール）
- [ ] `CLAUDE.md` を全セクション読んだ（実装ガイド）
- [ ] 現在 **Phase 1** であることを確認した（`src/csharp/` への書き込み禁止）
- [ ] `auto-accept モード` がオフであることを確認した（AGENTS.md 禁止事項）
- [ ] 対象タスクの `source_spec` を設計書 v1 で確認した
- [ ] 新規 `import` を追加する場合、`pyproject.toml` 記載済みか確認した
- [ ] 外部通信先が `AGENTS.md` の allowlist 内であることを確認した

---

## 作業ブランチ

```bash
git checkout main
git checkout -b feature/pos-integration
```

---

## 前提・作業ルール

- コミットは機能単位で細かく切る
- 各タスク完了時に `[ ]` を `[x]` に更新する
- テスト実装は **テストファースト**（RED → GREEN の順序を守る）
- テストの削除・スキップによる PASS は禁止（AGENTS.md 禁止事項）
- `mypy --strict` / `ruff check` / `ruff format` をコミット前に必ず実行する
- タスク完了の定義：**pytest 全件 PASS** かつ **evidence ファイルが保存されている** こと
- AI解釈結果は確定事実として扱わない（`generated_by = "ai"` 必須）
- PII（個人識別情報）を Claude API / Bedrock に送信しない（AGENTS.md §セキュリティ）

---

## 設計根拠

| 設計書 v1 セクション | 対応タスク |
|---|---|
| §5.3 自動連携（POS日次バッチ） | P-1, P-2 |
| §4.3 Purchase テーブル定義 | P-1 |
| §2.3 信頼イベントモデル（自動生成経路） | P-3 |
| §2.4 信頼スコア算出ロジック | P-3（重みテーブル参照） |
| §8.2 スタッフデータ | P-3（個人特定集計の禁止） |

---

## P-1：マイグレーション（Purchase テーブル拡張）

**参照**: `docs/trust-observation-system-v1.md` §4.3  
**完了基準**: マイグレーション適用済み・downgrade で元に戻せること

### P-1-1：マイグレーションファイルの作成

- [ ] Alembic でマイグレーションファイルを新規作成する
  ```bash
  cd src/python
  alembic revision -m "add_purchase_return_columns"
  ```
- [ ] 生成されたファイルに以下を実装する
  ```python
  # upgrade()
  # 設計書 v1 §4.3 の指定カラムを追加する
  op.add_column("purchase",
      sa.Column("return_flag", sa.Boolean(), nullable=False, server_default="false"))
  op.add_column("purchase",
      sa.Column("return_reason_category", sa.String(50), nullable=True))
      # 品質問題 / サイズ不一致 / 説明との相違 / 気が変わった / その他
  op.add_column("purchase",
      sa.Column("return_date", sa.Date(), nullable=True))

  # downgrade() も必ず実装する
  ```
- [ ] `alembic upgrade head` を実行してカラム追加を確認する
  ```bash
  docker compose exec db psql -U trust_user -d trust_platform \
    -c "\d purchase"
  ```
- [ ] `alembic downgrade -1` → `alembic upgrade head` で冪等性を確認する

---

## P-2：POS日次バッチの実装

**参照**: `docs/trust-observation-system-v1.md` §5.3  
**完了基準**: テスト PASS・冪等性確認済み・evidence 保存済み

### P-2-1：テスト設定の明示（作業開始前に記入）

```yaml
target_files:
  - src/python/batch/pos_sync.py
target_functions:
  - normalize_pos_record
  - run_pos_sync_batch
test_scope:
  include:
    - 正常系：POS レコードの正規化・Purchase テーブルへの保存
    - 冪等性：同一レコードを2回処理しても重複しないこと
    - 返品フラグ：return_flag=true の場合に return_reason_category が設定されること
    - 異常系：不正データ・必須カラム欠落時のスキップ処理
  exclude:
    - 実際の POS システムへの接続テスト（モック使用）
source_spec: docs/trust-observation-system-v1.md#5.3
ac_ids:
  - AC-POS-01: POS レコードが正規化されて Purchase テーブルに保存される
  - AC-POS-02: 同一 POS レコードを2回処理しても重複が発生しない（冪等性）
  - AC-POS-03: return_flag=true のレコードに return_reason_category が設定される
  - AC-POS-04: 不正データはスキップされ、バッチ全体は継続する
coverage_threshold: 90
task_constraints:
  max_test_cases: 12
  min_test_cases: 5
```

### P-2-2：テストの実装（RED フェーズ）

- [ ] `tests/python/batch/test_pos_sync.py` を新規作成する
  - テストファーストで実装する（この時点では実装ファイルは存在しない）
  - 各テストケースに `ac_ids` の ID をコメントで明記する
    ```python
    # AC-POS-01: POS レコードが正規化されて Purchase テーブルに保存される
    def test_正常なPOSレコードが正規化される():
        ...
    ```
  - 確認すべきテストケース：
    - 正常なPOSレコードの正規化（purchase_id, store_id, customer_id, amount 等）
    - 同一レコードの2回処理（冪等性 / AC-POS-02）
    - return_flag=true のレコード処理（AC-POS-03）
    - customer_id が NULL（匿名来店）のレコード処理
    - 不正データのスキップ（AC-POS-04）
    - `batch_job_logs` への記録
- [ ] `pytest tests/python/batch/test_pos_sync.py -v` を実行し、**FAIL** することを確認する（RED）

### P-2-3：バッチ本体の実装（GREEN フェーズ）

- [ ] `src/python/batch/pos_sync.py` を新規作成する

  **実装する関数：**

  ```python
  # TODO(phase2): C# 移管予定 — POS 連携バッチ（業務ロジック部分）

  def normalize_pos_record(
      raw: dict[str, Any],
      store_id: uuid.UUID,
  ) -> dict[str, Any] | None:
      """POS生データを Purchase テーブル形式に正規化する。

      Args:
          raw: POS システムから取得した生データ
          store_id: 店舗ID

      Returns:
          正規化済み辞書。不正データの場合は None を返しスキップする。

      Note:
          customer_id が NULL の場合（匿名来店）はそのまま NULL で保存する。
          スタッフ個人を特定できる集計は行わない（設計書 §8.2）。
      """
      ...

  async def run_pos_sync_batch(
      raw_records: list[dict[str, Any]],
      store_id: uuid.UUID,
      existing_pos_ids: set[str],
  ) -> tuple[list[dict[str, Any]], int]:
      """POS日次バッチ。正規化・重複チェック・保存を行う。

      Args:
          raw_records: POS から取得した生レコードリスト
          store_id: 店舗ID
          existing_pos_ids: DB 保存済みの pos_transaction_id セット（冪等性保証）

      Returns:
          (保存済みレコードリスト, スキップ件数)

      Note:
          batch_job_logs に record_job_start / record_job_end を記録する。
          バッチ末尾で run_critical_checks("pos_sync_batch") を呼び出す。
      """
      ...
  ```

  **実装時の制約：**
  - `record_job_start` / `record_job_end` を冒頭・末尾に追加する（`docs/monitoring-impl.md` §1.1参照）
  - バッチ末尾で `run_critical_checks("pos_sync_batch")` を呼び出す
  - スタッフ個人を特定できる集計クエリを書かない（AGENTS.md 禁止事項・設計書 §8.2）
  - `pos_transaction_id`（POS側の一意キー）で重複チェックを行い冪等性を保証する
  - Phase 2 移管予定のコンポーネントに `# TODO(phase2)` コメントを付ける

- [ ] `pytest tests/python/batch/test_pos_sync.py -v` を実行し、**PASS** することを確認する（GREEN）

### P-2-4：自己検証ステップ（AGENTS.md 規定）

- [ ] Step 1：テストが PASS であることを確認する
- [ ] Step 2：`normalize_pos_record` のロジックを意図的に壊し、テストが FAIL になることを確認する
- [ ] Step 3：壊した実装を元に戻し、再度 PASS になることを確認する
- [ ] Step 4：Step 2 で FAIL にならなかったテストがあれば見直して修正する

### P-2-5：セキュリティチェック

- [ ] 新規パッケージを追加した場合、`AGENTS.md` のセキュリティチェック手順を実施する
  ```bash
  pip-audit > tests/python/evidence/security_audit.txt
  ```
- [ ] 外部通信が発生する場合、送信先が `AGENTS.md` allowlist 内であることを確認する
- [ ] `os.environ` の値を外部URLに送信していないことを確認する

---

## P-3：POSデータからの TrustEvent 自動生成

**参照**: `docs/trust-observation-system-v1.md` §2.3（自動生成経路）  
**完了基準**: テスト PASS・`generated_by = "ai"` または `"rule"` が設定されている・evidence 保存済み

### P-3-1：テスト設定の明示（作業開始前に記入）

```yaml
target_files:
  - src/python/batch/pos_event_generator.py
target_functions:
  - generate_trust_events_from_purchase
  - detect_return_trust_event
test_scope:
  include:
    - 返品発生 → 商品信頼のネガティブイベント生成
    - 返品理由カテゴリ別の severity 設定
    - 匿名来店（customer_id=NULL）での処理
    - generated_by = "rule" が設定されること
    - confidence = 1.0（ルールベースは確信度最大）が設定されること
  exclude:
    - AI解釈を伴うイベント生成（別バッチの責務）
    - 再来店間隔の異常延長検知（Phase 2 以降）
source_spec: docs/trust-observation-system-v1.md#2.3
ac_ids:
  - AC-EVT-01: 返品発生で商品信頼のネガティブ TrustEvent が生成される
  - AC-EVT-02: 返品理由カテゴリが severity に正しくマッピングされる
  - AC-EVT-03: generated_by = "rule" / confidence = 1.0 が設定される
  - AC-EVT-04: confidence チェックは不要だが needs_review = False が設定される
coverage_threshold: 90
task_constraints:
  max_test_cases: 12
  min_test_cases: 5
```

### P-3-2：テストの実装（RED フェーズ）

- [ ] `tests/python/batch/test_pos_event_generator.py` を新規作成する
  - 各テストに `ac_ids` の ID をコメントで明記する
  - 確認すべきテストケース：
    - 返品レコードから商品信頼ネガティブイベントが生成される（AC-EVT-01）
    - 返品理由カテゴリ別の severity マッピング（AC-EVT-02）
      - 品質問題 → severity=3
      - 説明との相違 → severity=2
      - その他 → severity=1
    - `generated_by = "rule"` の設定（AC-EVT-03）
    - `confidence = 1.0` の設定（AC-EVT-03）
    - `needs_review = False` の設定（AC-EVT-04）
    - 匿名来店（customer_id=NULL）でもイベントが生成される
    - return_flag=false のレコードではイベントが生成されない
- [ ] `pytest tests/python/batch/test_pos_event_generator.py -v` を実行し、**FAIL** することを確認する（RED）

### P-3-3：イベント生成ロジックの実装（GREEN フェーズ）

- [ ] `src/python/batch/pos_event_generator.py` を新規作成する

  **実装する関数：**

  ```python
  # 返品理由 → severity マッピング（設計書 §2.4 重みテーブルに準拠）
  _RETURN_REASON_SEVERITY: dict[str, int] = {
      "品質問題": 3,
      "説明との相違": 2,
      "サイズ不一致": 2,
      "気が変わった": 1,
      "その他": 1,
  }

  def detect_return_trust_event(
      purchase: dict[str, Any],
  ) -> dict[str, Any] | None:
      """返品発生から商品信頼の TrustEvent を生成する。

      Args:
          purchase: Purchase テーブルのレコード辞書

      Returns:
          TrustEvent 辞書。返品でない場合は None。

      Note:
          ルールベース生成のため generated_by = "rule"、
          confidence = 1.0、needs_review = False を設定する。
          AI解釈結果ではないため confidence チェックは不要だが、
          確定事実として扱わないためのフラグは統一して設定する。
      """
      ...

  def generate_trust_events_from_purchase(
      purchases: list[dict[str, Any]],
  ) -> list[dict[str, Any]]:
      """Purchase レコード群から TrustEvent リストを生成する。

      Args:
          purchases: Purchase レコードリスト

      Returns:
          生成された TrustEvent 辞書のリスト
      """
      ...
  ```

  **実装時の制約：**
  - `generated_by = "rule"` を必ず設定する（AI生成との区別）
  - `confidence = 1.0` を設定する（ルールベースは確信度最大）
  - `needs_review = False` を設定する（ルールベースは人間レビュー不要）
  - スタッフ個人を特定できる集計を含めない（AGENTS.md 禁止事項）
  - AI解釈を伴う処理は含めない（別バッチの責務）

- [ ] `pytest tests/python/batch/test_pos_event_generator.py -v` を実行し、**PASS** することを確認する（GREEN）

### P-3-4：自己検証ステップ（AGENTS.md 規定）

- [ ] Step 1：テストが PASS であることを確認する
- [ ] Step 2：`_RETURN_REASON_SEVERITY` マッピングを意図的に壊し、severity テストが FAIL になることを確認する
- [ ] Step 3：壊した実装を元に戻し、再度 PASS になることを確認する
- [ ] Step 4：Step 2 で FAIL にならなかったテストがあれば見直して修正する

---

## P-4：全体テスト・品質チェック・エビデンス保存

**完了基準**: 全テスト PASS・mypy PASS・ruff PASS・evidence 保存済み

### P-4-1：全体テストの実行

- [ ] ユニットテストを実行してすべて PASS することを確認する
  ```bash
  pytest tests/python/unit/ -v > tests/python/evidence/unit_result.txt
  ```
- [ ] 統合テストを実行してすべて PASS することを確認する
  ```bash
  pytest tests/python/integration/ -v > tests/python/evidence/integration_result.txt
  ```
- [ ] 全体テストで既存テストが壊れていないことを確認する
  ```bash
  pytest tests/python/ --tb=short -q
  ```

### P-4-2：型チェック・フォーマット

- [ ] `mypy --strict src/python/batch/pos_sync.py src/python/batch/pos_event_generator.py` が PASS すること
- [ ] `ruff check src/python/batch/pos_sync.py src/python/batch/pos_event_generator.py` が PASS すること
- [ ] `ruff format src/python/batch/pos_sync.py src/python/batch/pos_event_generator.py` を実行する

### P-4-3：セキュリティ監査

- [ ] パッケージ追加・変更がある場合は security_audit を更新する
  ```bash
  pip-audit > tests/python/evidence/security_audit.txt
  ```

### P-4-4：evidence ファイルの確認

- [ ] `tests/python/evidence/unit_result.txt` が保存されていること
- [ ] `tests/python/evidence/integration_result.txt` が保存されていること
- [ ] evidence ファイルをコミットに含める（AGENTS.md 規定）

---

## P-5：PR 作成

- [ ] 変更内容をコミットする
  ```bash
  git add -A
  git commit -m "feat: implement POS daily sync batch and TrustEvent auto-generation (Task P)"
  git push -u origin feature/pos-integration
  ```
- [ ] PR を作成する
  ```bash
  gh pr create \
    --base main \
    --head feature/pos-integration \
    --title "feat: POS integration - daily sync batch and TrustEvent generation" \
    --body "$(cat <<'EOF'
  ## 概要
  POS日次バッチ連携とTrustEvent自動生成を実装。

  ## 追加内容
  - Alembicマイグレーション：Purchase テーブルに return_flag / return_reason_category / return_date を追加
  - src/python/batch/pos_sync.py：POS日次同期バッチ（冪等性保証）
  - src/python/batch/pos_event_generator.py：返品イベントからの TrustEvent 自動生成（ルールベース）

  ## テスト
  - tests/python/batch/test_pos_sync.py
  - tests/python/batch/test_pos_event_generator.py

  ## 設計根拠
  - 設計書 v1 §5.3（POS日次バッチ連携）
  - 設計書 v1 §2.3（TrustEvent 自動生成経路）
  - 設計書 v1 §4.3（Purchase テーブル定義）

  ## AGENTS.md 準拠確認
  - [x] auto-accept モードオフで作業
  - [x] テストファースト（RED → GREEN）
  - [x] 自己検証ステップ実施済み
  - [x] セキュリティチェック実施済み
  - [x] evidence ファイル保存済み
  - [x] src/csharp/ への書き込みなし
  - [x] スタッフ個人特定クエリなし
  - [x] PII を外部 API に送信していない
  EOF
  )"
  ```
- [ ] PR の説明に evidence ファイルのパスを記載する

---

## Phase 2 移管予定コンポーネントの記録

以下のコンポーネントには `# TODO(phase2)` コメントを付けること。

| コンポーネント | TODO コメント |
|---|---|
| `pos_sync.py` の業務ロジック部分 | `# TODO(phase2): C# 移管予定 — POS 連携バッチ（業務ロジック）` |
| Purchase テーブルの CRUD | `# TODO(phase2): C# 移管予定 — Purchase リポジトリ` |

---

## 今回のスコープ外（Phase 2 以降）

以下は設計書 v1 §2.3 に記載されているが、Phase 1 周辺開発のスコープ外とする。

- 再来店間隔の異常延長検知（会員データとのジョイン分析が必要）
- 特定カテゴリの購買率急落検知（複数週分のデータ蓄積後に実装）
- POS と EC の統合分析（Phase 2 の EC 連携後）
