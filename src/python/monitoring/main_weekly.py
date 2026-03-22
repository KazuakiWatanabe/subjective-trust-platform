"""週次監視 Cloud Functions エントリポイント。

Cloud Scheduler から毎週月曜 08:00 に呼び出される。

Usage（ローカル）:
    python -m src.python.monitoring.main_weekly
"""

import logging

import functions_framework  # type: ignore[import-untyped]

from src.python.monitoring.checks.weekly import run_weekly_checks

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@functions_framework.http
def weekly_monitoring(request: object) -> tuple[str, int]:
    """Cloud Functions エントリポイント。"""
    logger.info("=== 週次監視開始 ===")
    results = run_weekly_checks()
    failures = [r for r in results if not r.is_ok()]
    if failures:
        logger.warning("=== 週次監視完了（警告あり: %d 件） ===", len(failures))
    else:
        logger.info("=== 週次監視完了（全チェック正常） ===")
    return "ok", 200


def main() -> None:
    """ローカル実行用エントリポイント。"""
    logger.info("=== 週次監視開始（ローカル） ===")
    results = run_weekly_checks()
    failures = [r for r in results if not r.is_ok()]
    if failures:
        logger.warning("=== 週次監視完了（警告あり: %d 件） ===", len(failures))
    else:
        logger.info("=== 週次監視完了（全チェック正常） ===")


if __name__ == "__main__":
    main()
