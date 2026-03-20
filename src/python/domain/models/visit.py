"""来店（Visit）モデル。

設計書 §4.2 に基づく来店記録テーブル。
visit_purpose は State 情報として扱う — カラムの意味を変えてはならない。

Note:
    anxiety_tags は ARRAY(VARCHAR) で複数選択に対応する。
    staff_note は Meta 手がかりの主要ソース。
"""

import datetime
import uuid

from sqlalchemy import ARRAY, Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.python.domain.models.base import Base


class Visit(Base):
    """来店記録。"""

    __tablename__ = "visit"

    visit_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("customer.customer_id"), nullable=True
    )
    store_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("store.store_id"))
    staff_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("staff.staff_id"), nullable=True
    )
    visit_datetime: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    # visit_purpose は State 情報として扱う
    visit_purpose: Mapped[str | None] = mapped_column(String(30), nullable=True)
    purchase_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    contact_result: Mapped[str | None] = mapped_column(String(30), nullable=True)
    out_of_stock_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    alternative_proposed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    backorder_offered: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    anxiety_tags: Mapped[list[str] | None] = mapped_column(
        ARRAY(String), nullable=True
    )
    next_visit_likelihood: Mapped[str | None] = mapped_column(String(10), nullable=True)
    staff_note: Mapped[str | None] = mapped_column(Text, nullable=True)
