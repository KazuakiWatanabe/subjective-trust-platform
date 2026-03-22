# 周辺開発タスク（Phase 1完了後 / Phase 2前）
## subjective-trust-platform

---

## 前提・作業ルール

- 作業ブランチは各タスクグループごとに分ける（下記参照）
- コミットは機能単位で細かく切る
- 各タスク完了時に `[ ]` を `[x]` に更新する
- テストが存在するタスクは、実装後に `pytest` を実行してすべて PASS を確認する
- mypy（strict モード）・ruff のチェックをパスさせる
- AI出力・解釈結果はすべて仮説として扱う設計を維持する

---

## ブランチ構成

```
main
├── docs/update-readme-phase1   ← README更新（PR作成待ち）
├── feature/monitoring          ← タスクA（監視実装）
└── feature/hq-ux-design        ← タスクB（本部UX設計ドキュメント）
```

マージ順序：`docs/update-readme-phase1` → `feature/monitoring` → `feature/hq-ux-design`

---

## タスクA：監視実装

**ブランチ**: `feature/monitoring`（作成済み・プッシュ済み）  
**参照ドキュメント**: `docs/monitoring-impl.md`  
**完了基準**: 全テスト PASS・mypy PASS・ruff PASS

---

### A-1：バッチ実行記録テーブルの追加

- [x] `git checkout feature/monitoring`
- [x] `git checkout demo/phase1 -- src/python/db/migrations/` で既存マイグレーションを取り込む
- [x] Alembicでマイグレーションファイルを新規作成する
  ```bash
  cd src/python
  alembic revision -m "add_batch_job_logs"
  ```
- [x] 生成されたファイルに以下を実装する（`docs/monitoring-impl.md` §1.1参照）
  - `batch_job_logs` テーブルの `upgrade()` / `downgrade()`
  - カラム：`log_id`, `job_name`, `store_id`, `started_at`, `finished_at`, `status`, `processed_count`, `api_cost_jpy`, `error_message`, `created_at`
  - インデックス：`idx_batch_job_logs_job_name_started`
- [x] `alembic upgrade head` を実行してテーブル作成を確認する
  ```bash
  docker compose exec db psql -U postgres -d trust_platform -c "\d batch_job_logs"
  ```

---

### A-2：既存バッチへのジョブ記録追加

- [x] `src/python/batch/` 配下のAI解釈バッチに以下を追加する（`docs/monitoring-impl.md` §1.1参照）
  - バッチ冒頭に `record_job_start(conn, "ai_interpretation_batch")`
  - バッチ末尾に `record_job_end(conn, log_id, processed_count)`
  - `api_cost_jpy` を計算してログに記録する（Claude APIのusageトークンからコスト換算）
- [x] スコア算出バッチに同様の記録処理を追加する
  - バッチ冒頭に `record_job_start(conn, "score_calculation_batch")`
  - バッチ末尾に `record_job_end(conn, log_id, processed_count)`

---

### A-3：monitoring/ ディレクトリとファイルの整備

> `feature/monitoring` ブランチにすでに17ファイルがコミット済み。  
> 既存の実装内容を `docs/monitoring-impl.md` の仕様と照合し、差分があれば修正する。

- [x] `src/python/monitoring/common.py` を確認・修正する
  - `CheckResult`, `CheckStatus` の定義
  - `get_db()` コンテキストマネージャ
  - `slack_alert(message, level, channel)` の実装
  - 環境変数：`DATABASE_URL`, `SLACK_WEBHOOK_URL`, `SLACK_CHANNEL_OPS`, `SLACK_CHANNEL_PDM`

- [x] `src/python/monitoring/checks/critical.py` を確認・修正する（`docs/monitoring-impl.md` §2参照）
  - `check_batch_duration(job_name, threshold_minutes=30)` ：前7日中央値×2倍超でアラート
  - `check_snapshot_completeness()` ：当日分Snapshotが全店舗に存在するか確認
  - `check_duplicate_trust_events()` ：同一`(source_type, source_id, trust_dimension)`の重複検知
  - `run_critical_checks(job_name)` ：上記3関数をまとめて呼び出す

- [x] `src/python/monitoring/checks/daily.py` を確認・修正する（`docs/monitoring-impl.md` §3参照）
  - `check_batch_processed_count(job_name, drop_ratio=0.5)` ：前7日平均の50%未満でアラート
  - `check_claude_api_cost()` ：前7日平均の150%超でアラート
  - `check_trust_event_by_source()` ：source_type別に3日連続ゼロを検知
  - `run_daily_checks()` ：上記3関数をまとめて呼び出す

