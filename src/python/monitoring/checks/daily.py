"""日次チェック（毎朝 08:30）。

- check_batch_processed_count: バッチ処理件数の減少検知（前7日平均の50%未満）
- check_claude_api_cost: Claude API コスト急増（前7日平均の150%超）
- check_trust_event_by_source: source_type 別に 3 日連続ゼロを検知

Note:
    Cloud Scheduler から main_daily.py 経由で起動する。
"""

import logging

from src.python.monitoring.common import CheckResult, CheckStatus, get_db, slack_alert

logger = logging.getLogger(__name__)


def check_batch_processed_count(
    job_name: str,
    drop_ratio: float = 0.5,
) -> CheckResult:
    """バッチ処理件数の減少を検知する。

    Args:
        job_name: ジョブ名
        drop_ratio: 前7日平均に対する警告閾値（デフォルト 50%）

    Returns:
        CheckResult
    """
    try:
        with get_db() as conn, conn.cursor() as cur:
            cur.execute(
                """
                    SELECT processed_count
                    FROM batch_job_logs
                    WHERE job_name = %s AND status = 'completed'
                    ORDER BY finished_at DESC LIMIT 1
                    """,
                (job_name,),
            )
            latest = cur.fetchone()
            if not latest or latest["processed_count"] == 0:
                msg = (
                    f"*バッチ処理件数ゼロ* `{job_name}`\n"
                    f"本日の処理件数が0件です。入力データを確認してください"
                )
                slack_alert(msg, level="warning")
                return CheckResult(
                    name="batch_processed_count", status=CheckStatus.WARN, message=msg
                )

            cur.execute(
                """
                    SELECT AVG(processed_count) AS avg_count
                    FROM batch_job_logs
                    WHERE job_name = %s AND status = 'completed'
                    AND started_at BETWEEN NOW() - INTERVAL '8 days' AND NOW() - INTERVAL '1 day'
                    """,
                (job_name,),
            )
            stats = cur.fetchone()

        avg = float(stats["avg_count"]) if stats and stats["avg_count"] else 0.0
        today = latest["processed_count"]

        if avg > 0 and today < avg * drop_ratio:
            msg = (
                f"*バッチ処理件数減少* `{job_name}`\n"
                f"本日: {today}件 / 前7日平均: {avg:.1f}件（{today / avg * 100:.0f}%）\n"
                f"接客タグ入力率またはアンケート配信を確認してください"
            )
            slack_alert(msg, level="warning")
            return CheckResult(name="batch_processed_count", status=CheckStatus.WARN, message=msg)

        return CheckResult(
            name="batch_processed_count",
            status=CheckStatus.OK,
            message=f"処理件数正常: {job_name} ({today}件)",
        )
    except Exception as e:
        return CheckResult(
            name="batch_processed_count",
            status=CheckStatus.ERROR,
            message=f"処理件数チェックエラー: {e}",
        )


def check_claude_api_cost() -> CheckResult:
    """Claude API コスト急増を検知する（前7日平均の150%超）。

    Returns:
        CheckResult
    """
    try:
        with get_db() as conn, conn.cursor() as cur:
            cur.execute(
                """
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
                    WHERE job_name = 'ai_interpretation_batch' AND status = 'completed'
                    ORDER BY finished_at DESC LIMIT 1
                    """
            )
            row = cur.fetchone()

        if not row or not row["avg_cost"] or not row["today_cost"]:
            return CheckResult(
                name="claude_api_cost", status=CheckStatus.OK, message="API コストデータなし"
            )

        today_cost = float(row["today_cost"])
        avg_cost = float(row["avg_cost"])

        if today_cost > avg_cost * 1.5:
            msg = (
                f"*Claude APIコスト急増*\n"
                f"本日: ¥{today_cost:.0f} / 前7日平均: ¥{avg_cost:.0f}\n"
                f"プロンプト改修または処理件数の急増を確認してください"
            )
            slack_alert(msg, level="warning")
            return CheckResult(name="claude_api_cost", status=CheckStatus.WARN, message=msg)

        return CheckResult(
            name="claude_api_cost",
            status=CheckStatus.OK,
            message=f"API コスト正常: ¥{today_cost:.0f}",
        )
    except Exception as e:
        return CheckResult(
            name="claude_api_cost",
            status=CheckStatus.ERROR,
            message=f"API コストチェックエラー: {e}",
        )


def check_trust_event_by_source() -> CheckResult:
    """source_type 別に 3 日連続ゼロを検知する。

    Returns:
        CheckResult
    """
    source_types = ["visit", "feedback", "complaint", "review"]

    try:
        with get_db() as conn, conn.cursor() as cur:
            cur.execute(
                """
                    SELECT
                        source_type,
                        SUM(CASE WHEN detected_at::date = CURRENT_DATE THEN 1 ELSE 0 END) AS d0,
                        SUM(CASE WHEN detected_at::date = CURRENT_DATE - 1 THEN 1 ELSE 0 END) AS d1,
                        SUM(CASE WHEN detected_at::date = CURRENT_DATE - 2 THEN 1 ELSE 0 END) AS d2
                    FROM trust_event
                    WHERE detected_at >= CURRENT_DATE - INTERVAL '3 days'
                    GROUP BY source_type
                    """
            )
            rows = {r["source_type"]: r for r in cur.fetchall()}

        zero_sources: list[str] = []
        for src in source_types:
            r = rows.get(src)
            if not r or (r["d0"] == 0 and r["d1"] == 0 and r["d2"] == 0):
                zero_sources.append(src)

        if zero_sources:
            msg = (
                f"*TrustEvent生成ゼロ（3日連続）* source_type={', '.join(zero_sources)}\n"
                f"該当する入力経路の疎通を確認してください"
            )
            slack_alert(msg, level="warning")
            return CheckResult(name="trust_event_by_source", status=CheckStatus.WARN, message=msg)

        return CheckResult(
            name="trust_event_by_source",
            status=CheckStatus.OK,
            message="全 source_type でイベント生成あり",
        )
    except Exception as e:
        return CheckResult(
            name="trust_event_by_source",
            status=CheckStatus.ERROR,
            message=f"ソース別チェックエラー: {e}",
        )


def run_daily_checks() -> list[CheckResult]:
    """全日次チェックを実行する。

    Returns:
        CheckResult のリスト
    """
    results = [
        check_batch_processed_count("ai_interpretation_batch"),
        check_batch_processed_count("score_calculation_batch"),
        check_claude_api_cost(),
        check_trust_event_by_source(),
    ]

    for r in results:
        level = logging.WARNING if not r.is_ok() else logging.INFO
        logger.log(level, "[daily] %s: %s — %s", r.status.value, r.name, r.message)

    return results
