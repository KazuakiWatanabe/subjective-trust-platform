"""週次チェック（毎週月曜 08:00）。

- check_confidence_distribution: needs_review 率が前4週平均の1.5倍超で警告
- check_is_reliable_progress: is_reliable の逆転（true→false）を検知
- check_tag_input_rate: 接客タグ入力件数を店舗別に集計
- check_review_queue_backlog: 未レビュー件数50件超・7日超過で警告

Note:
    結果は PdM チャンネル（SLACK_CHANNEL_PDM）に通知する。
"""

import logging

from src.python.monitoring.common import (
    SLACK_CHANNEL_PDM,
    CheckResult,
    CheckStatus,
    get_db,
    slack_alert,
)

logger = logging.getLogger(__name__)


def check_confidence_distribution() -> CheckResult:
    """needs_review 率が前4週平均の1.5倍超で警告する。

    Returns:
        CheckResult
    """
    try:
        with get_db() as conn, conn.cursor() as cur:
            cur.execute(
                """
                    SELECT
                        COUNT(*) FILTER (WHERE needs_review = true)::float
                        / NULLIF(COUNT(*), 0) AS review_ratio
                    FROM trust_event
                    WHERE detected_at >= CURRENT_DATE - INTERVAL '7 days'
                    """
            )
            row = cur.fetchone()
            this_week = float(row["review_ratio"]) if row and row["review_ratio"] else 0.0

            cur.execute(
                """
                    SELECT AVG(weekly_ratio) AS avg_ratio FROM (
                        SELECT
                            DATE_TRUNC('week', detected_at) AS wk,
                            COUNT(*) FILTER (WHERE needs_review = true)::float
                            / NULLIF(COUNT(*), 0) AS weekly_ratio
                        FROM trust_event
                        WHERE detected_at BETWEEN CURRENT_DATE - INTERVAL '5 weeks'
                                              AND CURRENT_DATE - INTERVAL '7 days'
                        GROUP BY wk
                    ) sub
                    """
            )
            row2 = cur.fetchone()
            avg = float(row2["avg_ratio"]) if row2 and row2["avg_ratio"] else 0.0

        msg = (
            f"*【週次】confidence分布チェック*\n"
            f"今週の要レビュー率: {this_week * 100:.1f}% / 前4週平均: {avg * 100:.1f}%"
        )
        if avg > 0 and this_week > avg * 1.5:
            msg += "\n要レビュー率が急増しています。プロンプトの見直しを検討してください"
            slack_alert(msg, level="warning", channel=SLACK_CHANNEL_PDM)
            return CheckResult(name="confidence_distribution", status=CheckStatus.WARN, message=msg)

        slack_alert(msg, level="info", channel=SLACK_CHANNEL_PDM)
        return CheckResult(name="confidence_distribution", status=CheckStatus.OK, message=msg)
    except Exception as e:
        return CheckResult(
            name="confidence_distribution",
            status=CheckStatus.ERROR,
            message=f"confidence チェックエラー: {e}",
        )


