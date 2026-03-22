"""POS データからの TrustEvent 自動生成のユニットテスト。

対象: src/python/batch/pos_event_generator.py
テスト観点: 返品→商品信頼ネガティブ、severity マッピング、generated_by/confidence/needs_review
参照: docs/trust-observation-system-v1.md §2.3

Note:
    ルールベース生成のため AI 解釈は伴わない。
"""

import uuid
from typing import Any

import pytest

from src.python.batch.pos_event_generator import (
    detect_return_trust_event,
    generate_trust_events_from_purchase,
)

_STORE_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")


def _make_purchase(**overrides: Any) -> dict[str, Any]:
    """テスト用 Purchase 辞書を生成するヘルパー。"""
    base: dict[str, Any] = {
        "purchase_id": str(uuid.uuid4()),
        "store_id": str(_STORE_ID),
        "visit_id": str(uuid.uuid4()),
        "product_category": "アウター",
        "amount": 45000,
        "return_flag": False,
        "return_reason_category": None,
        "return_date": None,
        "customer_id": str(uuid.uuid4()),
    }
    base.update(overrides)
    return base


class TestDetectReturnTrustEvent:
    """返品からの TrustEvent 検出テスト。"""

    # AC-EVT-01: 返品発生で商品信頼のネガティブ TrustEvent が生成される
    def test_返品でネガティブイベント生成(self) -> None:
        """return_flag=True の場合に product/negative の TrustEvent が生成される。"""
        purchase = _make_purchase(
            return_flag=True,
            return_reason_category="品質問題",
            return_date="2026-03-20",
        )
        event = detect_return_trust_event(purchase)
        assert event is not None
        assert event["trust_dimension"] == "product"
        assert event["sentiment"] == "negative"

    # AC-EVT-01: return_flag=false のレコードではイベントが生成されない
    def test_非返品ではイベント生成なし(self) -> None:
        """return_flag=False の場合は None を返す。"""
        purchase = _make_purchase(return_flag=False)
        event = detect_return_trust_event(purchase)
        assert event is None

    # AC-EVT-02: 返品理由カテゴリが severity に正しくマッピングされる — 品質問題
    def test_品質問題のseverityは3(self) -> None:
        """品質問題 → severity=3。"""
        purchase = _make_purchase(
            return_flag=True,
            return_reason_category="品質問題",
        )
        event = detect_return_trust_event(purchase)
        assert event is not None
        assert event["severity"] == 3

    # AC-EVT-02: 返品理由カテゴリが severity に正しくマッピングされる — 説明との相違
    def test_説明との相違のseverityは2(self) -> None:
        """説明との相違 → severity=2。"""
        purchase = _make_purchase(
            return_flag=True,
            return_reason_category="説明との相違",
        )
        event = detect_return_trust_event(purchase)
        assert event is not None
        assert event["severity"] == 2

    # AC-EVT-02: 返品理由カテゴリが severity に正しくマッピングされる — サイズ不一致
    def test_サイズ不一致のseverityは2(self) -> None:
        """サイズ不一致 → severity=2。"""
        purchase = _make_purchase(
            return_flag=True,
            return_reason_category="サイズ不一致",
        )
        event = detect_return_trust_event(purchase)
        assert event is not None
        assert event["severity"] == 2

    # AC-EVT-02: 返品理由カテゴリが severity に正しくマッピングされる — 気が変わった
    def test_気が変わったのseverityは1(self) -> None:
        """気が変わった → severity=1。"""
        purchase = _make_purchase(
            return_flag=True,
            return_reason_category="気が変わった",
        )
        event = detect_return_trust_event(purchase)
        assert event is not None
        assert event["severity"] == 1

    # AC-EVT-02: 返品理由カテゴリが severity に正しくマッピングされる — その他
    def test_その他のseverityは1(self) -> None:
        """その他 → severity=1。"""
        purchase = _make_purchase(
            return_flag=True,
            return_reason_category="その他",
        )
        event = detect_return_trust_event(purchase)
        assert event is not None
        assert event["severity"] == 1

    # AC-EVT-03: generated_by = "rule" / confidence = 1.0 が設定される
    def test_generated_byとconfidence(self) -> None:
        """ルールベース生成のメタデータが正しく設定される。"""
        purchase = _make_purchase(
            return_flag=True,
            return_reason_category="品質問題",
        )
        event = detect_return_trust_event(purchase)
        assert event is not None
        assert event["generated_by"] == "rule"
        assert event["confidence"] == 1.0

    # AC-EVT-04: confidence チェックは不要だが needs_review = False が設定される
    def test_needs_reviewはFalse(self) -> None:
        """ルールベースのため needs_review = False。"""
        purchase = _make_purchase(
            return_flag=True,
            return_reason_category="品質問題",
        )
        event = detect_return_trust_event(purchase)
        assert event is not None
        assert event["needs_review"] is False

    # AC-EVT-01: 匿名来店（customer_id=NULL）でもイベントが生成される
    def test_匿名来店でもイベント生成(self) -> None:
        """customer_id=None の場合でも返品イベントは生成される。"""
        purchase = _make_purchase(
            return_flag=True,
            return_reason_category="品質問題",
            customer_id=None,
        )
        event = detect_return_trust_event(purchase)
        assert event is not None
        assert event["trust_dimension"] == "product"


class TestGenerateTrustEventsFromPurchase:
    """Purchase リスト全体からの TrustEvent 一括生成テスト。"""

    # AC-EVT-01: 返品のみイベント生成される
    def test_返品のみイベント生成(self) -> None:
        """返品1件 + 非返品2件 → イベント1件。"""
        purchases = [
            _make_purchase(return_flag=False),
            _make_purchase(
                return_flag=True,
                return_reason_category="品質問題",
            ),
            _make_purchase(return_flag=False),
        ]
        events = generate_trust_events_from_purchase(purchases)
        assert len(events) == 1
        assert events[0]["trust_dimension"] == "product"
        assert events[0]["sentiment"] == "negative"

    # AC-EVT-01: 返品なしの場合は空リスト
    def test_返品なしで空リスト(self) -> None:
        """返品がない場合はイベントリストが空。"""
        purchases = [
            _make_purchase(return_flag=False),
            _make_purchase(return_flag=False),
        ]
        events = generate_trust_events_from_purchase(purchases)
        assert len(events) == 0
