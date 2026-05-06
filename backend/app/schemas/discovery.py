"""Discovery 请求/响应模型。"""
from datetime import date

from pydantic import BaseModel, Field, HttpUrl


class DiscoveryScanRequest(BaseModel):
    entry_url: str = Field(..., min_length=1)
    max_depth: int = Field(default=2, ge=1, le=3)
    max_links: int = Field(default=50, ge=1, le=200)
    enable_pagination: bool = Field(default=True)
    max_pages: int = Field(default=5, ge=1, le=50)


class DiscoveryTaskCreate(BaseModel):
    entry_url: str = Field(..., min_length=1)
    target_date: date
    date_to: date | None = None
    task_name: str | None = None
    max_depth: int = Field(default=2, ge=1, le=3)
    max_links: int = Field(default=50, ge=1, le=200)
    enable_pagination: bool = Field(default=True)
    max_pages: int = Field(default=5, ge=1, le=50)
