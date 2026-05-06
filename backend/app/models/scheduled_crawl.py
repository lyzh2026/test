"""scheduled_crawl 表 — 定时爬取任务配置。"""
from datetime import datetime
import uuid

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ScheduledCrawl(Base):
    __tablename__ = "scheduled_crawl"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    url_list: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    weekdays: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)  # 0=Sun..6=Sat
    email_config_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_task_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
