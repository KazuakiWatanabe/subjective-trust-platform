"""POS 日次連携バッチ。

設計書 §5.3 に基づく POS データの日次取り込みサービス。
購入金額・商品カテゴリ・値引額・返品を取得し、
返品発生時に TrustEvent（商品信頼・ネガティブ）を自動生成する。

入力: POS トランザクションデータ（モックまたは実 POS DB）
出力: Purchase 辞書リスト + TrustEvent 辞書リスト
制約:
    - 冪等性を保証する（同一 pos_transaction_id の再処理でデータが重複しない）
    - 実 POS 接続は allowlist に追記するまで禁止

Note:
    Phase 1 ではモックデータで動作確認する。
"""

import logging
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class PosTransaction(BaseModel):
    """POS トランザクションデータ。

    Args:
        pos_transaction_id: POS 側のトランザクション ID（冪等性キー）
        store_id: 店舗 ID
        visit_id: 来店 ID
        product_category: 商品カテゴリ
        amount: 購入金額
        discount_amount: 値引額
        purchased_at: 購入日時
        return_flag: 返品フラグ
        return_reason_category: 返品理由カテゴリ
        return_date: 返品日
    """

    pos_transaction_id: str
    store_id: uuid.UUID
    visit_id: uuid.UUID
    product_category: str | None = None
    amount: Decimal | None = None
    discount_amount: Decimal | None = None
    purchased_at: datetime | None = None
    return_flag: bool = False
    return_reason_category: str | None = None
    return_date: date | None = None


class PosSyncService:
    """POS 日次連携サービス。

    冪等性を processed_ids セットで管理する。
    同一 pos_transaction_id のトランザクションは再処理しない。

    Note:
        Phase 1 ではインメモリの processed_ids で管理。
        本番では DB の処理済みテーブルで管理する。
    """

    def __init__(self) -> None:
        self._processed_ids: set[str] = set()

    def process_transactions(
        self,
        transactions: list[PosTransaction],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """POS トランザクションを処理し、Purchase と TrustEvent を生成する。

        Args:
            transactions: POS トランザクションリスト

        Returns:
            (Purchase 辞書リスト, TrustEvent 辞書リスト) のタプル

        Note:
            同一 pos_transaction_id のデータはスキップされる（冪等性）。
        """
        purchases: list[dict[str, Any]] = []
        events: list[dict[str, Any]] = []

        for txn in transactions:
            # 冪等性チェック
            if txn.pos_transaction_id in self._processed_ids:
                logger.debug(
                    "スキップ（処理済み）: pos_transaction_id=%s",
                    txn.pos_transaction_id,
                )
                continue

            # Purchase 辞書を生成
            purchase = {
                "purchase_id": uuid.uuid4(),
                "visit_id": txn.visit_id,
                "product_category": txn.product_category,
                "amount": txn.amount,
                "discount_amount": txn.discount_amount,
                "purchased_at": txn.purchased_at,
                "return_flag": txn.return_flag,
                "return_reason_category": txn.return_reason_category,
                "return_date": txn.return_date,
            }
            purchases.append(purchase)

            # 返品発生時に TrustEvent を自動生成
            if txn.return_flag:
                event = {
                    "trust_event_id": uuid.uuid4(),
                    "store_id": txn.store_id,
                    "source_type": "pos",
                    "source_id": purchase["purchase_id"],
                    "trust_dimension": "product",
                    "sentiment": "negative",
                    "severity": 2,
                    "theme_tags": [txn.return_reason_category] if txn.return_reason_category else [],
                    "generated_summary": f"商品返品: {txn.product_category or '不明'}",
                    "interpretation": None,
                    "trait_signal": None,
                    "state_signal": None,
                    "meta_signal": None,
                    "confidence": None,
                    "needs_review": False,
                    "reviewed_flag": False,
                    "generated_by": "rule",
                    "detected_at": txn.return_date
                    if txn.return_date
                    else datetime.now(timezone.utc),
                }
                events.append(event)
                logger.info(
                    "返品 TrustEvent 生成: store_id=%s, category=%s",
                    txn.store_id,
                    txn.product_category,
                )

            self._processed_ids.add(txn.pos_transaction_id)

        logger.info(
            "POS 同期完了: %d 件取り込み, %d 件 TrustEvent 生成",
            len(purchases),
            len(events),
        )
        return purchases, events
