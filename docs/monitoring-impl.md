# 監視実装ガイド v1
## subjective-trust-platform / Phase 1

---

## 0. 全体構成

```
monitoring/
├── common.py              # 共通ユーティリティ（DB接続・Slack通知）
├── checks/
│   ├── critical.py        # 🔴 即時アラート（②⑥⑫）
│   ├── daily.py           # 🟡 日次チェック（①④⑤）
│   └── weekly.py          # 🟢 週次チェック（③⑦⑧⑨⑩⑪）
├── main_critical.py       # Cloud Functions エントリポイント（即時）
├── main_daily.py          # Cloud Functions エントリポイント（日次）
├── main_weekly.py         # Cloud Functions エントリポイント（週次）
└── migrations/
    └── add_batch_job_logs.sql  # バッチ実行記録テーブル
```

**通知フロー**

```
Cloud Scheduler
  → Cloud Functions（monitoring）
    → PostgreSQL（チェッククエリ）
      → 異常検知 → Slack Webhook → #trust-platform-alerts
```

---

## 1. 事前準備

### 1.1 バッチ実行記録テーブルの追加

既存の設計書v1テーブルに以下を追加します。

```sql
-- migrations/add_batch_job_logs.sql

CREATE TABLE batch_job_logs (
    log_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_name        VARCHAR(100) NOT NULL,
    store_id        UUID REFERENCES stores(store_id),  -- NULL=全店舗対象
    started_at      TIMESTAMPTZ NOT NULL,
    finished_at     TIMESTAMPTZ,
    status          VARCHAR(20) NOT NULL DEFAULT 'running',
      -- running / completed / failed
    processed_count INTEGER DEFAULT 0,
    error_message   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_batch_job_logs_job_name_started
    ON batch_job_logs(job_name, started_at DESC);
```

**既存のAI解釈バッチ・スコア算出バッチに、開始・終了の記録を追加します。**

```python
# 既存バッチの冒頭に追加
def record_job_start(conn, job_name: str) -> str:
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO batch_job_logs (job_name, started_at, status)
            VALUES (%s, NOW(), 'running')
            RETURNING log_id
        """, (job_name,))
        return str(cur.fetchone()[0])

# 既存バッチの末尾に追加
def record_job_end(conn, log_id: str, processed_count: int, error: str = None):
    status = 'failed' if error else 'completed'
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE batch_job_logs
            SET finished_at = NOW(),
                status = %s,
                processed_count = %s,
                error_message = %s
            WHERE log_id = %s
        """, (status, processed_count, error, log_id))
```

### 1.2 共通ユーティリティ

```python
# monitoring/common.py

import os
import logging
from contextlib import contextmanager
from typing import Optional
import psycopg2
from psycopg2.extras import RealDictCursor
import requests

logger = logging.getLogger(__name__)

# 環境変数（Cloud Functions の Secret Manager 経由で設定）
DATABASE_URL       = os.environ["DATABASE_URL"]
SLACK_WEBHOOK_URL  = os.environ["SLACK_WEBHOOK_URL"]
SLACK_CHANNEL_OPS  = os.environ.get("SLACK_CHANNEL_OPS",  "#trust-platform-alerts")
SLACK_CHANNEL_PDM  = os.environ.get("SLACK_CHANNEL_PDM",  "#trust-platform-weekly")


@contextmanager
def get_db():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def slack_alert(message: str, level: str = "warning", channel: str = None):
    """
    level: "critical" | "warning" | "info"
    """
    emoji   = {"critical": "🔴", "warning": "🟡", "info": "🟢"}.get(level, "⚪")
    target  = channel or SLACK_CHANNEL_OPS
    payload = {"text": f"{emoji} *[Trust Platform]* {message}"}
    try:
        r = requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=5)
        r.raise_for_status()
    except Exception as e:
        logger.error(f"Slack通知失敗: {e}")
```

### 1.3 環境変数の設定（Cloud Functions）

```bash
# Secret Manager に登録
gcloud secrets create trust-db-url     --data-file=<(echo -n "$DATABASE_URL")
gcloud secrets create trust-slack-hook --data-file=<(echo -n "$SLACK_WEBHOOK_URL")

# Cloud Functions デプロイ時に参照
--set-secrets DATABASE_URL=trust-db-url:latest,SLACK_WEBHOOK_URL=trust-slack-hook:latest
```

---

## 2. 🔴 即時アラート

バッチ完了後に呼び出すチェック群です。
AI解釈バッチとスコア算出バッチの末尾から直接呼び出します。

