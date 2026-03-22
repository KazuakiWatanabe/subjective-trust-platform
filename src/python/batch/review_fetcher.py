"""Google 口コミ取得バッチ。

Google Business Profile API からレビューを取得し、
PII マスキング後に review_external テーブルに保存する。

Note:
    認証は OAuth 2.0 サービスアカウント。
    google_review_id で重複防止。reviewer_name は「（匿名）」固定。
    D-9（1 店舗テスト）は実環境 API キーが必要なため別途実施する。
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from src.python.utils.pii_masker import ANONYMOUS_REVIEWER_NAME, mask_review_text

logger = logging.getLogger(__name__)

# Google API の星評価を int に変換するマッピング
_STAR_RATING_MAP: dict[str, int] = {
    "ONE": 1,
    "TWO": 2,
    "THREE": 3,
    "FOUR": 4,
    "FIVE": 5,
}


def parse_rating(star_rating: str) -> int:
    """Google API の starRating を int に変換する。

    Args:
        star_rating: "ONE" 〜 "FIVE"

    Returns:
        1〜5 の整数
    """
    return _STAR_RATING_MAP.get(star_rating, 0)


def parse_datetime(iso_str: str) -> datetime:
    """ISO 8601 文字列を datetime に変換する。

    Args:
        iso_str: ISO 8601 形式の日時文字列

    Returns:
        datetime (UTC)
    """
    return datetime.fromisoformat(iso_str.replace("Z", "+00:00"))


def normalize_review(
    raw_review: dict[str, Any],
    store_id: uuid.UUID,
) -> dict[str, Any]:
    """Google API のレビュー応答を review_external 形式に正規化する。

    Args:
        raw_review: Google API のレビュー dict
        store_id: 店舗 ID

    Returns:
        review_external テーブルに挿入可能な辞書
    """
    comment = raw_review.get("comment", "")
    masked_text = mask_review_text(comment) if comment else ""

    return {
        "review_id": uuid.uuid4(),
        "store_id": store_id,
        "platform": "google",
        "rating": parse_rating(raw_review.get("starRating", "")),
        "review_text": masked_text,
        "reviewer_name": ANONYMOUS_REVIEWER_NAME,
        "posted_at": parse_datetime(raw_review.get("createTime", datetime.now(UTC).isoformat())),
        "fetched_at": datetime.now(UTC),
        "google_review_id": raw_review.get("reviewId"),
        "processed_flag": False,
        "processed_at": None,
    }


def filter_new_reviews(
    raw_reviews: list[dict[str, Any]],
    existing_google_ids: set[str],
) -> list[dict[str, Any]]:
    """既存の google_review_id と重複するレビューを除外する。

    Args:
        raw_reviews: Google API から取得した全レビュー
        existing_google_ids: DB に保存済みの google_review_id セット

    Returns:
        新規レビューのみのリスト
    """
    new_reviews = []
    for review in raw_reviews:
        review_id = review.get("reviewId", "")
        if review_id and review_id not in existing_google_ids:
            new_reviews.append(review)
    return new_reviews


def run_review_fetch(
    raw_reviews: list[dict[str, Any]],
    store_id: uuid.UUID,
    existing_google_ids: set[str],
) -> list[dict[str, Any]]:
    """レビュー取得結果を正規化・フィルタリングする。

    Args:
        raw_reviews: Google API から取得した全レビュー
        store_id: 店舗 ID
        existing_google_ids: DB に保存済みの google_review_id セット

    Returns:
        review_external テーブルに挿入可能な辞書のリスト（新規のみ）
    """
    new_reviews = filter_new_reviews(raw_reviews, existing_google_ids)

    normalized: list[dict[str, Any]] = []
    for raw in new_reviews:
        record = normalize_review(raw, store_id)
        normalized.append(record)

    logger.info(
        "口コミ取得完了: 全 %d 件中 新規 %d 件",
        len(raw_reviews),
        len(normalized),
    )
    return normalized
