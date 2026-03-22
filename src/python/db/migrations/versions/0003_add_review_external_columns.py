"""add_review_external_columns

Revision ID: 0003_review_ext_cols
Revises: 0002_batch_job_logs
Create Date: 2026-03-22
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_review_ext_cols"
down_revision: Union[str, None] = "0002_batch_job_logs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("review_external", sa.Column("google_review_id", sa.String(255), unique=True, nullable=True))
    op.add_column("review_external", sa.Column("processed_flag", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("review_external", sa.Column("processed_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.create_index("idx_review_external_processed", "review_external", ["processed_flag", "store_id"])


def downgrade() -> None:
    op.drop_index("idx_review_external_processed")
    op.drop_column("review_external", "processed_at")
    op.drop_column("review_external", "processed_flag")
    op.drop_column("review_external", "google_review_id")