```python
# monitoring/checks/critical.py

from common import get_db, slack_alert
from datetime import date


def check_batch_duration(job_name: str, threshold_minutes: int = 30):
    """
    ② バッチ処理時間の超過検知
    前7日の中央値の2倍超 OR 絶対上限を超えた場合にアラート
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            # 最新の完了ジョブの処理時間（分）
            cur.execute("""
                SELECT
                    EXTRACT(EPOCH FROM (finished_at - started_at)) / 60 AS duration_min,
                    processed_count
                FROM batch_job_logs
                WHERE job_name = %s
                  AND status = 'completed'
                ORDER BY finished_at DESC
                LIMIT 1
            """, (job_name,))
            latest = cur.fetchone()
            if not latest:
                return

            # 前7日の中央値
            cur.execute("""
                SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (
                    ORDER BY EXTRACT(EPOCH FROM (finished_at - started_at)) / 60
                ) AS median_min
                FROM batch_job_logs
                WHERE job_name = %s
                  AND status = 'completed'
                  AND started_at >= NOW() - INTERVAL '7 days'
            """, (job_name,))
            stats = cur.fetchone()

        duration = latest["duration_min"]
        median   = stats["median_min"] if stats["median_min"] else 0
        threshold = max(threshold_minutes, (median or 0) * 2)

        if duration > threshold:
            slack_alert(
                f"*バッチ処理時間超過* `{job_name}`\n"
                f"今回: {duration:.1f}分 / 閾値: {threshold:.1f}分（前7日中央値: {median:.1f}分）\n"
                f"処理件数: {latest['processed_count']}件",
                level="critical"
            )


def check_snapshot_completeness():
    """
    ⑥ TrustScoreSnapshot更新漏れの検知
    アクティブな全店舗に当日分のSnapshotが存在するか確認
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT s.store_id, s.store_name
                FROM stores s
                LEFT JOIN trust_score_snapshots t
                    ON  t.target_id   = s.store_id
                    AND t.target_type = 'store'
                    AND t.snapshot_date = CURRENT_DATE
                WHERE s.status = 'active'
                  AND t.snapshot_id IS NULL
            """)
            missing = cur.fetchall()

    if missing:
        names = ", ".join(r["store_name"] for r in missing)
        slack_alert(
            f"*Snapshot更新漏れ* {len(missing)}店舗\n"
            f"対象: {names}\n"
            f"スコア算出バッチの再実行を確認してください",
            level="critical"
        )


def check_duplicate_trust_events():
    """
    ⑫ TrustEventの重複生成検知
    同一 (source_type, source_id, trust_dimension) の重複を検知
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    source_type,
                    source_id,
                    trust_dimension,
                    COUNT(*) AS cnt
                FROM trust_events
                WHERE detected_at >= NOW() - INTERVAL '25 hours'
                GROUP BY source_type, source_id, trust_dimension
                HAVING COUNT(*) > 1
            """)
            duplicates = cur.fetchall()

    if duplicates:
        slack_alert(
            f"*TrustEvent重複検知* {len(duplicates)}件\n"
            f"例: source_type={duplicates[0]['source_type']}, "
            f"dimension={duplicates[0]['trust_dimension']}, "
            f"count={duplicates[0]['cnt']}\n"
            f"スコアが歪む可能性があります。バッチの冪等性を確認してください",
            level="critical"
        )


def run_critical_checks(job_name: str):
    """AI解釈バッチ・スコア算出バッチの末尾から呼び出すエントリポイント"""
    check_batch_duration(job_name)
    check_snapshot_completeness()
    check_duplicate_trust_events()
```

**既存バッチへの組み込み方（2行追加するだけ）:**

```python
# 既存のスコア算出バッチ末尾に追加
from monitoring.checks.critical import run_critical_checks

# ... 既存処理 ...

record_job_end(conn, log_id, processed_count)
run_critical_checks("score_calculation_batch")  # ← 追加
```

---

## 3. 🟡 日次チェック

毎朝バッチ完了後（例：08:30）にCloud Schedulerから起動します。