- [x] `src/python/monitoring/checks/weekly.py` を確認・修正する（`docs/monitoring-impl.md` §4参照）
  - `check_confidence_distribution()` ：`needs_review=true`率が前4週平均の1.5倍超でアラート
  - `check_is_reliable_progress()` ：`is_reliable` の逆転（true→false）を検知
  - `check_tag_input_rate()` ：週次の接客タグ入力件数を店舗別に集計・通知
  - `check_review_queue_backlog()` ：未レビュー件数50件超・7日超過で警告
  - `run_weekly_checks()` ：上記4関数をまとめて呼び出す

- [x] `src/python/monitoring/main_daily.py` を確認する
  - Cloud Functions エントリポイント `daily_monitoring(request)` の実装

- [x] `src/python/monitoring/main_weekly.py` を確認する
  - Cloud Functions エントリポイント `weekly_monitoring(request)` の実装

---

### A-4：既存バッチへのcritical checks組み込み

- [x] AI解釈バッチ末尾に `run_critical_checks("ai_interpretation_batch")` を追加する
- [x] スコア算出バッチ末尾に `run_critical_checks("score_calculation_batch")` を追加する

```python
# 追加例（バッチ末尾）
from src.python.monitoring.checks.critical import run_critical_checks
record_job_end(conn, log_id, processed_count)
run_critical_checks("score_calculation_batch")
```

---

### A-5：テストの確認と補完

- [x] `tests/python/monitoring/test_critical.py` の6テストがすべてPASSすることを確認する
- [x] `tests/python/monitoring/test_daily.py` の7テストがすべてPASSすることを確認する
- [x] `tests/python/monitoring/test_weekly.py` の8テストがすべてPASSすることを確認する
- [x] A-2・A-4で追加したバッチ変更に対するテストが不足していれば追加する
- [x] `pytest tests/python/monitoring/ -v` を実行してすべてPASSを確認する

---

### A-6：pyproject.tomlの確認

- [x] `requests>=2.31.0` が依存に追加されていることを確認する
- [x] `functions-framework` が依存に追加されていることを確認する（Cloud Functionsデプロイ用）

---

### A-7：ドキュメントのコミット

- [x] `docs/monitoring-impl.md` を `feature/monitoring` ブランチにコミットする
  ```bash
  git add docs/monitoring-impl.md
  git commit -m "docs: add monitoring implementation guide"
  git push
  ```

---

### A-8：最終確認とPR準備

- [x] `pytest` 全体（165テスト）がPASSすることを確認する
- [x] `mypy src/python/monitoring/ --strict` がPASSすることを確認する
- [x] `ruff check src/python/monitoring/` がPASSすることを確認する
- [x] PRの説明に以下を記載する
  - 追加した監視項目の一覧（🔴即時3件・🟡日次3件・🟢週次4件）
  - `batch_job_logs` テーブルの追加
  - 既存バッチへの影響範囲（record_job_start/end・run_critical_checksの追加）

---

## タスクB：本部分析画面 UX設計ドキュメント

**ブランチ**: `feature/hq-ux-design`（新規作成）  
**参照ドキュメント**: `docs/hq-analysis-ux-v1.md`  
**完了基準**: ドキュメントのコミット・プッシュ完了

---

### B-1：ブランチ作成とドキュメント追加

- [ ] `feature/hq-ux-design` ブランチを `main` から作成する
  ```bash
  git checkout main
  git checkout -b feature/hq-ux-design
  ```
- [ ] `docs/hq-analysis-ux-v1.md` を追加してコミットする
  ```bash
  git add docs/hq-analysis-ux-v1.md
  git commit -m "docs: add HQ analysis screen UX spec v1"
  git push -u origin feature/hq-ux-design
  ```

---

### B-2：README への反映

`docs/update-readme-phase1` ブランチのREADMEのドキュメント構成表に以下を追記する。

> 注：`docs/update-readme-phase1` のPRがマージされた後に行う。

- [ ] `docs/update-readme-phase1` をチェックアウトする
- [ ] READMEの「ドキュメント構成」セクションに以下を追加する

```markdown
│   ├── monitoring-impl.md            ← 監視実装ガイド（Phase 1周辺開発）
│   └── hq-analysis-ux-v1.md          ← 本部分析画面UX設計仕様書（Phase 2準備）
```

- [ ] ドキュメント対応表に以下を追加する

