"""外部レビュー（ReviewExternal）モデル。

設計書 §4.3 / §5.3 に基づく外部レビューテーブル。
Google ビジネスプロフィール等から日次で連携される。

Note:
    review_text は AI 解釈パイプラインの入力対象。
"""

import datetime
import uuid

from sqlalchemy import DateTime, ForeignKey, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.python.domain.models.base import Base


class ReviewExternal(Base):
    """外部レビュー（Google ビジネスプロフィール等）。"""

    __tablename__ = "review_external"

    review_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    store_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("store.store_id"))
    platform: Mapped[str] = mapped_column(String(30))
    rating: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    review_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    posted_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
