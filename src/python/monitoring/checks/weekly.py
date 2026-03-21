"""週次チェック。

信頼スコアの異常変動、データ充足度、アラート閾値の傾向を確認する。

Note:
    毎週月曜に実行し、週次レポートと合わせて確認する。
"""

import logging
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.python.monitoring.common import CheckResult, CheckStatus

logger = logging.getLogger(__name__)


def check_score_anomaly(
    engine: Engine,
    anomaly_threshold: float = 10.0,
) -> CheckResult:
    """信頼スコアの週次異常変動を検知する。

    Args:
        engine: SQLAlchemy エンジン
        anomaly_threshold: 1 週間で許容するスコア変動幅（デフォルト 10pt）

    Returns:
        CheckResult
    """
    try:
        with engine.connect() as conn:
            # 直近 2 週のスナップショットを取得
            result = conn.execute(
                text(
                    "SELECT target_id, snapshot_date, overall_score "
                    "FROM trust_score_snapshot "
                    "WHERE target_type = 'store' "
                    "ORDER BY target_id, snapshot_date DESC"
                )
            )
            rows = result.fetchall()

        # 店舗ごとに直近 2 週を比較
        store_scores: dict[str, list[tuple[date, float]]] = {}
        for row in rows:
            store_id = str(row[0])
            if store_id not in store_scores:
                store_scores[store_id] = []
            if len(store_scores[store_id]) < 2:
                score = float(row[2]) if row[2] is not None else 50.0
                store_scores[store_id].append((row[1], score))

        anomalies: list[str] = []
        for store_id, scores in store_scores.items():
            if len(scores) >= 2:
                diff = abs(scores[0][1] - scores[1][1])
                if diff > anomaly_threshold:
                    anomalies.append(
                        f"store={store_id[:8]}...: {scores[1][1]:.1f}→{scores[0][1]:.1f} (差 {diff:.1f}pt)"
                    )

        if anomalies:
            return CheckResult(
                name="score_anomaly",
                status=CheckStatus.WARN,
                message=f"スコア異常変動 {len(anomalies)} 件: {'; '.join(anomalies)}",
                details={"anomalies": anomalies},
            )

        return CheckResult(
            name="score_anomaly",
            status=CheckStatus.OK,
            message="スコア変動正常（異常変動なし）",
        )
    except Exception as e:
        return CheckResult(
            name="score_anomaly",
            status=CheckStatus.ERROR,
            message=f"スコア異常チェックエラー: {e}",
        )


def check_data_sufficiency(
    engine: Engine,
    min_events_per_store: int = 10,
) -> CheckResult:
    """店舗ごとのデータ充足度を確認する。

    Args:
        engine: SQLAlchemy エンジン
        min_events_per_store: 1 週間に期待する最小イベント数

    Returns:
        CheckResult
    """
    week_ago = date.today() - timedelta(weeks=1)

    try:
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT s.store_id, s.store_name, "
                    "  COALESCE(event_counts.cnt, 0) AS event_count "
                    "FROM store s "
                    "LEFT JOIN ("
                    "  SELECT store_id, COUNT(*) AS cnt "
                    "  FROM trust_event "
                    "  WHERE detected_at::date >= :week_ago "
                    "  GROUP BY store_id"
                    ") event_counts ON s.store_id = event_counts.store_id "
                    "WHERE s.status = 'active'"
                ),
                {"week_ago": week_ago},
            )
            rows = result.fetchall()

        insufficient: list[str] = []
        for row in rows:
            if row[2] < min_events_per_store:
                insufficient.append(f"{row[1]}({row[2]}件)")

        if insufficient:
            return CheckResult(
                name="data_sufficiency",
                status=CheckStatus.WARN,
                message=(
                    f"データ不足店舗 {len(insufficient)} 件: "
                    f"{', '.join(insufficient)}（閾値: 週{min_events_per_store}件）"
                ),
                details={"insufficient_stores": insufficient},
            )

        return CheckResult(
            name="data_sufficiency",
            status=CheckStatus.OK,
            message=f"全店舗データ充足（閾値: 週{min_events_per_store}件）",
        )
    except Exception as e:
        return CheckResult(
            name="data_sufficiency",
            status=CheckStatus.ERROR,
            message=f"データ充足度チェックエラー: {e}",
        )


def check_unreliable_stores(engine: Engine) -> CheckResult:
    """is_reliable=False の店舗数を確認する。

    Args:
        engine: SQLAlchemy エンジン

    Returns:
        CheckResult
    """
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT COUNT(*) FROM trust_score_snapshot "
                    "WHERE target_type = 'store' "
                    "AND is_reliable = false "
                    "AND snapshot_date = ("
                    "  SELECT MAX(snapshot_date) FROM trust_score_snapshot"
                    ")"
                )
            )
            unreliable_count = result.scalar() or 0

            result = conn.execute(
                text(
                    "SELECT COUNT(*) FROM trust_score_snapshot "
                    "WHERE target_type = 'store' "
                    "AND snapshot_date = ("
                    "  SELECT MAX(snapshot_date) FROM trust_score_snapshot"
                    ")"
                )
            )
            total_count = result.scalar() or 0

        if total_count == 0:
            return CheckResult(
                name="unreliable_stores",
                status=CheckStatus.WARN,
                message="スコアスナップショットが存在しない",
            )

        if unreliable_count > 0:
            return CheckResult(
                name="unreliable_stores",
                status=CheckStatus.WARN,
                message=f"unreliable 店舗: {unreliable_count}/{total_count} 件",
                details={"unreliable": unreliable_count, "total": total_count},
            )

        return CheckResult(
            name="unreliable_stores",
            status=CheckStatus.OK,
            message=f"全 {total_count} 店舗が reliable",
        )
    except Exception as e:
        return CheckResult(
            name="unreliable_stores",
            status=CheckStatus.ERROR,
            message=f"unreliable チェックエラー: {e}",
        )


def run_weekly_checks(engine: Engine) -> list[CheckResult]:
    """全週次チェックを実行する。

    Args:
        engine: SQLAlchemy エンジン

    Returns:
        CheckResult のリスト
    """
    results = [
        check_score_anomaly(engine),
        check_data_sufficiency(engine),
        check_unreliable_stores(engine),
    ]

    for r in results:
        level = logging.WARNING if not r.is_ok() else logging.INFO
        logger.log(level, "[weekly] %s: %s — %s", r.status.value, r.name, r.message)

    return results
