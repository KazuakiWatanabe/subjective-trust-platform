"""TrustEvent 自動生成（ルールベース）のユニットテスト。

対象: src/python/domain/services/event_generator.py
テスト観点: 接客結果・アンケートスコアからのルールベースイベント生成、冪等性

Note:
    設計書 §2.3 の手動生成ルールを検証する。
"""

import uuid
from typing import Any

import pytest

from src.python.domain.services.event_generator import RuleBasedEventGenerator


def _make_visit(
    contact_result: str = "purchase",
    alternative_proposed: bool | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """テスト用 Visit 辞書を生成するヘルパー。"""
    base: dict[str, Any] = {
        "visit_id": uuid.uuid4(),
        "store_id": uuid.uuid4(),
        "contact_result": contact_result,
        "alternative_proposed": alternative_proposed,
    }
    base.update(kwargs)
    return base


def _make_feedback(
    score_revisit: int = 3,
    **kwargs: Any,
) -> dict[str, Any]:
    """テスト用 Feedback 辞書を生成するヘルパー。"""
    base: dict[str, Any] = {
        "feedback_id": uuid.uuid4(),
        "visit_id": uuid.uuid4(),
        "store_id": uuid.uuid4(),
        "score_revisit": score_revisit,
    }
    base.update(kwargs)
    return base


class TestVisitRules:
    """Visit からのルールベースイベント生成。"""

    # AC-01: 欠品離脱 + alternative_proposed=False → 提案信頼ネガティブ
    def test_欠品離脱_代替提案なしで提案信頼ネガティブ(self) -> None:
        """contact_result=out_of_stock_exit, alternative_proposed=False で proposal/negative。"""
        gen = RuleBasedEventGenerator()
        visit = _make_visit(
            contact_result="out_of_stock_exit",
            alternative_proposed=False,
        )
        events = gen.generate_from_visit(visit)
        assert len(events) == 1
        assert events[0]["trust_dimension"] == "proposal"
        assert events[0]["sentiment"] == "negative"
        assert events[0]["generated_by"] == "rule"

    # AC-01: 欠品離脱 + alternative_proposed=True → イベント生成なし
    def test_欠品離脱_代替提案ありでイベントなし(self) -> None:
        """代替提案済みの場合はネガティブイベントを生成しない。"""
        gen = RuleBasedEventGenerator()
        visit = _make_visit(
            contact_result="out_of_stock_exit",
            alternative_proposed=True,
        )
        events = gen.generate_from_visit(visit)
        assert len(events) == 0

    # AC-01: 通常購入ではイベント生成なし
    def test_通常購入ではイベント生成なし(self) -> None:
        """contact_result=purchase ではルールベースイベントは生成されない。"""
        gen = RuleBasedEventGenerator()
        visit = _make_visit(contact_result="purchase")
        events = gen.generate_from_visit(visit)
        assert len(events) == 0


class TestFeedbackRules:
    """Feedback からのルールベースイベント生成。"""

    # AC-02: score_revisit 1〜2 → 接客信頼ネガティブ
    @pytest.mark.parametrize("score", [1, 2])
    def test_低スコアで接客信頼ネガティブ(self, score: int) -> None:
        """score_revisit 1-2 で service/negative。"""
        gen = RuleBasedEventGenerator()
        feedback = _make_feedback(score_revisit=score)
        events = gen.generate_from_feedback(feedback)
        negative_events = [e for e in events if e["sentiment"] == "negative"]
        assert len(negative_events) >= 1
        assert negative_events[0]["trust_dimension"] == "service"

    # AC-03: score_revisit 4〜5 → 接客信頼ポジティブ
    @pytest.mark.parametrize("score", [4, 5])
    def test_高スコアで接客信頼ポジティブ(self, score: int) -> None:
        """score_revisit 4-5 で service/positive。"""
        gen = RuleBasedEventGenerator()
        feedback = _make_feedback(score_revisit=score)
        events = gen.generate_from_feedback(feedback)
        positive_events = [e for e in events if e["sentiment"] == "positive"]
        assert len(positive_events) >= 1
        assert positive_events[0]["trust_dimension"] == "service"

    # AC-02/AC-03: score_revisit=3 → イベント生成なし
    def test_中間スコアではイベント生成なし(self) -> None:
        """score_revisit=3 ではルールベースイベントは生成されない。"""
        gen = RuleBasedEventGenerator()
        feedback = _make_feedback(score_revisit=3)
        events = gen.generate_from_feedback(feedback)
        assert len(events) == 0


class TestIdempotency:
    """AC-04: 同一 source_id から重複イベントが生成されない。"""

    # AC-04: 同一 visit_id の再処理で重複しない
    def test_同一visitの再処理で重複しない(self) -> None:
        """同じ visit を 2 回処理しても 1 回分のイベントしか生成されない。"""
        gen = RuleBasedEventGenerator()
        visit = _make_visit(
            contact_result="out_of_stock_exit",
            alternative_proposed=False,
        )
        events1 = gen.generate_from_visit(visit)
        events2 = gen.generate_from_visit(visit)
        assert len(events1) == 1
        assert len(events2) == 0

    # AC-04: 同一 feedback_id の再処理で重複しない
    def test_同一feedbackの再処理で重複しない(self) -> None:
        """同じ feedback を 2 回処理しても 1 回分のイベントしか生成されない。"""
        gen = RuleBasedEventGenerator()
        feedback = _make_feedback(score_revisit=1)
        events1 = gen.generate_from_feedback(feedback)
        events2 = gen.generate_from_feedback(feedback)
        assert len(events1) >= 1
        assert len(events2) == 0
