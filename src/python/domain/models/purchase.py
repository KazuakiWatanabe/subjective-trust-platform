"""購入（Purchase）モデル。

設計書 §4.3 に基づく購入明細テーブル。
POS 日次連携バッチ（T-11）でデータを取り込む。

Note:
    return_flag が True の場合、TrustEvent（商品信頼・ネガティブ）が自動生成される。
"""

import datetime
import decimal
import uuid

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.python.domain.models.base import Base


class Purchase(Base):
    """購入明細。"""

    __tablename__ = "purchase"

    purchase_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    visit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("visit.visit_id"))
    product_category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    amount: Mapped[decimal.Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    discount_amount: Mapped[decimal.Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    purchased_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    return_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    return_reason_category: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )
    return_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    pos_transaction_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("pos_transaction_id", name="uq_purchase_pos_transaction_id"),
    )
