"""add_purchase_pos_transaction_id

POS 日次バッチの冪等性を保証するため、Purchase テーブルに
pos_transaction_id カラムを追加する。

Note:
    return_flag / return_reason_category / return_date は
    初期スキーマ (4250e437ab00) で作成済みのため本マイグレーションでは扱わない。

Revision ID: 0004_purchase_pos_txn
Revises: 0003_review_ext_cols
Create Date: 2026-03-22
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004_purchase_pos_txn"
down_revision: Union[str, None] = "0003_review_ext_cols"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "purchase",
        sa.Column("pos_transaction_id", sa.String(100), nullable=True),
    )
    op.create_unique_constraint(
        "uq_purchase_pos_transaction_id",
        "purchase",
        ["pos_transaction_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_purchase_pos_transaction_id", "purchase", type_="unique")
    op.drop_column("purchase", "pos_transaction_id")
