"""记忆层三张表：修改记录、推文草稿、站点渲染统计（迁移 0008）。"""
from __future__ import annotations

from datetime import date, datetime
import uuid

from sqlalchemy import (
    Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class EditRecord(Base):
    """人工修改记录。target_type=category 时 target_id 为 article_id。"""

    __tablename__ = "edit_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    target_type: Mapped[str] = mapped_column(String(16), nullable=False)  # category | tweet
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    field: Mapped[str] = mapped_column(String(32), nullable=False)
    old_value: Mapped[object | None] = mapped_column(JSONB)
    new_value: Mapped[object | None] = mapped_column(JSONB)
    editor: Mapped[str | None] = mapped_column(String(64))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_edit_records_target", "target_id", "created_at"),
        Index("idx_edit_records_type", "target_type", "created_at"),
    )


class TweetDraft(Base):
    """推文草稿。AI 首次生成写 v1；每次保存写新版本，不覆盖。"""

    __tablename__ = "tweet_drafts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    article_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("articles.id"), nullable=False
    )
    title: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)
    template: Mapped[str | None] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("article_id", "version", name="uq_tweet_drafts_article_version"),
        Index("idx_tweet_drafts_article_version", "article_id", "version"),
    )


class SiteRenderStat(Base):
    """站点渲染成败统计，按 (domain, stat_date) 按天 upsert 累加。

    ab_ok / ab_fail 由兜底路由计划写入，本期只建列。
    """

    __tablename__ = "site_render_stats"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    domain: Mapped[str] = mapped_column(String(512), nullable=False)
    stat_date: Mapped[date] = mapped_column(Date, nullable=False)

    ff_ok: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    ff_fail: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    pw_ok: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    pw_fail: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    ab_ok: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    ab_fail: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    __table_args__ = (
        UniqueConstraint("domain", "stat_date", name="uq_site_render_stats_domain_date"),
        Index("idx_site_render_stats_domain_date", "domain", "stat_date"),
    )
