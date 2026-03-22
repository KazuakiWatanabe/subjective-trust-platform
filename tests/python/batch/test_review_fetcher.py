"""Google 口コミ取得バッチのユニットテスト。

対象: src/python/batch/review_fetcher.py
"""

import uuid

from src.python.batch.review_fetcher import (
    filter_new_reviews,
    normalize_review,
    parse_rating,
    run_review_fetch,
)
from src.python.utils.pii_masker import ANONYMOUS_REVIEWER_NAME


def _make_raw_review(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "reviewId": "google-review-001",
        "starRating": "FOUR",
        "comment": "接客がとても丁寧でした",
        "createTime": "2026-03-20T10:00:00Z",
        "updateTime": "2026-03-20T10:00:00Z",
    }
    base.update(overrides)
    return base


class TestParseRating:
    def test_FIVE_to_5(self) -> None:
        assert parse_rating("FIVE") == 5

    def test_ONE_to_1(self) -> None:
        assert parse_rating("ONE") == 1

    def test_unknown_to_0(self) -> None:
        assert parse_rating("UNKNOWN") == 0


class TestNormalizeReview:
    def test_正規化が正しい(self) -> None:
        store_id = uuid.uuid4()
        raw = _make_raw_review()
        result = normalize_review(raw, store_id)  # type: ignore[arg-type]
        assert result["platform"] == "google"
        assert result["rating"] == 4
        assert result["reviewer_name"] == ANONYMOUS_REVIEWER_NAME
        assert result["google_review_id"] == "google-review-001"
        assert result["processed_flag"] is False

    def test_PIIマスキングが適用される(self) -> None:
        store_id = uuid.uuid4()
        raw = _make_raw_review(comment="たなかさんの対応が良かった。電話は03-1234-5678")
        result = normalize_review(raw, store_id)  # type: ignore[arg-type]
        assert "たなかさん" not in result["review_text"]
        assert "03-1234-5678" not in result["review_text"]


class TestFilterNewReviews:
    def test_重複除外(self) -> None:
        reviews = [
            _make_raw_review(reviewId="id-1"),
            _make_raw_review(reviewId="id-2"),
            _make_raw_review(reviewId="id-3"),
        ]
        existing = {"id-1", "id-3"}
        result = filter_new_reviews(reviews, existing)  # type: ignore[arg-type]
        assert len(result) == 1
        assert result[0]["reviewId"] == "id-2"

    def test_全件新規(self) -> None:
        reviews = [_make_raw_review(reviewId="new-1")]
        result = filter_new_reviews(reviews, set())  # type: ignore[arg-type]
        assert len(result) == 1


class TestRunReviewFetch:
    def test_正規化とフィルタが統合される(self) -> None:
        store_id = uuid.uuid4()
        reviews = [
            _make_raw_review(reviewId="id-1"),
            _make_raw_review(reviewId="id-2"),
        ]
        existing = {"id-1"}
        result = run_review_fetch(reviews, store_id, existing)  # type: ignore[arg-type]
        assert len(result) == 1
        assert result[0]["google_review_id"] == "id-2"
