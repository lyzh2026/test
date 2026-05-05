"""articles 表（PRD 4.2）。"""
from __future__ import annotations

from datetime import date, datetime
import uuid

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, String, Text, false, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("crawler_tasks.id"), nullable=True)

    original_title: Mapped[str] = mapped_column(String(512), nullable=False)
    source_unit: Mapped[str | None] = mapped_column(String(256))
    original_link: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    publish_date: Mapped[date] = mapped_column(Date, nullable=False)
    raw_content: Mapped[str | None] = mapped_column(Text)

    ai_analysis: Mapped["AIAnalysis | None"] = relationship("AIAnalysis", uselist=False)

    status: Mapped[str] = mapped_column(String(32), default="raw", nullable=False)
    failed_reason: Mapped[str | None] = mapped_column(Text)
    bookmarked: Mapped[bool] = mapped_column(Boolean, server_default=false(), default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("idx_articles_publish_date", "publish_date"),
        Index("idx_articles_status", "status"),
        Index("idx_articles_source_unit", "source_unit"),
    )
