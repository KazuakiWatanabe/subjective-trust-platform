"""POS 日次連携バッチのユニットテスト。

対象: src/python/domain/services/pos_sync.py
テスト観点: POS データ取り込み、返品時の TrustEvent 自動生成、冪等性

Note:
    実際の POS システム接続は行わない。モックデータで検証する。
"""

import json
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from src.python.domain.services.pos_sync import (
    PosSyncService,
    PosTransaction,
)

_FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "pos_mock_data.json"


def _load_mock_data() -> list[dict[str, Any]]:
    """モック POS データを読み込む。"""
    with open(_FIXTURE_PATH, encoding="utf-8") as f:
        return json.load(f)


class TestPosTransaction:
    """POS トランザクションデータのパース。"""

    # AC-01: 購入金額・商品カテゴリ・値引額・返品が取得される
    def test_正常なPOSデータがパースできる(self) -> None:
        """PosTransaction が正しくフィールドを保持する。"""
        data = _load_mock_data()
        txn = PosTransaction.model_validate(data[0])
        assert txn.product_category == "アウター"
        assert txn.amount == 45000
        assert txn.discount_amount == 0
        assert txn.return_flag is False

    # AC-01: 返品データが正しくパースされる
    def test_返品データがパースできる(self) -> None:
        """return_flag=True のデータが正しく読み込まれる。"""
        data = _load_mock_data()
        txn = PosTransaction.model_validate(data[1])
        assert txn.return_flag is True
        assert txn.return_reason_category == "品質不満"
        assert txn.return_date == date(2026, 3, 20)


class TestPosSyncService:
    """POS 同期サービスのテスト。"""

    # AC-02: 返品発生時に TrustEvent（商品信頼・ネガティブ）が自動生成される
    def test_返品でTrustEventが生成される(self) -> None:
        """return_flag=True の場合に product/negative の TrustEvent が生成される。"""
        service = PosSyncService()
        data = _load_mock_data()
        transactions = [PosTransaction.model_validate(d) for d in data]

        purchases, events = service.process_transactions(transactions)
        # 返品は 1 件なので TrustEvent も 1 件
        assert len(events) == 1
        event = events[0]
        assert event["trust_dimension"] == "product"
        assert event["sentiment"] == "negative"
        assert event["source_type"] == "pos"
        assert event["generated_by"] == "rule"

    # AC-02: 返品なしの場合は TrustEvent が生成されない
    def test_返品なしでTrustEventは生成されない(self) -> None:
        """return_flag=False のトランザクションのみの場合、TrustEvent は空。"""
        service = PosSyncService()
        data = _load_mock_data()
        # 返品なしのデータのみ
        non_return = [PosTransaction.model_validate(d) for d in data if not d["return_flag"]]

        purchases, events = service.process_transactions(non_return)
        assert len(events) == 0
        assert len(purchases) == 2

    # AC-01: 全トランザクションが Purchase 辞書として返される
    def test_全トランザクションがPurchaseとして返される(self) -> None:
        """process_transactions が全件を Purchase 辞書リストとして返す。"""
        service = PosSyncService()
        data = _load_mock_data()
        transactions = [PosTransaction.model_validate(d) for d in data]

        purchases, events = service.process_transactions(transactions)
        assert len(purchases) == 3

    # AC-03: 冪等性 — 同一 pos_transaction_id の再処理でデータが重複しない
    def test_冪等性_同一データの再処理で重複しない(self) -> None:
        """同じトランザクションを 2 回処理しても結果が同じ。"""
        service = PosSyncService()
        data = _load_mock_data()
        transactions = [PosTransaction.model_validate(d) for d in data]

        # 1 回目
        purchases1, events1 = service.process_transactions(transactions)
        # 2 回目（同一データ）
        purchases2, events2 = service.process_transactions(transactions)

        # processed_ids により重複が防がれる
        assert len(purchases2) == 0
        assert len(events2) == 0

    # AC-03: 冪等性 — 新規データのみ処理される
    def test_冪等性_新規データのみ処理される(self) -> None:
        """既処理データと新規データの混在で新規のみ処理される。"""
        service = PosSyncService()
        data = _load_mock_data()
        transactions = [PosTransaction.model_validate(d) for d in data]

        # 1 回目: 全件処理
        service.process_transactions(transactions)

        # 2 回目: 1 件追加
        new_txn = PosTransaction(
            pos_transaction_id="POS-2026-03-19-NEW",
            store_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
            visit_id=uuid.UUID("aaaa4444-4444-4444-4444-444444444444"),
            product_category="シューズ",
            amount=28000,
            discount_amount=0,
            purchased_at=datetime(2026, 3, 19, 17, 0, tzinfo=timezone.utc),
            return_flag=False,
        )
        purchases, events = service.process_transactions(transactions + [new_txn])
        assert len(purchases) == 1  # 新規の 1 件のみ
        assert purchases[0]["product_category"] == "シューズ"
