"""Google Business Profile API 接続確認スクリプト。

Usage:
    python scripts/test_google_api.py --store-id <STORE_ID>

Note:
    GOOGLE_SERVICE_ACCOUNT_KEY_PATH と GOOGLE_LOCATION_IDS が設定済みであること。
    D-9（1 店舗テスト）で使用する。
"""

import argparse
import json
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    """API 接続を確認しレビュー件数を出力する。"""
    parser = argparse.ArgumentParser(description="Google Business Profile API 接続確認")
    parser.add_argument("--store-id", required=True, help="対象店舗 ID")
    args = parser.parse_args()

    key_path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_KEY_PATH")
    location_ids_raw = os.environ.get("GOOGLE_LOCATION_IDS", "{}")

    if not key_path:
        logger.error("GOOGLE_SERVICE_ACCOUNT_KEY_PATH が未設定です")
        sys.exit(1)

    try:
        location_ids = json.loads(location_ids_raw)
    except json.JSONDecodeError:
        logger.error("GOOGLE_LOCATION_IDS が不正な JSON です")
        sys.exit(1)

    location_name = location_ids.get(args.store_id)
    if not location_name:
        logger.error("store_id=%s に対応する location_name が見つかりません", args.store_id)
        sys.exit(1)

    try:
        from google.oauth2 import service_account  # type: ignore[import-untyped]
        from googleapiclient.discovery import build  # type: ignore[import-untyped]

        scopes = ["https://www.googleapis.com/auth/business.manage"]
        credentials = service_account.Credentials.from_service_account_file(
            key_path, scopes=scopes
        )
        service = build("mybusiness", "v4", credentials=credentials)

        request = service.accounts().locations().reviews().list(
            parent=location_name,
            pageSize=10,
        )
        response = request.execute()
        reviews = response.get("reviews", [])

        logger.info("API 接続成功")
        logger.info("取得件数: %d 件（pageSize=10）", len(reviews))
        logger.info("totalReviewCount: %s", response.get("totalReviewCount", "N/A"))

        for r in reviews[:3]:
            logger.info(
                "  - %s: %s (%s)",
                r.get("starRating", "?"),
                (r.get("comment", "")[:50] + "...") if r.get("comment") else "(本文なし)",
                r.get("updateTime", "?"),
            )

    except Exception as e:
        logger.error("API 接続失敗: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
