"""Tests for app.modules.crawler.adapters.base: SpiderAdapter, RenderedPage, ArticleDraft."""
from datetime import date
from unittest.mock import AsyncMock

import pytest

from app.modules.crawler.adapters.base import ArticleDraft, RenderedPage, SpiderAdapter


# ======================================================================
# Helper: concrete adapter subclass
# ======================================================================

class ConcreteTestAdapter(SpiderAdapter):
    """Minimal concrete subclass for testing the abstract interface."""
    name = "test_adapter"

    async def extract(self, page: RenderedPage) -> ArticleDraft | None:
        # Dummy implementation — tests verify it runs without error.
        return None


def _create_adapter() -> SpiderAdapter:
    return ConcreteTestAdapter()


# ======================================================================
# SpiderAdapter.validate()
# ======================================================================

class TestSpiderAdapterValidate:
    """validate() returns True only for valid ArticleDraft instances."""

    def test_valid_draft_returns_true(self):
        adapter = _create_adapter()
        draft = ArticleDraft(
            original_title="Valid Title",
            raw_content="x" * 100,
        )
        assert adapter.validate(draft) is True

    def test_valid_draft_with_extra_fields_returns_true(self):
        """A draft with all optional fields set should still pass."""
        adapter = _create_adapter()
        draft = ArticleDraft(
            original_title="Real News Headline",
            raw_content="x" * 250,
            source_unit="cnn",
            publish_date=date(2024, 12, 1),
            confidence=0.85,
            extra={"author": "John"},
        )
        assert adapter.validate(draft) is True

    def test_none_returns_false(self):
        adapter = _create_adapter()
        assert adapter.validate(None) is False

    def test_empty_title_returns_false(self):
        adapter = _create_adapter()
        draft = ArticleDraft(
            original_title="",
            raw_content="x" * 100,
        )
        assert adapter.validate(draft) is False

    def test_whitespace_only_title_returns_false(self):
        adapter = _create_adapter()
        draft = ArticleDraft(
            original_title="   \t  \n  ",
            raw_content="x" * 100,
        )
        assert adapter.validate(draft) is False

    def test_content_shorter_than_100_chars_returns_false(self):
        adapter = _create_adapter()
        draft = ArticleDraft(
            original_title="Valid Title",
            raw_content="x" * 99,
        )
        assert adapter.validate(draft) is False

    def test_content_exactly_100_chars_returns_true(self):
        adapter = _create_adapter()
        draft = ArticleDraft(
            original_title="Valid Title",
            raw_content="x" * 100,
        )
        assert adapter.validate(draft) is True

    def test_empty_content_returns_false(self):
        adapter = _create_adapter()
        draft = ArticleDraft(
            original_title="Valid Title",
            raw_content="",
        )
        assert adapter.validate(draft) is False

    def test_whitespace_only_content_returns_false(self):
        """Content with only whitespace is shorter than 100 chars after strip."""
        adapter = _create_adapter()
        draft = ArticleDraft(
            original_title="Valid Title",
            raw_content="   \t   ",
        )
        assert adapter.validate(draft) is False


# ======================================================================
# Concrete adapter extract() interface
# ======================================================================

class TestConcreteAdapterExtract:
    """A concrete SpiderAdapter subclass can run extract() without error."""

    @pytest.mark.asyncio
    async def test_extract_runs_without_error(self):
        adapter = _create_adapter()
        page = RenderedPage(
            url="https://example.com/article",
            final_url="https://example.com/article",
            html="<html><body><article>Content</article></body></html>",
            title="Example Article",
        )
        result = await adapter.extract(page)
        assert result is None  # our dummy returns None

    @pytest.mark.asyncio
    async def test_extract_accepts_minimal_page(self):
        adapter = _create_adapter()
        page = RenderedPage(
            url="https://example.com/article",
            final_url="https://example.com/article",
            html="<html></html>",
        )
        result = await adapter.extract(page)
        assert result is None


# ======================================================================
# RenderedPage dataclass
# ======================================================================

class TestRenderedPage:
    """RenderedPage dataclass construction."""

    def test_create_with_all_fields(self):
        page = RenderedPage(
            url="https://example.com/page",
            final_url="https://example.com/redirected",
            html="<html><body>Hello</body></html>",
            title="Example Page",
        )
        assert page.url == "https://example.com/page"
        assert page.final_url == "https://example.com/redirected"
        assert page.html == "<html><body>Hello</body></html>"
        assert page.title == "Example Page"

    def test_create_with_minimal_fields(self):
        page = RenderedPage(
            url="https://example.com/page",
            final_url="https://example.com/page",
            html="<html></html>",
        )
        assert page.url == "https://example.com/page"
        assert page.final_url == "https://example.com/page"
        assert page.html == "<html></html>"
        assert page.title is None

    def test_fields_are_mutable(self):
        page = RenderedPage(
            url="url_a",
            final_url="url_b",
            html="<html>old</html>",
        )
        page.html = "<html>updated</html>"
        page.title = "New Title"
        assert page.html == "<html>updated</html>"
        assert page.title == "New Title"


# ======================================================================
# ArticleDraft dataclass
# ======================================================================

class TestArticleDraft:
    """ArticleDraft dataclass construction."""

    def test_create_with_all_fields(self):
        draft = ArticleDraft(
            original_title="Test Article",
            raw_content="Detailed content of the article goes here...",
            source_unit="test_source",
            publish_date=date(2024, 6, 1),
            confidence=0.95,
            extra={"key": "value", "tags": ["news"]},
        )
        assert draft.original_title == "Test Article"
        assert draft.raw_content == "Detailed content of the article goes here..."
        assert draft.source_unit == "test_source"
        assert draft.publish_date == date(2024, 6, 1)
        assert draft.confidence == 0.95
        assert draft.extra == {"key": "value", "tags": ["news"]}

    def test_create_with_defaults(self):
        draft = ArticleDraft(
            original_title="Minimal",
            raw_content="Just enough content.",
        )
        assert draft.original_title == "Minimal"
        assert draft.raw_content == "Just enough content."
        assert draft.source_unit is None
        assert draft.publish_date is None
        assert draft.confidence == 1.0
        assert draft.extra == {}

    def test_extra_default_is_fresh_dict_per_instance(self):
        """Each ArticleDraft gets its own empty dict, not shared."""
        d1 = ArticleDraft(original_title="A", raw_content="x" * 100)
        d2 = ArticleDraft(original_title="B", raw_content="y" * 100)
        d1.extra["key"] = "value"
        assert d2.extra == {}

    def test_publish_date_accepts_none(self):
        draft = ArticleDraft(
            original_title="Title",
            raw_content="x" * 100,
            publish_date=None,
        )
        assert draft.publish_date is None