```python
# monitoring/checks/daily.py

from common import get_db, slack_alert
from datetime import date, timedelta


def check_batch_processed_count(job_name: str, drop_ratio: float = 0.5):
    """
    ① バッチ処理件数の減少検知
    前7日平均の50%未満で警告
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            # 直近の処理件数
            cur.execute("""
                SELECT processed_count
                FROM batch_job_logs
                WHERE job_name = %s AND status = 'completed'
                ORDER BY finished_at DESC
                LIMIT 1
            """, (job_name,))
            latest = cur.fetchone()
            if not latest or latest["processed_count"] == 0:
                slack_alert(
                    f"*バッチ処理件数ゼロ* `{job_name}`\n"
                    f"本日の処理件数が0件です。入力データを確認してください",
                    level="warning"
                )
                return

            # 前7日平均
            cur.execute("""
                SELECT AVG(processed_count) AS avg_count
                FROM batch_job_logs
                WHERE job_name = %s
                  AND status = 'completed'
                  AND started_at BETWEEN NOW() - INTERVAL '8 days'
                                     AND NOW() - INTERVAL '1 day'
            """, (job_name,))
            stats = cur.fetchone()

    avg   = stats["avg_count"] or 0
    today = latest["processed_count"]

    if avg > 0 and today < avg * drop_ratio:
        slack_alert(
            f"*バッチ処理件数減少* `{job_name}`\n"
            f"本日: {today}件 / 前7日平均: {avg:.1f}件（{today/avg*100:.0f}%）\n"
            f"接客タグ入力率またはアンケート配信を確認してください",
            level="warning"
        )


def check_claude_api_cost():
    """
    ④ Claude APIコスト急増の検知
    前7日平均の150%超で警告
    注: コストはbatch_job_logsにapi_cost_jpyカラムを追加して記録する
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    api_cost_jpy AS today_cost,
                    (SELECT AVG(api_cost_jpy)
                     FROM batch_job_logs
                     WHERE job_name = 'ai_interpretation_batch'
                       AND status = 'completed'
                       AND started_at BETWEEN NOW() - INTERVAL '8 days'
                                          AND NOW() - INTERVAL '1 day'
                    ) AS avg_cost
                FROM batch_job_logs
                WHERE job_name = 'ai_interpretation_batch'
                  AND status = 'completed'
                ORDER BY finished_at DESC
                LIMIT 1
            """)
            row = cur.fetchone()

    if not row or not row["avg_cost"]:
        return

    if row["today_cost"] > row["avg_cost"] * 1.5:
        slack_alert(
            f"*Claude APIコスト急増*\n"
            f"本日: ¥{row['today_cost']:.0f} / 前7日平均: ¥{row['avg_cost']:.0f}\n"
            f"プロンプト改修または処理件数の急増を確認してください",
            level="warning"
        )


def check_trust_event_by_source():
    """
    ⑤ TrustEvent生成件数のソース別チェック
    いずれかのsource_typeで3日連続ゼロを検知
    """
    source_types = ["visit", "feedback", "complaint", "review"]

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    source_type,
                    SUM(CASE WHEN detected_at::date = CURRENT_DATE - 0 THEN 1 ELSE 0 END) AS d0,
                    SUM(CASE WHEN detected_at::date = CURRENT_DATE - 1 THEN 1 ELSE 0 END) AS d1,
                    SUM(CASE WHEN detected_at::date = CURRENT_DATE - 2 THEN 1 ELSE 0 END) AS d2
                FROM trust_events
                WHERE detected_at >= CURRENT_DATE - INTERVAL '3 days'
                GROUP BY source_type
            """)
            rows = {r["source_type"]: r for r in cur.fetchall()}

    for src in source_types:
        r = rows.get(src)
        if r and r["d0"] == 0 and r["d1"] == 0 and r["d2"] == 0:
            slack_alert(
                f"*TrustEvent生成ゼロ（3日連続）* source_type=`{src}`\n"
                f"該当する入力経路（接客タグ/アンケート/クレームDB/外部レビュー）の疎通を確認してください",
                level="warning"
            )


def run_daily_checks():
    check_batch_processed_count("ai_interpretation_batch")
    check_batch_processed_count("score_calculation_batch")
    check_claude_api_cost()
    check_trust_event_by_source()
```

---

## 4. 🟢 週次チェック

毎週月曜 08:00 にCloud Schedulerから起動し、結果をPdMチャンネルに通知します。

