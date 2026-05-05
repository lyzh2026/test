from datetime import date, datetime
from typing import Any

from pydantic import BaseModel


class ArticleListItem(BaseModel):
    id: str
    original_title: str
    source_unit: str | None
    original_link: str
    publish_date: date
    status: str
    summary: str | None = None
    categories: list[dict[str, Any]] = []
    created_at: datetime


class ArticleDetail(BaseModel):
    id: str
    task_id: str | None
    original_title: str
    source_unit: str | None
    original_link: str
    publish_date: date
    raw_content: str | None
    status: str
    failed_reason: str | None
    summary: str | None = None
    categories: list[dict[str, Any]] = []
    keywords: list[str] = []
    cover_image: str | None = None
    model_used: str | None = None
    processing_time_ms: int | None = None
    created_at: datetime


class DailyStatsResponse(BaseModel):
    date: date
    total: int
    categories: list[dict[str, Any]]
    top_sources: list[dict[str, Any]]
