"""日次監視エントリポイント。

クリティカルチェック + 日次チェックを実行し、異常があれば Slack 通知する。

Usage:
    docker compose exec api python -m src.python.monitoring.main_daily
"""

import logging
import sys

from src.python.monitoring.checks.critical import run_critical_checks
from src.python.monitoring.checks.daily import run_daily_checks
from src.python.monitoring.common import get_sync_engine, send_slack_notification

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    """日次監視を実行する。"""
    logger.info("=== 日次監視開始 ===")

    engine = get_sync_engine()

    # クリティカルチェック
    critical_results = run_critical_checks(engine)

    # クリティカルに失敗した場合は日次チェックをスキップ
    critical_failures = [r for r in critical_results if not r.is_ok()]
    if critical_failures:
        logger.error("クリティカルチェック失敗: %d 件", len(critical_failures))
        send_slack_notification(critical_results, channel_label="critical")
        sys.exit(1)

    # 日次チェック
    daily_results = run_daily_checks(engine)

    # 全結果を通知
    all_results = critical_results + daily_results
    send_slack_notification(all_results, channel_label="daily")

    failures = [r for r in all_results if not r.is_ok()]
    if failures:
        logger.warning("=== 日次監視完了（警告あり: %d 件） ===", len(failures))
    else:
        logger.info("=== 日次監視完了（全チェック正常） ===")

    engine.dispose()


if __name__ == "__main__":
    main()
