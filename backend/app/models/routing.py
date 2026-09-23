"""渲染路由与兜底队列（迁移 0009）。"""
from __future__ import annotations

from datetime import datetime
import uuid

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class RenderRoutePolicy(Base):
    """渲染路由策略。与 allowed_domains 无关：那个管 URL 来源校验，这个管渲染路径。"""

    __tablename__ = "render_route_policy"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    domain: Mapped[str] = mapped_column(String(512), nullable=False)
    mode: Mapped[str] = mapped_column(String(24), nullable=False)  # auto | always_aibrowser | always_static
    source: Mapped[str] = mapped_column(String(16), nullable=False)  # manual | auto
    reason: Mapped[str | None] = mapped_column(Text)
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("domain", name="uq_render_route_policy_domain"),
    )


class FallbackQueue(Base):
    """待 AI Browser 兜底的 URL 队列。落库以便重启后续跑（spec §6.2）。"""

    __tablename__ = "fallback_queue"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crawler_tasks.id"), nullable=False
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    fail_reason: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")  # pending | done | ok | failed

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("idx_fallback_queue_task_state", "task_id", "state"),
        Index("idx_fallback_queue_state_created", "state", "created_at"),
    )
