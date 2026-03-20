"""SQLAlchemy 宣言的ベースクラス。

全モデルはこの Base を継承する。Alembic の target_metadata もここから取得する。
"""

import uuid

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Alembic の命名規約（制約名の自動生成ルール）
convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """全モデルの基底クラス。"""

    metadata = MetaData(naming_convention=convention)


class UUIDMixin:
    """UUID 主キーの共通ミックスイン。"""

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