| ドキュメント | 読者 | 目的 |
|---|---|---|
| 監視実装ガイド | 開発チーム | Phase 1の監視設計・実装手順・閾値定義 |
| 本部分析画面UX設計仕様書 | 開発チーム・PdM | Phase 2の本部分析3画面の設計仕様・API定義 |

- [ ] コミット・プッシュする
  ```bash
  git commit -m "docs: add monitoring-impl and hq-ux-spec to document index"
  git push
  ```

---

## タスクC：Cloud Scheduler / Cloud Functions デプロイ設定

**ブランチ**: `feature/monitoring`  
**参照ドキュメント**: `docs/monitoring-impl.md` §6・§7  
**完了基準**: ステージング環境で動作確認済み

> Phase 2前に本番環境に適用する。タスクAのPRマージ後に着手する。

- [ ] Secret Managerに環境変数を登録する（`docs/monitoring-impl.md` §1.3参照）
  - `trust-db-url`
  - `trust-slack-hook`
- [ ] `daily_monitoring` をCloud Functionsにデプロイする（§8参照）
- [ ] `weekly_monitoring` をCloud Functionsにデプロイする（§8参照）
- [ ] Cloud Schedulerを設定する（§6参照）
  - 日次：毎朝08:30
  - 週次：毎週月曜08:00（Asia/Tokyo）
- [ ] Cloud Monitoringのネイティブアラートを設定する（§7参照）
  - Cloud Functionsのエラーレート5%超アラート
- [ ] ステージング環境で手動トリガーして動作確認する
  ```bash
  gcloud scheduler jobs run trust-daily-monitoring --location=asia-northeast1
  ```
- [ ] Slackの `#trust-platform-alerts` チャンネルに通知が届くことを確認する

---

## タスクD：Google口コミ連携

**ブランチ**: `feature/google-review`（作成済み・プッシュ済み）  
**参照ドキュメント**: `docs/google-review-integration-v1.md`  
**完了基準**: 全テスト PASS・mypy PASS・ruff PASS・1店舗での動作確認済み

---

### D-1：マイグレーション

- [x] `feature/google-review` をチェックアウトする
  ```bash
  git checkout feature/google-review
  ```
- [x] Alembicでマイグレーションファイルを新規作成する
  ```bash
  cd src/python
  alembic revision -m "add_review_external_columns"
  ```
- [x] 生成されたファイルに以下を実装する（`docs/google-review-integration-v1.md` §3.1参照）
  - `google_review_id VARCHAR(255) UNIQUE`
  - `processed_flag BOOLEAN NOT NULL DEFAULT false`
  - `processed_at TIMESTAMPTZ`
  - インデックス：`idx_review_external_processed (processed_flag, store_id)`
- [x] `alembic upgrade head` を実行してカラム追加を確認する
  ```bash
  docker compose exec db psql -U postgres -d trust_platform \
    -c "\d review_external"
  ```

---

### D-2：PIIマスキングモジュールの拡張

既存の `src/python/utils/pii_masker.py` に外部レビュー向けマスキングを追加する。（`docs/google-review-integration-v1.md` §5参照）

- [x] `mask_review_text(text: str) -> str` 関数を追加する
  - スタッフ氏名パターン（ひらがな・カタカナ）→ 「スタッフ」に置換
  - 電話番号パターン → 「[電話番号]」に置換
- [x] `reviewer_name` は保存しない方針を実装に反映する（保存時に「（匿名）」固定）
- [x] 既存のマスキングテストが引き続きPASSすることを確認する
- [x] `mask_review_text` の単体テストを `tests/python/utils/test_pii_masker.py` に追加する
  - スタッフ氏名が含まれるケース
  - 電話番号が含まれるケース
  - 両方含まれるケース
  - マスキング対象がないケース（変化なし）

---

### D-3：専用プロンプトの実装

- [x] `src/python/ai/prompts/review_interpretation.py` を新規作成する（`docs/google-review-integration-v1.md` §6.2参照）
  - `EXTERNAL_REVIEW_PROMPT_TEMPLATE` の定義
  - `PROMPT_VERSION` の設定（既存のバージョン管理に準拠）
- [x] プロンプトの出力スキーマを確認する
  - `mentions` 配列（複数次元対応）
  - `subjective_hints`（trait_signal / state_signal / meta_signal）
  - `overall_sentiment`
  - `review_type`（single_visit / multi_visit / comparison / unknown）
  - `contains_competitor_mention`
- [x] `tests/python/ai/test_review_prompt.py` を新規作成する
  - Mockクライアントを使ったプロンプト出力の単体テスト
  - 複数次元が混在するレビューで `mentions` が複数生成されるケース
  - 星と本文の感情が乖離するケース（星3・本文ネガティブ等）
  - 競合比較を含むレビューで `contains_competitor_mention=true` になるケース
  - レビュー本文が空のケース

