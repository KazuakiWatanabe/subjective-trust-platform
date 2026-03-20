"""問い合わせ・苦情（ComplaintInquiry）モデル。

設計書 §4.3 に基づく顧客問い合わせテーブル。
trust_dimension は AI 分類結果を格納する。

Note:
    問い合わせ DB から日次で連携されるデータ。
"""

import datetime
import uuid

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.python.domain.models.base import Base


class ComplaintInquiry(Base):
    """問い合わせ・苦情。"""

    __tablename__ = "complaint_inquiry"

    complaint_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("customer.customer_id"), nullable=True
    )
    store_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("store.store_id"))
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_time_hours: Mapped[int | None] = mapped_column(nullable=True)
    resolution_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    trust_dimension: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reported_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
