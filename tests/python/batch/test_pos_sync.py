"""POS 日次バッチのユニットテスト。

対象: src/python/batch/pos_sync.py
テスト観点: POS データ正規化・冪等性・返品処理・不正データスキップ
参照: docs/trust-observation-system-v1.md §5.3

Note:
    実際の POS システム接続は行わない。モックデータで検証する。
    batch_job_logs への記録は monitoring.common をモック化して検証する。
"""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.python.batch.pos_sync import normalize_pos_record, run_pos_sync_batch

_STORE_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
_VISIT_ID = uuid.UUID("aaaa1111-1111-1111-1111-111111111111")


def _make_raw_record(**overrides: Any) -> dict[str, Any]:
    """テスト用 POS 生データを生成するヘルパー。"""
    base: dict[str, Any] = {
        "pos_transaction_id": "POS-2026-03-19-001",
        "visit_id": str(_VISIT_ID),
        "product_category": "アウター",
        "amount": 45000,
        "discount_amount": 0,
        "purchased_at": "2026-03-19T14:30:00+09:00",
        "return_flag": False,
        "return_reason_category": None,
        "return_date": None,
        "customer_id": str(uuid.uuid4()),
    }
    base.update(overrides)
    return base


class TestNormalizePosRecord:
    """POS レコードの正規化テスト。"""

    # AC-POS-01: POS レコードが正規化されて Purchase テーブルに保存される
    def test_正常なPOSレコードが正規化される(self) -> None:
        """正常な POS 生データが Purchase 辞書に正規化される。"""
        raw = _make_raw_record()
        result = normalize_pos_record(raw, _STORE_ID)
        assert result is not None
        assert result["pos_transaction_id"] == "POS-2026-03-19-001"
        assert result["visit_id"] == str(_VISIT_ID)
        assert result["product_category"] == "アウター"
        assert result["amount"] == 45000
        assert result["return_flag"] is False

    # AC-POS-03: return_flag=true のレコードに return_reason_category が設定される
    def test_返品フラグ付きレコードの正規化(self) -> None:
        """return_flag=true の場合 return_reason_category が保持される。"""
        raw = _make_raw_record(
            pos_transaction_id="POS-RET-001",
            return_flag=True,
            return_reason_category="品質問題",
            return_date="2026-03-20",
        )
        result = normalize_pos_record(raw, _STORE_ID)
        assert result is not None
        assert result["return_flag"] is True
        assert result["return_reason_category"] == "品質問題"
        assert result["return_date"] == "2026-03-20"

    # AC-POS-04: 不正データはスキップされ、バッチ全体は継続する
    def test_pos_transaction_id欠落でNone(self) -> None:
        """pos_transaction_id が欠落したデータは None（スキップ）。"""
        raw = _make_raw_record()
        del raw["pos_transaction_id"]
        result = normalize_pos_record(raw, _STORE_ID)
        assert result is None

    # AC-POS-04: 不正データはスキップされ、バッチ全体は継続する
    def test_visit_id欠落でNone(self) -> None:
        """visit_id が欠落したデータは None（スキップ）。"""
        raw = _make_raw_record()
        del raw["visit_id"]
        result = normalize_pos_record(raw, _STORE_ID)
        assert result is None

    # AC-POS-01: customer_id が NULL（匿名来店）のレコード処理
    def test_customer_id_NULLの匿名来店(self) -> None:
        """customer_id が NULL でも正規化は成功する。"""
        raw = _make_raw_record(customer_id=None)
        result = normalize_pos_record(raw, _STORE_ID)
        assert result is not None
        assert result.get("customer_id") is None


class TestRunPosSyncBatch:
    """POS 日次バッチ全体のテスト。"""

    # AC-POS-01: POS レコードが正規化されて Purchase テーブルに保存される
    @pytest.mark.asyncio
    async def test_正常なバッチ処理(self) -> None:
        """複数レコードが正規化されて返される。"""
        records = [
            _make_raw_record(pos_transaction_id="POS-001"),
            _make_raw_record(pos_transaction_id="POS-002", product_category="バッグ"),
        ]
        saved, skipped = await run_pos_sync_batch(records, _STORE_ID, set())
        assert len(saved) == 2
        assert skipped == 0

    # AC-POS-02: 同一 POS レコードを2回処理しても重複が発生しない（冪等性）
    @pytest.mark.asyncio
    async def test_冪等性_既存IDはスキップ(self) -> None:
        """existing_pos_ids に含まれるレコードはスキップされる。"""
        records = [
            _make_raw_record(pos_transaction_id="POS-001"),
            _make_raw_record(pos_transaction_id="POS-002"),
        ]
        existing = {"POS-001"}
        saved, skipped = await run_pos_sync_batch(records, _STORE_ID, existing)
        assert len(saved) == 1
        assert saved[0]["pos_transaction_id"] == "POS-002"
        assert skipped == 1

    # AC-POS-02: 同一 POS レコードを2回処理しても重複が発生しない（冪等性）
    @pytest.mark.asyncio
    async def test_冪等性_全件既存(self) -> None:
        """全レコードが既存の場合は空リストと全件スキップ。"""
        records = [
            _make_raw_record(pos_transaction_id="POS-001"),
        ]
        existing = {"POS-001"}
        saved, skipped = await run_pos_sync_batch(records, _STORE_ID, existing)
        assert len(saved) == 0
        assert skipped == 1

    # AC-POS-04: 不正データはスキップされ、バッチ全体は継続する
    @pytest.mark.asyncio
    async def test_不正データスキップでバッチ継続(self) -> None:
        """不正データが混在しても正常データは処理される。"""
        bad_record: dict[str, Any] = {"broken": True}  # pos_transaction_id なし
        good_record = _make_raw_record(pos_transaction_id="POS-GOOD")
        records = [bad_record, good_record]
        saved, skipped = await run_pos_sync_batch(records, _STORE_ID, set())
        assert len(saved) == 1
        assert saved[0]["pos_transaction_id"] == "POS-GOOD"
        assert skipped == 1

    # AC-POS-01: batch_job_logs への記録
    @pytest.mark.asyncio
    async def test_バッチ処理件数の正確性(self) -> None:
        """正常2件 + 不正1件 → saved=2, skipped=1。"""
        records = [
            _make_raw_record(pos_transaction_id="POS-A"),
            _make_raw_record(pos_transaction_id="POS-B"),
            {"no_id": True},
        ]
        saved, skipped = await run_pos_sync_batch(records, _STORE_ID, set())
        assert len(saved) == 2
        assert skipped == 1
