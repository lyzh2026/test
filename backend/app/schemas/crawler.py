from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl, model_validator


class CrawlerTaskCreate(BaseModel):
    task_name: str | None = None
    target_date: date
    date_to: date | None = None
    url_list: list[str] = Field(default=[], max_length=100)
    direct_urls: list[str] = Field(default=[], max_length=100)
    callback_url: HttpUrl | None = None

    @model_validator(mode="after")
    def _require_at_least_one_url(self):
        if not self.url_list and not self.direct_urls:
            raise ValueError("url_list 和 direct_urls 至少需要提供一个")
        return self


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


class AIBrowseRequest(BaseModel):
    urls: list[str] = Field(min_length=1, max_length=20)


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