---

### D-4：TrustEvent生成ロジックの実装

- [x] `src/python/batch/review_interpreter.py` に `mentions_to_trust_events()` を実装する（`docs/google-review-integration-v1.md` §6.4参照）
  - `mentions` 配列の各要素を1件の `TrustEvent` として生成する
  - `source_type='review'`・`source_id=review.review_id` を設定する
  - `trait_signal` / `state_signal` / `meta_signal` を `subjective_hints` から設定する
  - `confidence < 0.6` の場合 `needs_review=true` を設定する
  - `detected_at` は `review.review_date` を使用する

---

### D-5：Google口コミ取得バッチの実装

`src/python/batch/review_fetcher.py` を新規作成する。（`docs/google-review-integration-v1.md` §4・§7.2参照）

- [x] OAuth 2.0 サービスアカウント認証を実装する
  - `google-auth` / `google-api-python-client` を `pyproject.toml` に追加する
  - 認証情報は環境変数 `GOOGLE_SERVICE_ACCOUNT_KEY_PATH` から取得する
- [x] `fetch_new_reviews(location_name, since)` を実装する
  - `pageSize=50` でページネーション対応
  - `updateTime > since` の差分取得
  - `since` は `batch_job_logs` の前回成功日時から取得する（なければ前日）
- [x] `run_review_fetch_batch(store_id, location_name)` を実装する
  - バッチ冒頭に `record_job_start(conn, "review_fetch_batch")`
  - `google_review_id` による重複チェック
  - `mask_review_text()` によるPIIマスキング
  - `reviewer_name` は「（匿名）」固定で保存
  - バッチ末尾に `record_job_end()` と `run_critical_checks("review_fetch_batch")`
- [x] エラーハンドリングを実装する（`docs/google-review-integration-v1.md` §8参照）
  - Google API認証エラー：即時失敗・Slackアラート
  - クォータ超過：翌日リトライ（差分取得のため重複なし）
  - レビュー本文が空：スキップ（`processed_flag=true` で保存）
- [x] `tests/python/batch/test_review_fetcher.py` を新規作成する
  - Google APIのレスポンスをモックした取得テスト
  - 重複チェック（同一 `google_review_id` を2回処理しないこと）
  - PIIマスキングが適用されること
  - `batch_job_logs` に記録されること

---

### D-6：Google口コミ解釈バッチの実装

`src/python/batch/review_interpreter.py` を新規作成する。（`docs/google-review-integration-v1.md` §7.3・§8参照）

- [x] `get_unprocessed_reviews(store_id)` を実装する
  - `processed_flag=false` のレコードを取得する
- [x] `run_review_interpret_batch(store_id)` を実装する
  - バッチ冒頭に `record_job_start(conn, "review_interpret_batch")`
  - `EXTERNAL_REVIEW_PROMPT_TEMPLATE` を使ってプロンプトを生成する
  - 既存の抽象クライアント（`get_ai_client()`）経由でBedrock Claudeを呼び出す
  - `mentions_to_trust_events()` でTrustEventを生成・保存する
  - `mark_review_processed()` で `processed_flag=true` / `processed_at=NOW()` を更新する
  - スロットリング：`await asyncio.sleep(0.5)`（既存バッチに準拠）
  - バッチ末尾に `record_job_end()` と `run_critical_checks("review_interpret_batch")`
- [x] Bedrockリトライを実装する（`docs/google-review-integration-v1.md` §8.2参照）
  - `tenacity` を `pyproject.toml` に追加する
  - 最大3回・指数バックオフ（min=2s / max=10s）
  - `ClientError`（ThrottlingException等）をリトライ対象にする
- [x] JSON解析エラー時の処理を実装する
  - `needs_review=true` で保存し、手動レビューキューに入れる
- [x] `tests/python/batch/test_review_interpreter.py` を新規作成する
  - Mockクライアントを使った解釈テスト
  - 1件のレビューから複数のTrustEventが生成されるケース
  - `processed_flag` が `true` に更新されること
  - Bedrock APIエラー時に `needs_review=true` になること
  - JSON解析エラー時に `needs_review=true` になること

---

### D-7：環境変数・設定の追加

- [x] `src/python/core/settings.py`（または設定ファイル）に以下を追加する
  ```python
  GOOGLE_SERVICE_ACCOUNT_KEY_PATH: str = ""
  GOOGLE_LOCATION_IDS: dict[str, str] = {}
    # キー: store_id、値: "accounts/{id}/locations/{id}"
  ```
