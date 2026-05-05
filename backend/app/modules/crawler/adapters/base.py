"""SpiderAdapter 抽象基类（PRD 2.1.10）。"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date


@dataclass
class RenderedPage:
    url: str
    final_url: str
    html: str
    title: str | None = None


@dataclass
class ArticleDraft:
    original_title: str
    raw_content: str
    source_unit: str | None = None
    publish_date: date | None = None
    confidence: float = 1.0
    extra: dict = field(default_factory=dict)


class SpiderAdapter(ABC):
    name: str = "base"

    @abstractmethod
    async def extract(self, page: RenderedPage) -> ArticleDraft | None:
        ...

    def validate(self, draft: ArticleDraft | None) -> bool:
        if not draft:
            return False
        if not draft.original_title or not draft.original_title.strip():
            return False
        if not draft.raw_content or len(draft.raw_content.strip()) < 200:
            return False
        return True
