"""信頼スコアスナップショット（TrustScoreSnapshot）モデル。

設計書 §4.2 に基づく週次信頼スコアのスナップショットテーブル。
5 次元それぞれのスコア（0〜100）と加重平均の overall_score を保持する。

Note:
    is_reliable は event_count が閾値を超過した場合に True になる。
    (target_type, target_id, snapshot_date) にユニーク制約を設定する。
"""
# TODO(phase2): C# 移管予定 — スコアスナップショットの書き込みは C# ドメインサービスに移行する

import datetime
import decimal
import uuid

from sqlalchemy import (
    Boolean,
    Date,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.python.domain.models.base import Base


class TrustScoreSnapshot(Base):
    """週次信頼スコアスナップショット。"""

    __tablename__ = "trust_score_snapshot"

    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    target_type: Mapped[str] = mapped_column(String(20))
    target_id: Mapped[uuid.UUID] = mapped_column()
    snapshot_date: Mapped[datetime.date] = mapped_column(Date)
    product_score: Mapped[decimal.Decimal | None] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    service_score: Mapped[decimal.Decimal | None] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    proposal_score: Mapped[decimal.Decimal | None] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    operation_score: Mapped[decimal.Decimal | None] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    story_score: Mapped[decimal.Decimal | None] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    overall_score: Mapped[decimal.Decimal | None] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    event_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_reliable: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        UniqueConstraint(
            "target_type",
            "target_id",
            "snapshot_date",
            name="uq_trust_score_snapshot",
        ),
    )