```python
# monitoring/checks/weekly.py

from common import get_db, slack_alert, SLACK_CHANNEL_PDM
from datetime import date, timedelta


def check_confidence_distribution():
    """
    ③ confidence分布の変化
    needs_review=trueの割合が前4週平均の1.5倍超で警告
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            # 直近1週間の要レビュー率
            cur.execute("""
                SELECT
                    COUNT(*) FILTER (WHERE needs_review = true)::float
                    / NULLIF(COUNT(*), 0) AS review_ratio
                FROM trust_events
                WHERE detected_at >= CURRENT_DATE - INTERVAL '7 days'
            """)
            this_week = cur.fetchone()["review_ratio"] or 0

            # 前4週平均
            cur.execute("""
                SELECT AVG(weekly_ratio) AS avg_ratio FROM (
                    SELECT
                        DATE_TRUNC('week', detected_at) AS wk,
                        COUNT(*) FILTER (WHERE needs_review = true)::float
                        / NULLIF(COUNT(*), 0) AS weekly_ratio
                    FROM trust_events
                    WHERE detected_at BETWEEN CURRENT_DATE - INTERVAL '5 weeks'
                                          AND CURRENT_DATE - INTERVAL '7 days'
                    GROUP BY wk
                ) sub
            """)
            avg = cur.fetchone()["avg_ratio"] or 0

    msg = (
        f"*【週次】confidence分布チェック*\n"
        f"今週の要レビュー率: {this_week*100:.1f}% / 前4週平均: {avg*100:.1f}%"
    )
    if avg > 0 and this_week > avg * 1.5:
        msg += "\n⚠️ 要レビュー率が急増しています。プロンプトの見直しを検討してください"
        slack_alert(msg, level="warning", channel=SLACK_CHANNEL_PDM)
    else:
        slack_alert(msg, level="info", channel=SLACK_CHANNEL_PDM)


def check_is_reliable_progress():
    """
    ⑦ is_reliable変化の定点観測
    true→falseへの逆転があれば即時警告
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    s.store_name,
                    t_now.is_reliable  AS reliable_now,
                    t_prev.is_reliable AS reliable_prev
                FROM stores s
                JOIN trust_score_snapshots t_now
                    ON  t_now.target_id   = s.store_id
                    AND t_now.snapshot_date = CURRENT_DATE
                LEFT JOIN trust_score_snapshots t_prev
                    ON  t_prev.target_id   = s.store_id
                    AND t_prev.snapshot_date = CURRENT_DATE - INTERVAL '7 days'
                WHERE s.status = 'active'
            """)
            rows = cur.fetchall()

    reliable_count = sum(1 for r in rows if r["reliable_now"])
    regressions    = [r for r in rows if r["reliable_prev"] and not r["reliable_now"]]

    msg = (
        f"*【週次】is_reliable進捗*\n"
        f"信頼区間確立済み店舗: {reliable_count} / {len(rows)}店舗"
    )
    slack_alert(msg, level="info", channel=SLACK_CHANNEL_PDM)

    if regressions:
        names = ", ".join(r["store_name"] for r in regressions)
        slack_alert(
            f"*⚠️ is_reliable 逆転（true→false）* {names}\n"
            f"データ収集が滞っている可能性があります",
            level="warning"
        )


def check_tag_input_rate():
    """
    ⑧ 接客タグ入力率（週次）
    POS件数に対するVisit記録の割合で近似
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            # Visit件数（接客タグ入力件数の近似）
            cur.execute("""
                SELECT
                    s.store_name,
                    COUNT(v.visit_id) AS visit_count
                FROM stores s
                LEFT JOIN visits v
                    ON  v.store_id = s.store_id
                    AND v.visit_datetime >= CURRENT_DATE - INTERVAL '7 days'
                WHERE s.status = 'active'
                GROUP BY s.store_id, s.store_name
            """)
            rows = cur.fetchall()

    low_stores = [r for r in rows if r["visit_count"] < 10]  # 閾値は運用で調整
    msg = (
        f"*【週次】接客タグ入力状況*\n"
        + "\n".join(f"　{r['store_name']}: {r['visit_count']}件" for r in rows)
    )
    if low_stores:
        msg += f"\n⚠️ 入力件数が少ない店舗: {', '.join(r['store_name'] for r in low_stores)}"
    slack_alert(msg, level="info", channel=SLACK_CHANNEL_PDM)


def check_review_queue_backlog():
    """
    ⑩ 人間レビューキューの滞留
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    COUNT(*) AS total_pending,
                    COUNT(*) FILTER (
                        WHERE detected_at < NOW() - INTERVAL '7 days'
                    ) AS overdue_7d
                FROM trust_events
                WHERE needs_review  = true
                  AND reviewed_flag = false
            """)
            row = cur.fetchone()

    msg = (
        f"*【週次】レビューキュー状況*\n"
        f"未レビュー件数: {row['total_pending']}件（うち7日超過: {row['overdue_7d']}件）"
    )
    level = "warning" if row["total_pending"] > 50 or row["overdue_7d"] > 0 else "info"
    slack_alert(msg, level=level, channel=SLACK_CHANNEL_PDM)


def run_weekly_checks():
    check_confidence_distribution()
    check_is_reliable_progress()
    check_tag_input_rate()
    check_review_queue_backlog()
```

