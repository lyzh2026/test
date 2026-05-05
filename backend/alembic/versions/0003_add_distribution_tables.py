"""add distribution_config / distribution_log tables.

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # distribution_config
    op.create_table(
        "distribution_config",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("channel_type", sa.String(20), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("config", postgresql.JSONB, nullable=False),
        sa.Column("enabled", sa.Boolean, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # distribution_log
    op.create_table(
        "distribution_log",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("config_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("config_name", sa.String(100)),
        sa.Column("channel_type", sa.String(20)),
        sa.Column("report_week", sa.String(10), nullable=False),
        sa.Column("date_range_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("date_range_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("article_count", sa.Integer, server_default="0"),
        sa.Column("category_count", sa.Integer, server_default="0"),
        sa.Column("error_message", sa.Text),
        sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_distribution_log_week", "distribution_log", ["report_week"])
    op.create_index("idx_distribution_log_status", "distribution_log", ["status"])


def downgrade() -> None:
    op.drop_index("idx_distribution_log_status", table_name="distribution_log")
    op.drop_index("idx_distribution_log_week", table_name="distribution_log")
    op.drop_table("distribution_log")
    op.drop_table("distribution_config")
