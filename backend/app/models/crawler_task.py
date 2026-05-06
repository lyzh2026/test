"""crawler_tasks 表（PRD 4.2）。"""
from datetime import date, datetime
import uuid

from sqlalchemy import Date, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CrawlerTask(Base):
    __tablename__ = "crawler_tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_name: Mapped[str | None] = mapped_column(String(256))
    target_date: Mapped[date] = mapped_column(Date, nullable=False)
    date_to: Mapped[date | None] = mapped_column(Date)
    url_list: Mapped[list] = mapped_column(JSONB, nullable=False)

    total_urls: Mapped[int] = mapped_column(Integer, default=0)
    completed_urls: Mapped[int] = mapped_column(Integer, default=0)
    failed_urls: Mapped[int] = mapped_column(Integer, default=0)
    failed_details: Mapped[list] = mapped_column(JSONB, default=list)

    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    callback_url: Mapped[str | None] = mapped_column(Text)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