def check_is_reliable_progress() -> CheckResult:
    """is_reliable の逆転（true→false）を検知する。

    Returns:
        CheckResult
    """
    try:
        with get_db() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    s.store_name,
                    t_now.is_reliable AS reliable_now,
                    t_prev.is_reliable AS reliable_prev
                FROM store s
                JOIN trust_score_snapshot t_now
                    ON t_now.target_id = s.store_id
                    AND t_now.target_type = 'store'
                    AND t_now.snapshot_date = (
                        SELECT MAX(snapshot_date)
                        FROM trust_score_snapshot
                    )
                LEFT JOIN trust_score_snapshot t_prev
                    ON t_prev.target_id = s.store_id
                    AND t_prev.target_type = 'store'
                    AND t_prev.snapshot_date = (
                        SELECT MAX(snapshot_date)
                        FROM trust_score_snapshot
                    ) - INTERVAL '7 days'
                WHERE s.status = 'active'
                """
            )
            rows = cur.fetchall()

        reliable_count = sum(1 for r in rows if r["reliable_now"])
        regressions = [r for r in rows if r["reliable_prev"] and not r["reliable_now"]]

        msg = f"*【週次】is_reliable進捗*\n信頼区間確立済み店舗: {reliable_count} / {len(rows)}店舗"
        slack_alert(msg, level="info", channel=SLACK_CHANNEL_PDM)

        if regressions:
            names = ", ".join(str(r["store_name"]) for r in regressions)
            warn_msg = (
                f"*is_reliable 逆転（true→false）* {names}\nデータ収集が滞っている可能性があります"
            )
            slack_alert(warn_msg, level="warning")
            return CheckResult(
                name="is_reliable_progress", status=CheckStatus.WARN, message=warn_msg
            )

        return CheckResult(name="is_reliable_progress", status=CheckStatus.OK, message=msg)
    except Exception as e:
        return CheckResult(
            name="is_reliable_progress",
            status=CheckStatus.ERROR,
            message=f"is_reliable チェックエラー: {e}",
        )


def check_tag_input_rate() -> CheckResult:
    """接客タグ入力件数を店舗別に集計する。

    Returns:
        CheckResult
    """
    try:
        with get_db() as conn, conn.cursor() as cur:
            cur.execute(
                """
                    SELECT s.store_name, COUNT(v.visit_id) AS visit_count
                    FROM store s
                    LEFT JOIN visit v
                        ON v.store_id = s.store_id
                        AND v.visit_datetime >= CURRENT_DATE - INTERVAL '7 days'
                    WHERE s.status = 'active'
                    GROUP BY s.store_id, s.store_name
                    """
            )
            rows = cur.fetchall()

        low_stores = [r for r in rows if r["visit_count"] < 10]
        lines = [f"  {r['store_name']}: {r['visit_count']}件" for r in rows]
        msg = "*【週次】接客タグ入力状況*\n" + "\n".join(lines)
        if low_stores:
            msg += f"\n入力件数が少ない店舗: {', '.join(str(r['store_name']) for r in low_stores)}"

        slack_alert(msg, level="info", channel=SLACK_CHANNEL_PDM)

        if low_stores:
            return CheckResult(name="tag_input_rate", status=CheckStatus.WARN, message=msg)
        return CheckResult(name="tag_input_rate", status=CheckStatus.OK, message=msg)
    except Exception as e:
        return CheckResult(
            name="tag_input_rate",
            status=CheckStatus.ERROR,
            message=f"タグ入力率チェックエラー: {e}",
        )


def check_review_queue_backlog() -> CheckResult:
    """未レビュー件数50件超・7日超過で警告する。

    Returns:
        CheckResult
    """
    try:
        with get_db() as conn, conn.cursor() as cur:
            cur.execute(
                """
                    SELECT
                        COUNT(*) AS total_pending,
                        COUNT(*) FILTER (
                            WHERE detected_at < NOW() - INTERVAL '7 days'
                        ) AS overdue_7d
                    FROM trust_event
                    WHERE needs_review = true AND reviewed_flag = false
                    """
            )
            row = cur.fetchone()

        total = row["total_pending"] if row else 0
        overdue = row["overdue_7d"] if row else 0

        msg = f"*【週次】レビューキュー状況*\n未レビュー件数: {total}件（うち7日超過: {overdue}件）"
        if total > 50 or overdue > 0:
            slack_alert(msg, level="warning", channel=SLACK_CHANNEL_PDM)
            return CheckResult(name="review_queue_backlog", status=CheckStatus.WARN, message=msg)

        slack_alert(msg, level="info", channel=SLACK_CHANNEL_PDM)
        return CheckResult(name="review_queue_backlog", status=CheckStatus.OK, message=msg)
    except Exception as e:
        return CheckResult(
            name="review_queue_backlog",
            status=CheckStatus.ERROR,
            message=f"レビューキューチェックエラー: {e}",
        )


def run_weekly_checks() -> list[CheckResult]:
    """全週次チェックを実行する。

    Returns:
        CheckResult のリスト
    """
    results = [
        check_confidence_distribution(),
        check_is_reliable_progress(),
        check_tag_input_rate(),
        check_review_queue_backlog(),
    ]

    for r in results:
        level = logging.WARNING if not r.is_ok() else logging.INFO
        logger.log(level, "[weekly] %s: %s — %s", r.status.value, r.name, r.message)

    return results
