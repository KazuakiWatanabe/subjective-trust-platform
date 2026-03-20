"""店舗（Store）モデル。

設計書 §4.2 に基づく店舗マスタテーブル。
直営/FC/ポップアップの店舗情報を管理する。

Note:
    status は active/closed/renovating の 3 値。
"""

import datetime
import uuid

from sqlalchemy import Date, String
from sqlalchemy.orm import Mapped, mapped_column

from src.python.domain.models.base import Base


class Store(Base):
    """店舗マスタ。"""

    __tablename__ = "store"

    store_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    store_name: Mapped[str] = mapped_column(String(100))
    area: Mapped[str] = mapped_column(String(50))
    format_type: Mapped[str] = mapped_column(String(30))
    open_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
