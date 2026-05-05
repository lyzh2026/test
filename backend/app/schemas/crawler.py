from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl


class CrawlerTaskCreate(BaseModel):
    task_name: str | None = None
    target_date: date
    date_to: date | None = None
    url_list: list[str] = Field(min_length=1, max_length=100)
    callback_url: HttpUrl | None = None
    priority: int = 1


class CrawlerTaskResponse(BaseModel):
    task_id: str
    status: str
    total_urls: int
    completed_urls: int
    failed_urls: int
    failed_details: list[dict[str, Any]] = []
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    task_name: str | None = None
    target_date: date
    date_to: date | None = None


class BatchDeleteRequest(BaseModel):
    task_ids: list[str] = Field(min_length=1, max_length=100)


class TaskListItem(BaseModel):
    task_id: str
    task_name: str | None
    status: str
    total_urls: int
    completed_urls: int
    failed_urls: int
    target_date: date
    date_to: date | None = None
    created_at: datetime
