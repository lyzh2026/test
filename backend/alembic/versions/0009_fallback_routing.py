"""fallback routing: render_route_policy, fallback_queue, crawler_tasks counters.

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "render_route_policy",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("domain", sa.String(512), nullable=False),
        sa.Column("mode", sa.String(24), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("domain", name="uq_render_route_policy_domain"),
    )

    op.create_table(
        "fallback_queue",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("fail_reason", sa.Text(), nullable=True),
        sa.Column("state", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["task_id"], ["crawler_tasks.id"]),
    )
    op.create_index("idx_fallback_queue_task_state", "fallback_queue", ["task_id", "state"])
    op.create_index("idx_fallback_queue_state_created", "fallback_queue", ["state", "created_at"])

    op.add_column("crawler_tasks", sa.Column("fallback_total", sa.Integer(), nullable=True, server_default="0"))
    op.add_column("crawler_tasks", sa.Column("fallback_done", sa.Integer(), nullable=True, server_default="0"))


def downgrade() -> None:
    op.drop_column("crawler_tasks", "fallback_done")
    op.drop_column("crawler_tasks", "fallback_total")
    op.drop_index("idx_fallback_queue_state_created", table_name="fallback_queue")
    op.drop_index("idx_fallback_queue_task_state", table_name="fallback_queue")
    op.drop_table("fallback_queue")
    op.drop_table("render_route_policy")
