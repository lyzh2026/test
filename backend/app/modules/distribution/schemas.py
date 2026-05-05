"""周报数据结构和 API schemas。"""
from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class ArticleItem(BaseModel):
    title: str
    summary: str
    url: str
    publish_date: date
    source_unit: str


class CategoryGroup(BaseModel):
    name: str
    articles: list[ArticleItem]


class ReportStats(BaseModel):
    total_articles: int
    total_categories: int


class WeeklyReport(BaseModel):
    year_week: str
    date_range_start: date
    date_range_end: date
    categories: list[CategoryGroup]
    stats: ReportStats


# --- API Schemas ---

class ConfigCreate(BaseModel):
    channel_type: str  # email | webhook
    name: str
    config: dict
    enabled: bool = True


class ConfigUpdate(BaseModel):
    name: Optional[str] = None
    config: Optional[dict] = None
    enabled: Optional[bool] = None


class ConfigResponse(BaseModel):
    id: str
    channel_type: str
    name: str
    config: dict
    enabled: bool
    created_at: Optional[datetime]
    updated_at: Optional[datetime]


class LogResponse(BaseModel):
    id: str
    config_name: Optional[str]
    channel_type: Optional[str]
    report_week: str
    status: str
    article_count: int
    category_count: int
    error_message: Optional[str]
    sent_at: Optional[datetime]
