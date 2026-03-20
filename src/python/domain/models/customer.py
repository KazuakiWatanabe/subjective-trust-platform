"""顧客（Customer）モデル。

設計書 §4.3 に基づく顧客テーブル。
consent_status で個人情報取り扱い同意を管理する。

Note:
    trait_summary は Phase 2 で AI 蓄積による Trait 要約を格納する。
    Claude API / Bedrock への個人識別情報の送信は禁止（§8.3）。
"""

import datetime
import uuid

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.python.domain.models.base import Base


class Customer(Base):
    """顧客マスタ。"""

    __tablename__ = "customer"

    customer_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    consent_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    consent_updated_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # TODO(phase2): C# 移管予定 — trait_summary は AI 蓄積による Trait 要約
    trait_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
