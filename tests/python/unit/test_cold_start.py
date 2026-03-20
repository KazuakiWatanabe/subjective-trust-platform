"""コールドスタート対応のユニットテスト。

対象: src/python/scoring/calculator.py, src/python/api/routers/scores.py
テスト観点: 導入初期のスコア表示制御（蓄積期・試行期・本運用）

Note:
    設計書 §2.5 のコールドスタート対応を検証する。
"""

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from src.python.api.main import app
from src.python.scoring.calculator import (
    ColdStartPhase,
    TrustScoreCalculator,
    determine_cold_start_phase,
)


class TestDetermineColdStartPhase:
    """コールドスタートフェーズ判定。"""

    # AC-01: 導入〜4週目は蓄積期
    def test_4週以内は蓄積期(self) -> None:
        """導入から 4 週以内は ACCUMULATING。"""
        phase = determine_cold_start_phase(weeks_since_launch=2)
        assert phase == ColdStartPhase.ACCUMULATING

    def test_4週ちょうどは蓄積期(self) -> None:
        """導入から 4 週ちょうどは ACCUMULATING。"""
        phase = determine_cold_start_phase(weeks_since_launch=4)
        assert phase == ColdStartPhase.ACCUMULATING

    # AC-02: 5〜12週目は試行期
    def test_5週は試行期(self) -> None:
        """導入から 5 週は TRIAL。"""
        phase = determine_cold_start_phase(weeks_since_launch=5)
        assert phase == ColdStartPhase.TRIAL

    def test_12週は試行期(self) -> None:
        """導入から 12 週は TRIAL。"""
        phase = determine_cold_start_phase(weeks_since_launch=12)
        assert phase == ColdStartPhase.TRIAL

    # AC-03: 13週目以降は本運用
    def test_13週以降は本運用(self) -> None:
        """導入から 13 週以降は PRODUCTION。"""
        phase = determine_cold_start_phase(weeks_since_launch=13)
        assert phase == ColdStartPhase.PRODUCTION


class TestColdStartCalculator:
    """TrustScoreCalculator のコールドスタート対応。"""

    # AC-01: 蓄積期はスコアを算出せず event_count のみ
    def test_蓄積期はスコアなしでevent_countのみ(self) -> None:
        """ACCUMULATING フェーズではスコアが None で event_count が返る。"""
        calculator = TrustScoreCalculator()
        events = [
            _make_event("service", "positive", weeks_ago=1)
            for _ in range(5)
        ]
        snapshot = calculator.calculate_snapshot(
            store_id=uuid.uuid4(),
            events=events,
            snapshot_date=date.today(),
            weeks_since_launch=3,
        )
        assert snapshot["service_score"] is None
        assert snapshot["overall_score"] is None
        assert snapshot["event_count"] == 5
        assert snapshot["cold_start_phase"] == "accumulating"

    # AC-02: 試行期は is_reliable=False でスコアが返る
    def test_試行期はスコアありでis_reliableがFalse(self) -> None:
        """TRIAL フェーズではスコアが算出されるが is_reliable=False。"""
        calculator = TrustScoreCalculator()
        events = [
            _make_event("service", "positive", weeks_ago=1)
            for _ in range(10)
        ]
        snapshot = calculator.calculate_snapshot(
            store_id=uuid.uuid4(),
            events=events,
            snapshot_date=date.today(),
            weeks_since_launch=8,
        )
        assert snapshot["service_score"] is not None
        assert snapshot["is_reliable"] is False
        assert snapshot["cold_start_phase"] == "trial"

    # AC-03: 本運用 + イベント20件以上で is_reliable=True
    def test_本運用でイベント十分ならis_reliableがTrue(self) -> None:
        """PRODUCTION + event_count >= 20 で is_reliable=True。"""
        calculator = TrustScoreCalculator()
        events = [
            _make_event("service", "positive", weeks_ago=i % 12 + 1)
            for i in range(25)
        ]
        snapshot = calculator.calculate_snapshot(
            store_id=uuid.uuid4(),
            events=events,
            snapshot_date=date.today(),
            weeks_since_launch=15,
        )
        assert snapshot["is_reliable"] is True
        assert snapshot["cold_start_phase"] == "production"


def _make_event(
    dimension: str = "service",
    sentiment: str = "positive",
    weeks_ago: int = 1,
) -> dict[str, Any]:
    """テスト用 TrustEvent 辞書。"""
    return {
        "trust_event_id": uuid.uuid4(),
        "store_id": uuid.uuid4(),
        "source_type": "feedback",
        "source_id": uuid.uuid4(),
        "trust_dimension": dimension,
        "sentiment": sentiment,
        "severity": 1,
        "confidence": 0.85,
        "needs_review": False,
        "generated_by": "ai",
        "detected_at": datetime.now(timezone.utc) - timedelta(weeks=weeks_ago),
    }
