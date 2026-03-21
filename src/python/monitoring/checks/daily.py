"""日次チェック。

AI 解釈パイプラインの実行状況、needs_review 率、POS 連携状況を確認する。

Note:
    毎朝実行し、前日のバッチ処理が正常に完了したかを検証する。
"""

import logging
from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.python.monitoring.common import CheckResult, CheckStatus

logger = logging.getLogger(__name__)


def check_pipeline_execution(
    engine: Engine,
    target_date: date | None = None,
) -> CheckResult:
    """AI 解釈パイプラインの実行確認。

    Args:
        engine: SQLAlchemy エンジン
        target_date: 確認対象日（デフォルトは前日）

    Returns:
        CheckResult
    """
    if target_date is None:
        target_date = date.today() - timedelta(days=1)

    try:
        with engine.connect() as conn:
            # 対象日に生成された AI イベント数を確認
            result = conn.execute(
                text(
                    "SELECT COUNT(*) FROM trust_event "
                    "WHERE generated_by = 'ai' "
                    "AND detected_at::date = :target_date"
                ),
                {"target_date": target_date},
            )
            ai_event_count = result.scalar() or 0

            # 対象日の未処理 Feedback（free_comment あり）を確認
            result = conn.execute(
                text(
                    "SELECT COUNT(*) FROM feedback f "
                    "WHERE f.free_comment IS NOT NULL "
                    "AND f.free_comment != '' "
                    "AND f.submitted_at::date = :target_date "
                    "AND NOT EXISTS ("
                    "  SELECT 1 FROM trust_event te "
                    "  WHERE te.source_type = 'feedback' "
                    "  AND te.source_id = f.feedback_id "
                    "  AND te.generated_by = 'ai'"
                    ")"
                ),
                {"target_date": target_date},
            )
            unprocessed_count = result.scalar() or 0

        if unprocessed_count > 0:
            return CheckResult(
                name="pipeline_execution",
                status=CheckStatus.WARN,
                message=(
                    f"未処理 Feedback あり: {unprocessed_count} 件"
                    f"（AI イベント生成: {ai_event_count} 件）"
                ),
                details={
                    "target_date": str(target_date),
                    "ai_event_count": ai_event_count,
                    "unprocessed_count": unprocessed_count,
                },
            )

        return CheckResult(
            name="pipeline_execution",
            status=CheckStatus.OK,
            message=f"パイプライン正常: AI イベント {ai_event_count} 件生成",
            details={"target_date": str(target_date), "ai_event_count": ai_event_count},
        )
    except Exception as e:
        return CheckResult(
            name="pipeline_execution",
            status=CheckStatus.ERROR,
            message=f"パイプラインチェックエラー: {e}",
        )


def check_needs_review_rate(
    engine: Engine,
    target_date: date | None = None,
    warn_threshold: float = 0.3,
) -> CheckResult:
    """needs_review 率の確認。

    Args:
        engine: SQLAlchemy エンジン
        target_date: 確認対象日（デフォルトは前日）
        warn_threshold: 警告閾値（デフォルト 30%）

    Returns:
        CheckResult
    """
    if target_date is None:
        target_date = date.today() - timedelta(days=1)

    try:
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT "
                    "  COUNT(*) AS total, "
                    "  SUM(CASE WHEN needs_review THEN 1 ELSE 0 END) AS review_count "
                    "FROM trust_event "
                    "WHERE generated_by = 'ai' "
                    "AND detected_at::date = :target_date"
                ),
                {"target_date": target_date},
            )
            row = result.fetchone()
            total = row[0] if row else 0
            review_count = row[1] if row else 0

        if total == 0:
            return CheckResult(
                name="needs_review_rate",
                status=CheckStatus.OK,
                message="AI イベントなし（needs_review 率算出スキップ）",
            )

        rate = review_count / total
        if rate > warn_threshold:
            return CheckResult(
                name="needs_review_rate",
                status=CheckStatus.WARN,
                message=(
                    f"needs_review 率が高い: {rate:.0%}（{review_count}/{total} 件）"
                    f" — 閾値 {warn_threshold:.0%}"
                ),
                details={"rate": rate, "total": total, "review_count": review_count},
            )

        return CheckResult(
            name="needs_review_rate",
            status=CheckStatus.OK,
            message=f"needs_review 率正常: {rate:.0%}（{review_count}/{total} 件）",
        )
    except Exception as e:
        return CheckResult(
            name="needs_review_rate",
            status=CheckStatus.ERROR,
            message=f"needs_review 率チェックエラー: {e}",
        )


def check_pos_sync(
    engine: Engine,
    target_date: date | None = None,
) -> CheckResult:
    """POS 日次連携の実行確認。

    Args:
        engine: SQLAlchemy エンジン
        target_date: 確認対象日（デフォルトは前日）

    Returns:
        CheckResult
    """
    if target_date is None:
        target_date = date.today() - timedelta(days=1)

    try:
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT COUNT(*) FROM purchase "
                    "WHERE purchased_at::date = :target_date"
                ),
                {"target_date": target_date},
            )
            purchase_count = result.scalar() or 0

        if purchase_count == 0:
            return CheckResult(
                name="pos_sync",
                status=CheckStatus.WARN,
                message=f"POS データなし: {target_date}（連携未実行の可能性）",
            )

        return CheckResult(
            name="pos_sync",
            status=CheckStatus.OK,
            message=f"POS 連携正常: {purchase_count} 件取り込み済み",
        )
    except Exception as e:
        return CheckResult(
            name="pos_sync",
            status=CheckStatus.ERROR,
            message=f"POS 連携チェックエラー: {e}",
        )


def run_daily_checks(
    engine: Engine,
    target_date: date | None = None,
) -> list[CheckResult]:
    """全日次チェックを実行する。

    Args:
        engine: SQLAlchemy エンジン
        target_date: 確認対象日

    Returns:
        CheckResult のリスト
    """
    results = [
        check_pipeline_execution(engine, target_date),
        check_needs_review_rate(engine, target_date),
        check_pos_sync(engine, target_date),
    ]

    for r in results:
        level = logging.WARNING if not r.is_ok() else logging.INFO
        logger.log(level, "[daily] %s: %s — %s", r.status.value, r.name, r.message)

    return results
