"""信頼スコア算出ロジックのユニットテスト。

対象: src/python/scoring/calculator.py
テスト観点: スコア算出式、base_score回帰、スナップショット生成、is_reliable判定

Note:
    DB は使用しない。算出ロジック単体をテストする。
"""

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest

from src.python.scoring.calculator import (
    BASE_SCORE,
    TrustScoreCalculator,
    calculate_dimension_score,
)


def _make_event(
    dimension: str = "service",
    sentiment: str = "positive",
    severity: int = 1,
    weeks_ago: int = 1,
    confidence: float = 0.85,
) -> dict[str, Any]:
    """テスト用 TrustEvent 辞書を生成するヘルパー。"""
    detected_at = datetime.now(timezone.utc) - timedelta(weeks=weeks_ago)
    return {
        "trust_event_id": uuid.uuid4(),
        "store_id": uuid.uuid4(),
        "source_type": "feedback",
        "source_id": uuid.uuid4(),
        "trust_dimension": dimension,
        "sentiment": sentiment,
        "severity": severity,
        "confidence": confidence,
        "needs_review": confidence < 0.6,
        "generated_by": "ai",
        "detected_at": detected_at,
    }


class TestCalculateDimensionScore:
    """AC-01: スコア算出式の検証。"""

    # AC-01: positive イベントでスコアが上がる
    def test_positiveイベントでスコアが上がる(self) -> None:
        """positive イベントが base_score に加算される。"""
        events = [_make_event(sentiment="positive", severity=1, weeks_ago=1)]
        score = calculate_dimension_score("service", events)
        assert score > BASE_SCORE

    # AC-01: negative イベントでスコアが下がる
    def test_negativeイベントでスコアが下がる(self) -> None:
        """negative イベントが base_score から減算される。"""
        events = [_make_event(sentiment="negative", severity=2, weeks_ago=1)]
        score = calculate_dimension_score("service", events)
        assert score < BASE_SCORE

    # AC-01: severity が大きいほど影響が大きい
    def test_severityが大きいほど影響が大きい(self) -> None:
        """severity=3 は severity=1 よりも大きな減点になる。"""
        events_sev1 = [_make_event(sentiment="negative", severity=1, weeks_ago=1)]
        events_sev3 = [_make_event(sentiment="negative", severity=3, weeks_ago=1)]
        score_sev1 = calculate_dimension_score("service", events_sev1)
        score_sev3 = calculate_dimension_score("service", events_sev3)
        assert score_sev3 < score_sev1

    # AC-01: recency_decay が適用される（古いイベントほど影響が小さい）
    def test_古いイベントほど影響が小さい(self) -> None:
        """weeks_ago=1 の方が weeks_ago=13 より影響が大きい。"""
        events_recent = [_make_event(sentiment="positive", severity=1, weeks_ago=1)]
        events_old = [_make_event(sentiment="positive", severity=1, weeks_ago=13)]
        score_recent = calculate_dimension_score("service", events_recent)
        score_old = calculate_dimension_score("service", events_old)
        assert score_recent > score_old

    # AC-01: neutral イベントはスコアに影響しない
    def test_neutralイベントはスコアに影響しない(self) -> None:
        """neutral イベントは base_score を変えない。"""
        events = [_make_event(sentiment="neutral", severity=1, weeks_ago=1)]
        score = calculate_dimension_score("service", events)
        assert score == BASE_SCORE


class TestBaseScore:
    """AC-02: base_score = 50 でデータ不足時に回帰する。"""

    # AC-02: イベントなしの場合は base_score を返す
    def test_イベントなしでbase_scoreを返す(self) -> None:
        """イベントが空の場合は base_score(50) を返す。"""
        score = calculate_dimension_score("service", [])
        assert score == BASE_SCORE

    # AC-02: base_score の値が 50 である
    def test_base_scoreが50(self) -> None:
        """BASE_SCORE 定数が 50 である。"""
        assert BASE_SCORE == 50.0


class TestTrustScoreCalculator:
    """AC-03/AC-04: スナップショット生成と is_reliable 判定。"""

    # AC-03: calculate_snapshot が5次元のスコアを含む辞書を返す
    def test_スナップショットが5次元のスコアを含む(self) -> None:
        """calculate_snapshot が product/service/proposal/operation/story のスコアを返す。"""
        calculator = TrustScoreCalculator()
        events = [_make_event(dimension="service", sentiment="positive", weeks_ago=1)]
        snapshot = calculator.calculate_snapshot(
            store_id=uuid.uuid4(),
            events=events,
            snapshot_date=datetime.now(timezone.utc).date(),
        )
        assert "product_score" in snapshot
        assert "service_score" in snapshot
        assert "proposal_score" in snapshot
        assert "operation_score" in snapshot
        assert "story_score" in snapshot
        assert "overall_score" in snapshot
        assert "event_count" in snapshot

    # AC-04: event_count < 20 の次元は is_reliable = False
    def test_イベント不足でis_reliableがFalse(self) -> None:
        """event_count < 20 の場合は is_reliable=False。"""
        calculator = TrustScoreCalculator()
        events = [_make_event(dimension="service", sentiment="positive", weeks_ago=1)
                  for _ in range(5)]
        snapshot = calculator.calculate_snapshot(
            store_id=uuid.uuid4(),
            events=events,
            snapshot_date=datetime.now(timezone.utc).date(),
        )
        assert snapshot["is_reliable"] is False

    # AC-04: event_count >= 20 の場合は is_reliable = True
    def test_イベント十分でis_reliableがTrue(self) -> None:
        """event_count >= 20 の場合は is_reliable=True。"""
        calculator = TrustScoreCalculator()
        events = [_make_event(dimension="service", sentiment="positive", weeks_ago=i % 12 + 1)
                  for i in range(25)]
        snapshot = calculator.calculate_snapshot(
            store_id=uuid.uuid4(),
            events=events,
            snapshot_date=datetime.now(timezone.utc).date(),
        )
        assert snapshot["is_reliable"] is True

    # AC-03: スコアは 0〜100 の範囲に収まる
    def test_スコアが0から100の範囲(self) -> None:
        """大量の negative イベントでもスコアが 0 未満にならない。"""
        calculator = TrustScoreCalculator()
        events = [_make_event(dimension="service", sentiment="negative", severity=3, weeks_ago=1)
                  for _ in range(50)]
        snapshot = calculator.calculate_snapshot(
            store_id=uuid.uuid4(),
            events=events,
            snapshot_date=datetime.now(timezone.utc).date(),
        )
        assert snapshot["service_score"] >= 0.0
        assert snapshot["service_score"] <= 100.0
