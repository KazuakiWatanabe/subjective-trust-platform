"""フィードバック（Feedback）モデル。

設計書 §4.2 に基づく来店後ミニアンケート回答テーブル。
1 来店に対して Feedback は 1 件のみ（UNIQUE 制約）。

Note:
    free_comment は AI 解釈パイプラインの主要入力。
    Trait / Meta 手がかりの抽出元となる。
"""

import datetime
import uuid

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, SmallInteger, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.python.domain.models.base import Base


class Feedback(Base):
    """来店後ミニアンケート回答。"""

    __tablename__ = "feedback"

    feedback_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    visit_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("visit.visit_id"), unique=True
    )
    score_consultation: Mapped[int] = mapped_column(SmallInteger)
    score_information: Mapped[int] = mapped_column(SmallInteger)
    score_revisit: Mapped[int] = mapped_column(SmallInteger)
    free_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "score_consultation >= 1 AND score_consultation <= 5",
            name="score_consultation_range",
        ),
        CheckConstraint(
            "score_information >= 1 AND score_information <= 5",
            name="score_information_range",
        ),
        CheckConstraint(
            "score_revisit >= 1 AND score_revisit <= 5",
            name="score_revisit_range",
        ),
    )