---

## 5. Cloud Functionsエントリポイント

```python
# monitoring/main_daily.py

import functions_framework
from checks.daily import run_daily_checks

@functions_framework.http
def daily_monitoring(request):
    run_daily_checks()
    return "ok", 200
```

```python
# monitoring/main_weekly.py

import functions_framework
from checks.weekly import run_weekly_checks

@functions_framework.http
def weekly_monitoring(request):
    run_weekly_checks()
    return "ok", 200
```

🔴の即時チェックは既存バッチから直接呼び出すため、専用エントリポイントは不要です。

---

## 6. Cloud Schedulerの設定

```bash
# 日次チェック（毎朝08:30・バッチ完了後を想定）
gcloud scheduler jobs create http trust-daily-monitoring \
  --schedule="30 8 * * *" \
  --uri="https://REGION-PROJECT.cloudfunctions.net/daily_monitoring" \
  --oidc-service-account-email=monitoring-sa@PROJECT.iam.gserviceaccount.com \
  --time-zone="Asia/Tokyo"

# 週次チェック（毎週月曜08:00）
gcloud scheduler jobs create http trust-weekly-monitoring \
  --schedule="0 8 * * 1" \
  --uri="https://REGION-PROJECT.cloudfunctions.net/weekly_monitoring" \
  --oidc-service-account-email=monitoring-sa@PROJECT.iam.gserviceaccount.com \
  --time-zone="Asia/Tokyo"
```

---

## 7. Cloud Monitoringネイティブアラート（インフラ層）

アプリケーション層の監視（上記）とは別に、インフラ層はCloud Monitoringで設定します。

```bash
# Cloud Functions の実行エラーレートアラート
gcloud alpha monitoring policies create \
  --policy-from-file=monitoring_policy_functions_error.json
```

```json
// monitoring_policy_functions_error.json
{
  "displayName": "Trust Platform - Functions Error Rate",
  "conditions": [{
    "displayName": "Error rate > 5%",
    "conditionThreshold": {
      "filter": "resource.type=\"cloud_function\" AND metric.type=\"cloudfunctions.googleapis.com/function/execution_count\" AND metric.labels.status!=\"ok\"",
      "comparison": "COMPARISON_GT",
      "thresholdValue": 0.05,
      "duration": "300s",
      "aggregations": [{
        "alignmentPeriod": "300s",
        "perSeriesAligner": "ALIGN_RATE"
      }]
    }
  }],
  "notificationChannels": ["projects/PROJECT/notificationChannels/SLACK_CHANNEL_ID"]
}
```

---

## 8. デプロイ手順

```bash
# 1. 依存パッケージ
pip install functions-framework psycopg2-binary requests

# 2. DBマイグレーション
psql $DATABASE_URL -f migrations/add_batch_job_logs.sql

# 3. 日次チェックのデプロイ
gcloud functions deploy daily_monitoring \
  --runtime=python311 \
  --trigger=http \
  --entry-point=daily_monitoring \
  --source=monitoring/ \
  --set-secrets DATABASE_URL=trust-db-url:latest,SLACK_WEBHOOK_URL=trust-slack-hook:latest \
  --region=asia-northeast1

# 4. 週次チェックのデプロイ
gcloud functions deploy weekly_monitoring \
  --runtime=python311 \
  --trigger=http \
  --entry-point=weekly_monitoring \
  --source=monitoring/ \
  --set-secrets DATABASE_URL=trust-db-url:latest,SLACK_WEBHOOK_URL=trust-slack-hook:latest \
  --region=asia-northeast1
```

---

## 9. 初期閾値と調整方針

Phase 1はデータが少ないため、閾値は**運用3〜4週後に必ず見直します**。

| 項目 | 初期閾値 | 調整タイミング | 調整の根拠 |
|---|---|---|---|
| バッチ処理時間 | 中央値×2倍 or 30分上限 | 4週後 | 正常レンジが安定したら上限を実績値ベースに変更 |
| 処理件数減少 | 前7日平均の50%未満 | 4週後 | 週次変動のレンジを見て比率を調整 |
| 要レビュー率 | 前4週平均の1.5倍 | 8週後 | 4週分の平均が溜まってから有効化 |
| レビューキュー | 50件超 | 4週後 | 実際の滞留ペースを見て閾値を設定 |
