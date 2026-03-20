"""AI 解釈パイプライン（日次バッチ）。

Feedback.free_comment と ReviewExternal のテキストを対象に
AI 解釈を実行し、TrustEvent テーブルに書き込む。

Note:
    T-05 で本実装を行う。現時点ではスタブのみ。
"""

import argparse
import asyncio
import logging
import sys

logger = logging.getLogger(__name__)


async def run_pipeline(target_date: str | None = None) -> None:
    """AI 解釈パイプラインを実行する。

    Args:
        target_date: 処理対象日（YYYY-MM-DD）。None の場合は前日分を処理する。

    Note:
        T-05 で本実装を行う。
    """
    logger.info("AI 解釈パイプライン: スタブ実行（target_date=%s）", target_date)


async def watch() -> None:
    """ワーカーモード: パイプラインの待機ループ。

    Note:
        T-05 で本実装を行う。現時点ではログ出力のみで待機する。
    """
    logger.info("AI 解釈ワーカー: 待機モード起動")
    while True:
        await asyncio.sleep(60)


def main() -> None:
    """エントリポイント。--watch または --date で起動モードを切り替える。"""
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="AI 解釈パイプライン")
    parser.add_argument("--date", type=str, default=None, help="処理対象日 (YYYY-MM-DD)")
    parser.add_argument("--watch", action="store_true", help="ワーカー待機モードで起動")
    args = parser.parse_args()

    if args.watch:
        asyncio.run(watch())
    else:
        asyncio.run(run_pipeline(target_date=args.date))


if __name__ == "__main__":
    main()
