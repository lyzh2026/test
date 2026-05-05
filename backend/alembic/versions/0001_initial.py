"""initial schema: articles / ai_analysis / crawler_tasks / allowed_domains.

Revision ID: 0001
Revises:
Create Date: 2026-04-26 00:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # crawler_tasks
    op.create_table(
        "crawler_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("task_name", sa.String(256)),
        sa.Column("target_date", sa.Date, nullable=False),
        sa.Column("url_list", postgresql.JSONB, nullable=False),
        sa.Column("total_urls", sa.Integer, server_default="0"),
        sa.Column("completed_urls", sa.Integer, server_default="0"),
        sa.Column("failed_urls", sa.Integer, server_default="0"),
        sa.Column("failed_details", postgresql.JSONB, server_default="[]"),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("callback_url", sa.Text),
        sa.Column("priority", sa.Integer, server_default="1"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_crawler_tasks_status", "crawler_tasks", ["status", "created_at"])

    # articles
    op.create_table(
        "articles",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("crawler_tasks.id"), nullable=True),
        sa.Column("original_title", sa.String(512), nullable=False),
        sa.Column("source_unit", sa.String(256)),
        sa.Column("original_link", sa.Text, nullable=False, unique=True),
        sa.Column("publish_date", sa.Date, nullable=False),
        sa.Column("raw_content", sa.Text),
        sa.Column("status", sa.String(32), nullable=False, server_default="raw"),
        sa.Column("failed_reason", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_articles_publish_date", "articles", ["publish_date"])
    op.create_index("idx_articles_status", "articles", ["status"])
    op.create_index("idx_articles_source_unit", "articles", ["source_unit"])

    # ai_analysis
    op.create_table(
        "ai_analysis",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("article_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("articles.id"), unique=True, nullable=False),
        sa.Column("categories", postgresql.JSONB, server_default="[]"),
        sa.Column("summary", sa.Text),
        sa.Column("cover_image", sa.Text),
        sa.Column("keywords", postgresql.JSONB, server_default="[]"),
        sa.Column("model_used", sa.String(64)),
        sa.Column("processing_time_ms", sa.Integer),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "idx_ai_analysis_categories", "ai_analysis", ["categories"], postgresql_using="gin"
    )

    # allowed_domains
    op.create_table(
        "allowed_domains",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("domain_pattern", sa.String(512), nullable=False),
        sa.Column("match_mode", sa.String(16), nullable=False, server_default="suffix"),
        sa.Column("enabled", sa.Boolean, server_default=sa.true()),
        sa.Column("auto_added", sa.Boolean, server_default=sa.false()),
        sa.Column("source", sa.String(32), server_default="manual"),
        sa.Column("remark", sa.Text),
        sa.Column("created_by", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )
    op.create_index("idx_allowed_domains_enabled", "allowed_domains", ["enabled", "deleted_at"])


def downgrade() -> None:
    op.drop_index("idx_allowed_domains_enabled", table_name="allowed_domains")
    op.drop_table("allowed_domains")
    op.drop_index("idx_ai_analysis_categories", table_name="ai_analysis")
    op.drop_table("ai_analysis")
    op.drop_index("idx_articles_source_unit", table_name="articles")
    op.drop_index("idx_articles_status", table_name="articles")
    op.drop_index("idx_articles_publish_date", table_name="articles")
    op.drop_table("articles")
    op.drop_index("idx_crawler_tasks_status", table_name="crawler_tasks")
    op.drop_table("crawler_tasks")
