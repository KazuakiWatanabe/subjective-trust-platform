"""信頼イベント（TrustEvent）モデル。

設計書 §4.2 に基づく信頼イベントテーブル。
多態的に複数ソース（visit/feedback/complaint/review/pos）を参照する。

Note:
    AI 解釈結果を書き込む際は generated_by = "ai" を記録し、
    confidence < 0.6 の場合は needs_review = True を自動セットすること。
    trait_signal / state_signal / meta_signal は Phase 2 で活用する。
"""

import datetime
import decimal
import uuid

from sqlalchemy import (
    ARRAY,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    CheckConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.python.domain.models.base import Base


class TrustEvent(Base):
    """信頼イベント。AI 解釈・ルールベース・手動の 3 経路で生成される。"""

    __tablename__ = "trust_event"

    trust_event_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    store_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("store.store_id"))
    source_type: Mapped[str] = mapped_column(String(30))
    source_id: Mapped[uuid.UUID] = mapped_column()
    trust_dimension: Mapped[str] = mapped_column(String(20))
    sentiment: Mapped[str] = mapped_column(String(10))
    severity: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    theme_tags: Mapped[list[str] | None] = mapped_column(
        ARRAY(String), nullable=True
    )
    generated_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    interpretation: Mapped[str | None] = mapped_column(Text, nullable=True)
    trait_signal: Mapped[str | None] = mapped_column(Text, nullable=True)
    state_signal: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta_signal: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[decimal.Decimal | None] = mapped_column(
        Numeric(3, 2), nullable=True
    )
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewed_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    generated_by: Mapped[str | None] = mapped_column(String(20), nullable=True)
    detected_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index(
            "idx_trust_event_store_dim_date",
            "store_id",
            "trust_dimension",
            "detected_at",
        ),
        CheckConstraint(
            "severity >= 1 AND severity <= 3",
            name="severity_range",
        ),
    )
