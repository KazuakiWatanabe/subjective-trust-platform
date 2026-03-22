"""Google 口コミ解釈バッチのユニットテスト。

対象: src/python/batch/review_interpreter.py
"""

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.python.batch.review_interpreter import (
    mentions_to_trust_events,
    run_review_interpret_batch,
)
from src.python.interpretation.schemas import SubjectiveHints, TrustInterpretation


def _make_review(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "review_id": uuid.uuid4(),
        "store_id": uuid.uuid4(),
        "rating": 4,
        "review_text": "接客がとても丁寧でした",
        "posted_at": datetime.now(timezone.utc),
    }
    base.update(overrides)
    return base


def _make_interpretation_result(
    dimension: str = "service",
    confidence: float = 0.85,
) -> dict[str, Any]:
    return {
        "mentions": [{
            "trust_dimension": dimension,
            "sentiment": "positive",
            "severity": 1,
            "theme_tags": ["丁寧"],
            "summary": "テスト要約",
            "interpretation": "テスト解釈",
            "confidence": confidence,
        }],
        "subjective_hints": {
            "trait_signal": "品質重視",
            "state_signal": None,
            "meta_signal": None,
        },
        "overall_sentiment": "positive",
        "review_type": "single_visit",
        "contains_competitor_mention": False,
    }


class TestMentionsToTrustEvents:
    """mentions → TrustEvent 変換。"""

    def test_1件のmentionから1件のTrustEvent(self) -> None:
        result = _make_interpretation_result()
        events = mentions_to_trust_events(
            review_id=uuid.uuid4(),
            store_id=uuid.uuid4(),
            review_date=datetime.now(timezone.utc),
            interpretation_result=result,
        )
        assert len(events) == 1
        assert events[0]["source_type"] == "review"
        assert events[0]["trust_dimension"] == "service"
        assert events[0]["generated_by"] == "ai"

    def test_複数mentionから複数TrustEvent(self) -> None:
        result = _make_interpretation_result()
        result["mentions"].append({
            "trust_dimension": "product",
            "sentiment": "negative",
            "severity": 2,
            "theme_tags": ["品質"],
            "summary": "品質不満",
            "interpretation": "期待以下",
            "confidence": 0.7,
        })
        events = mentions_to_trust_events(
            review_id=uuid.uuid4(),
            store_id=uuid.uuid4(),
            review_date=datetime.now(timezone.utc),
            interpretation_result=result,
        )
        assert len(events) == 2
        assert events[0]["trust_dimension"] == "service"
        assert events[1]["trust_dimension"] == "product"

    def test_低confidenceでneeds_reviewがTrue(self) -> None:
        result = _make_interpretation_result(confidence=0.4)
        events = mentions_to_trust_events(
            review_id=uuid.uuid4(),
            store_id=uuid.uuid4(),
            review_date=datetime.now(timezone.utc),
            interpretation_result=result,
        )
        assert events[0]["needs_review"] is True

    def test_subjective_hintsが設定される(self) -> None:
        result = _make_interpretation_result()
        events = mentions_to_trust_events(
            review_id=uuid.uuid4(),
            store_id=uuid.uuid4(),
            review_date=datetime.now(timezone.utc),
            interpretation_result=result,
        )
        assert events[0]["trait_signal"] == "品質重視"


@pytest.mark.asyncio
class TestRunReviewInterpretBatch:
    """解釈バッチ実行。"""

    async def test_正常な解釈バッチ(self) -> None:
        mock_client = AsyncMock()
        mock_client.interpret = AsyncMock(return_value=TrustInterpretation(
            trust_dimension="service",
            sentiment="positive",
            severity=1,
            theme_tags=["丁寧"],
            summary="テスト",
            interpretation="テスト解釈",
            subjective_hints=SubjectiveHints(trait_signal="品質重視"),
            confidence=0.85,
        ))
        reviews = [_make_review()]
        events, processed = await run_review_interpret_batch(reviews, mock_client)
        assert len(events) >= 1
        assert len(processed) == 1

    async def test_空テキストはスキップ(self) -> None:
        mock_client = AsyncMock()
        reviews = [_make_review(review_text="")]
        events, processed = await run_review_interpret_batch(reviews, mock_client)
        assert len(events) == 0
        assert len(processed) == 1
        mock_client.interpret.assert_not_called()

    async def test_エラー時はneeds_reviewがTrue(self) -> None:
        mock_client = AsyncMock()
        mock_client.interpret = AsyncMock(side_effect=Exception("API error"))
        reviews = [_make_review()]
        events, processed = await run_review_interpret_batch(reviews, mock_client)
        assert len(events) == 1
        assert events[0]["needs_review"] is True
        assert len(processed) == 1
