"""memory layer: edit_records, tweet_drafts, site_render_stats.

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "edit_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_type", sa.String(16), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("field", sa.String(32), nullable=False),
        sa.Column("old_value", postgresql.JSONB(), nullable=True),
        sa.Column("new_value", postgresql.JSONB(), nullable=True),
        sa.Column("editor", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_edit_records_target", "edit_records", ["target_id", "created_at"])
    op.create_index("idx_edit_records_type", "edit_records", ["target_type", "created_at"])

    op.create_table(
        "tweet_drafts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("article_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("template", sa.String(64), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["article_id"], ["articles.id"]),
        sa.UniqueConstraint("article_id", "version", name="uq_tweet_drafts_article_version"),
    )
    op.create_index("idx_tweet_drafts_article_version", "tweet_drafts", ["article_id", "version"])

    op.create_table(
        "site_render_stats",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("domain", sa.String(512), nullable=False),
        sa.Column("stat_date", sa.Date(), nullable=False),
        sa.Column("ff_ok", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ff_fail", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pw_ok", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pw_fail", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ab_ok", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ab_fail", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("domain", "stat_date", name="uq_site_render_stats_domain_date"),
    )
    op.create_index("idx_site_render_stats_domain_date", "site_render_stats", ["domain", "stat_date"])


def downgrade() -> None:
    op.drop_index("idx_site_render_stats_domain_date", table_name="site_render_stats")
    op.drop_table("site_render_stats")
    op.drop_index("idx_tweet_drafts_article_version", table_name="tweet_drafts")
    op.drop_table("tweet_drafts")
    op.drop_index("idx_edit_records_type", table_name="edit_records")
    op.drop_index("idx_edit_records_target", table_name="edit_records")
    op.drop_table("edit_records")
