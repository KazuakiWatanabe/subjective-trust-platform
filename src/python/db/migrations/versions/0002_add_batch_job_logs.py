"""add_batch_job_logs

Revision ID: 0002_batch_job_logs
Revises: 4250e437ab00
Create Date: 2026-03-21
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_batch_job_logs"
down_revision: Union[str, None] = "4250e437ab00"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "batch_job_logs",
        sa.Column("log_id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("job_name", sa.String(100), nullable=False),
        sa.Column("store_id", sa.UUID(), nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("processed_count", sa.Integer(), server_default="0"),
        sa.Column("api_cost_jpy", sa.Numeric(10, 2), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index(
        "idx_batch_job_logs_job_name_started",
        "batch_job_logs",
        ["job_name", "started_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_batch_job_logs_job_name_started")
    op.drop_table("batch_job_logs")
