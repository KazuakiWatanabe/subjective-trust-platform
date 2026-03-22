"""クリティカルチェック（即時アラート）。

バッチ完了後に呼び出す 3 つのチェック:
- check_batch_duration: バッチ処理時間の超過検知（前7日中央値×2倍 or 30分上限）
- check_snapshot_completeness: TrustScoreSnapshot 更新漏れの検知
- check_duplicate_trust_events: TrustEvent 重複生成の検知

Note:
    AI 解釈バッチ・スコア算出バッチの末尾から直接呼び出す。
    異常検知時は Slack の #trust-platform-alerts に即時通知する。
"""

import logging

from src.python.monitoring.common import CheckResult, CheckStatus, get_db, slack_alert

logger = logging.getLogger(__name__)


def check_batch_duration(
    job_name: str,
    threshold_minutes: int = 30,
) -> CheckResult:
    """バッチ処理時間の超過を検知する。

    前 7 日の中央値の 2 倍超、または絶対上限超でアラート。

    Args:
        job_name: ジョブ名
        threshold_minutes: 絶対上限（分）

    Returns:
        CheckResult
    """
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        EXTRACT(EPOCH FROM (finished_at - started_at)) / 60 AS duration_min,
                        processed_count
                    FROM batch_job_logs
                    WHERE job_name = %s AND status = 'completed'
                    ORDER BY finished_at DESC LIMIT 1
                    """,
                    (job_name,),
                )
                latest = cur.fetchone()
                if not latest:
                    return CheckResult(
                        name="batch_duration",
                        status=CheckStatus.OK,
                        message=f"完了ジョブなし: {job_name}",
                    )

                cur.execute(
                    """
                    SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (
                        ORDER BY EXTRACT(EPOCH FROM (finished_at - started_at)) / 60
                    ) AS median_min
                    FROM batch_job_logs
                    WHERE job_name = %s AND status = 'completed'
                    AND started_at >= NOW() - INTERVAL '7 days'
                    """,
                    (job_name,),
                )
                stats = cur.fetchone()

            duration = float(latest["duration_min"])
            median = float(stats["median_min"]) if stats and stats["median_min"] else 0.0
            effective_threshold = max(threshold_minutes, median * 2)

            if duration > effective_threshold:
                msg = (
                    f"*バッチ処理時間超過* `{job_name}`\n"
                    f"今回: {duration:.1f}分 / 閾値: {effective_threshold:.1f}分"
                    f"（前7日中央値: {median:.1f}分）\n"
                    f"処理件数: {latest['processed_count']}件"
                )
                slack_alert(msg, level="critical")
                return CheckResult(
                    name="batch_duration",
                    status=CheckStatus.CRITICAL,
                    message=msg,
                )

        return CheckResult(
            name="batch_duration",
            status=CheckStatus.OK,
            message=f"処理時間正常: {job_name} ({duration:.1f}分)",
        )
    except Exception as e:
        return CheckResult(
            name="batch_duration",
            status=CheckStatus.ERROR,
            message=f"バッチ時間チェックエラー: {e}",
        )


def check_snapshot_completeness() -> CheckResult:
    """TrustScoreSnapshot 更新漏れを検知する。

    アクティブな全店舗に当日分の Snapshot が存在するか確認する。

    Returns:
        CheckResult
    """
    try:
        with get_db() as conn, conn.cursor() as cur:
            cur.execute(
                """
                    SELECT s.store_id, s.store_name
                    FROM store s
                    LEFT JOIN trust_score_snapshot t
                        ON t.target_id = s.store_id
                        AND t.target_type = 'store'
                        AND t.snapshot_date = CURRENT_DATE
                    WHERE s.status = 'active'
                    AND t.snapshot_id IS NULL
                    """
            )
            missing = cur.fetchall()

        if missing:
            names = ", ".join(str(r["store_name"]) for r in missing)
            msg = (
                f"*Snapshot更新漏れ* {len(missing)}店舗\n"
                f"対象: {names}\n"
                f"スコア算出バッチの再実行を確認してください"
            )
            slack_alert(msg, level="critical")
            return CheckResult(
                name="snapshot_completeness",
                status=CheckStatus.CRITICAL,
                message=msg,
            )

        return CheckResult(
            name="snapshot_completeness",
            status=CheckStatus.OK,
            message="全店舗の Snapshot 更新済み",
        )
    except Exception as e:
        return CheckResult(
            name="snapshot_completeness",
            status=CheckStatus.ERROR,
            message=f"Snapshot チェックエラー: {e}",
        )


def check_duplicate_trust_events() -> CheckResult:
    """TrustEvent の重複生成を検知する。

    同一 (source_type, source_id, trust_dimension) の重複を過去 25 時間で検知。

    Returns:
        CheckResult
    """
    try:
        with get_db() as conn, conn.cursor() as cur:
            cur.execute(
                """
                    SELECT source_type, source_id, trust_dimension, COUNT(*) AS cnt
                    FROM trust_event
                    WHERE detected_at >= NOW() - INTERVAL '25 hours'
                    GROUP BY source_type, source_id, trust_dimension
                    HAVING COUNT(*) > 1
                    """
            )
            duplicates = cur.fetchall()

        if duplicates:
            first = duplicates[0]
            msg = (
                f"*TrustEvent重複検知* {len(duplicates)}件\n"
                f"例: source_type={first['source_type']}, "
                f"dimension={first['trust_dimension']}, count={first['cnt']}\n"
                f"スコアが歪む可能性があります。バッチの冪等性を確認してください"
            )
            slack_alert(msg, level="critical")
            return CheckResult(
                name="duplicate_trust_events",
                status=CheckStatus.CRITICAL,
                message=msg,
            )

        return CheckResult(
            name="duplicate_trust_events",
            status=CheckStatus.OK,
            message="TrustEvent 重複なし",
        )
    except Exception as e:
        return CheckResult(
            name="duplicate_trust_events",
            status=CheckStatus.ERROR,
            message=f"重複チェックエラー: {e}",
        )


def run_critical_checks(job_name: str) -> list[CheckResult]:
    """全クリティカルチェックを実行する。

    Args:
        job_name: バッチジョブ名（check_batch_duration に渡す）

    Returns:
        CheckResult のリスト
    """
    results = [
        check_batch_duration(job_name),
        check_snapshot_completeness(),
        check_duplicate_trust_events(),
    ]

    for r in results:
        level = logging.ERROR if not r.is_ok() else logging.INFO
        logger.log(level, "[critical] %s: %s — %s", r.status.value, r.name, r.message)

    return results
