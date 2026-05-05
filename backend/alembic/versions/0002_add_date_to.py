"""add date_to to crawler_tasks for range-based date filtering.

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-02 00:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("crawler_tasks", sa.Column("date_to", sa.Date))


def downgrade() -> None:
    op.drop_column("crawler_tasks", "date_to")
