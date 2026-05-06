"""add system_config table for runtime settings.

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "system_config",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_system_config_key", "system_config", ["key"], unique=True)

    # 插入默认 AI 配置（Kimi/Moonshot）
    op.execute("""
        INSERT INTO system_config (key, value) VALUES (
            'ai_provider',
            '{"provider": "kimi", "api_key": "", "base_url": "https://api.moonshot.cn/v1", "model": "moonshot-v1-32k"}'::jsonb
        )
    """)


def downgrade() -> None:
    op.drop_index("ix_system_config_key", table_name="system_config")
    op.drop_table("system_config")
