"""週次監視エントリポイント。

クリティカルチェック + 週次チェックを実行し、異常があれば Slack 通知する。

Usage:
    docker compose exec api python -m src.python.monitoring.main_weekly
"""

import logging
import sys

from src.python.monitoring.checks.critical import run_critical_checks
from src.python.monitoring.checks.weekly import run_weekly_checks
from src.python.monitoring.common import get_sync_engine, send_slack_notification

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    """週次監視を実行する。"""
    logger.info("=== 週次監視開始 ===")

    engine = get_sync_engine()

    # クリティカルチェック
    critical_results = run_critical_checks(engine)

    critical_failures = [r for r in critical_results if not r.is_ok()]
    if critical_failures:
        logger.error("クリティカルチェック失敗: %d 件", len(critical_failures))
        send_slack_notification(critical_results, channel_label="critical")
        sys.exit(1)

    # 週次チェック
    weekly_results = run_weekly_checks(engine)

    # 全結果を通知
    all_results = critical_results + weekly_results
    send_slack_notification(all_results, channel_label="weekly")

    failures = [r for r in all_results if not r.is_ok()]
    if failures:
        logger.warning("=== 週次監視完了（警告あり: %d 件） ===", len(failures))
    else:
        logger.info("=== 週次監視完了（全チェック正常） ===")

    engine.dispose()


if __name__ == "__main__":
    main()
