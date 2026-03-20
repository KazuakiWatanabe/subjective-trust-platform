"""スタッフ（Staff）モデル。

設計書 §4.3 に基づくスタッフマスタテーブル。

Note:
    スタッフ個人を特定できる集計クエリの実装は Phase 1 では禁止（§8.2）。
"""

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from src.python.domain.models.base import Base


class Staff(Base):
    """スタッフマスタ。"""

    __tablename__ = "staff"

    staff_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("store.store_id"))
    staff_name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