- [x] `.env.example` に以下を追記する
  ```bash
  GOOGLE_SERVICE_ACCOUNT_KEY_PATH=
  GOOGLE_LOCATION_ID_STORE_A=
  ```
- [x] `docker-compose.yml` の worker サービスに環境変数を追加する

---

### D-8：API接続確認スクリプトの作成

- [x] `scripts/test_google_api.py` を新規作成する（`docs/google-review-integration-v1.md` §11 Step 1参照）
  ```python
  # 実行方法:
  # python scripts/test_google_api.py --store-id <STORE_A_ID>
  # → レビュー一覧の取得件数とクォータ消費量を出力する
  ```

---

### D-9：1店舗テストの実施

> **前提**: `GOOGLE_SERVICE_ACCOUNT_KEY_PATH` と `GOOGLE_LOCATION_ID_STORE_A` が設定済みであること

- [ ] Step 1：API接続確認
  ```bash
  python scripts/test_google_api.py --store-id <STORE_A_ID>
  ```
  確認事項：レビュー一覧が取得できること・クォータ消費量を記録すること

- [ ] Step 2：取得バッチの単体実行
  ```bash
  docker compose exec worker python -m batch.review_fetcher --store-id <STORE_A_ID>
  ```
  確認事項：`review_external` にレコードが挿入されること・2回実行しても件数が変わらないこと

- [ ] Step 3：解釈バッチの単体実行
  ```bash
  docker compose exec worker python -m batch.review_interpreter --store-id <STORE_A_ID>
  ```
  確認事項：`trust_events` に `source_type='review'` のレコードが生成されること・1レビューから複数TrustEventが生成されるケースを確認すること

- [ ] Step 4：精度確認（20件サンプリング）
  - `docs/google-review-integration-v1.md` §9.1のサンプリングクエリを実行する
  - `trust_dimension` 正答率85%以上を確認する
  - `needs_review=true` の割合が40%超の場合はプロンプトを修正して再実行する

- [ ] Step 5：監視との統合確認
  ```bash
  docker compose exec worker python -m monitoring.checks.critical
  docker compose exec worker python -m monitoring.checks.daily
  ```
  確認事項：`source_type='review'` のゼロ検知が正常に動くこと

---

### D-10：テストの最終確認とPR準備

- [x] `pytest tests/python/batch/test_review_fetcher.py -v` が PASS すること
- [x] `pytest tests/python/batch/test_review_interpreter.py -v` が PASS すること
- [x] `pytest tests/python/ai/test_review_prompt.py -v` が PASS すること
- [x] `pytest` 全体が PASS すること
- [x] `mypy src/python/batch/review_fetcher.py src/python/batch/review_interpreter.py --strict` が PASS すること
- [x] `ruff check src/python/batch/review_fetcher.py src/python/batch/review_interpreter.py` が PASS すること
- [x] PRの説明に以下を記載する
  - 追加したバッチ：`review_fetcher` / `review_interpreter`
  - 追加したマイグレーション：`add_review_external_columns`
  - 専用プロンプト：`review_interpretation.py`（既存プロンプトとの差分を記載）
  - 1店舗テストの結果（精度・クォータ消費量）

---

## 完了チェックリスト

### Phase 2開始前に揃っている状態

- [x] `feature/monitoring` がmainにマージ済み
- [x] `feature/hq-ux-design` がmainにマージ済み
- [x] `docs/update-readme-phase1` がmainにマージ済み
- [x] Cloud Scheduler・Cloud Functionsがステージングで動作確認済み
- [x] `batch_job_logs` テーブルが本番DBに適用済み
- [x] Slack通知が `#trust-platform-alerts`・`#trust-platform-weekly` に届くことを確認済み
- [x] 本部分析画面の設計仕様書（`docs/hq-analysis-ux-v1.md`）がmainに存在する

---

## 初期閾値の見直しスケジュール

監視開始後、以下のタイミングで閾値を見直す。

| 項目 | 初期閾値 | 見直しタイミング |
|---|---|---|
| バッチ処理時間 | 中央値×2倍 or 30分上限 | 運用4週後 |
| 処理件数減少 | 前7日平均の50%未満 | 運用4週後 |
| 要レビュー率 | 前4週平均の1.5倍 | 運用8週後（4週分の平均が溜まってから） |
| レビューキュー | 50件超 | 運用4週後 |
| 接客タグ入力件数下限 | 10件/週/店舗 | 運用4週後 |
