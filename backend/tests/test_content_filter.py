"""Tests for app.modules.crawler.content_filter.

Covers: Pruning (low-value element removal), BM25Filter (top-K scoring),
        content_filter_pipeline, empty / fallback paths.
"""
from unittest.mock import patch

import pytest
from bs4 import BeautifulSoup

from app.modules.crawler.content_filter import (
    BM25Filter,
    Pruning,
    content_filter_pipeline,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PAD = '<div style="display:none">' + "x" * 450 + "</div>"


def _long_enough(body: str) -> str:
    """Wrap *body* so the total HTML exceeds 500 characters."""
    return f"<html><head><title>Test</title></head><body>{_PAD}{body}</body></html>"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def mock_cf_settings():
    """Provide deterministic content-filter settings for all tests in this file."""
    with patch("app.modules.crawler.content_filter.settings") as mock:
        mock.CONTENT_FILTER_PRUNING_MIN_DENSITY = 0.05
        mock.CONTENT_FILTER_BM25_TOP_K = 3
        yield mock


# ---------------------------------------------------------------------------
# Pruning
# ---------------------------------------------------------------------------


class TestPruning:
    """HTML denoising -- removes low-value elements but keeps main content."""

    @pytest.mark.parametrize("tag,klass", [
        ("div", "sidebar"),
        ("aside", "sidebar-right"),
        ("section", "sidebar"),
    ])
    def test_removes_sidebar(self, tag, klass):
        html = _long_enough(
            f'<{tag} class="{klass}">Sidebar text here</{tag}>'
            "<article><p>Main content. " + "y" * 80 + "</p></article>"
        )
        result = Pruning.prune(html)
        assert "Sidebar text" not in result

    @pytest.mark.parametrize("attr", ['id="ad"', 'class="advertisement"', 'class="banner"'])
    def test_removes_advertisement(self, attr):
        html = _long_enough(
            f'<div {attr}>Buy now!</div>'
            "<article><p>Real content. " + "z" * 80 + "</p></article>"
        )
        result = Pruning.prune(html)
        assert "Buy now" not in result

    def test_removes_comment_section(self):
        html = _long_enough(
            '<div class="comments">User comment here</div>'
            "<article><p>Article body. " + "w" * 80 + "</p></article>"
        )
        result = Pruning.prune(html)
        assert "User comment" not in result

    def test_removes_nav(self):
        """Bare <nav> is kept; <nav class="nav"> is removed (class matches keyword)."""
        html = _long_enough(
            '<nav class="nav">Nav links here</nav>'
            "<article><p>Content. " + "v" * 80 + "</p></article>"
        )
        result = Pruning.prune(html)
        assert "Nav links" not in result

    def test_removes_footer(self):
        html = _long_enough(
            '<div class="footer">Footer here</div>'
            "<article><p>Content. " + "u" * 80 + "</p></article>"
        )
        result = Pruning.prune(html)
        assert "Footer here" not in result

    def test_preserves_main_content(self):
        html = _long_enough(
            '<div class="sidebar">Sidebar</div>'
            "<article><p>This is the main article content that must be preserved.</p></article>"
            '<div class="footer">Footer</div>'
        )
        result = Pruning.prune(html)
        assert "main article content" in result.lower()

    def test_empty_html_returns_as_is(self):
        assert Pruning.prune("") == ""

    def test_short_html_passthrough(self):
        html = "<p>Short</p>"
        assert Pruning.prune(html) == html


# ---------------------------------------------------------------------------
# BM25Filter
# ---------------------------------------------------------------------------


class TestBM25Filter:
    """BM25 relevance scoring -- keeps top-K blocks relevant to the page title."""

    def test_keeps_contiguous_high_score_region(self):
        """Only the longest contiguous high-score region survives (not scattered ones)."""
        # 6 Python paragraphs (high score, title="Python programming")
        py_blocks = "".join(
            f"<p>Python programming is a versatile language used in many "
            f"domains such as web development data science and automation. "
            f"This is paragraph {i} about Python.</p>"
            for i in range(6)
        )
        # 6 cooking paragraphs (low score, no match with title)
        cook_blocks = "".join(
            f"<p>Cooking and recipes are enjoyable activities for the whole "
            f"family especially on weekends and holidays. "
            f"This is paragraph {i + 6} about cooking.</p>"
            for i in range(6)
        )

        html = (
            f"<html><head><title>Python programming</title></head>"
            f"<body>{py_blocks}{cook_blocks}</body></html>"
        )

        bm25 = BM25Filter()
        result = bm25.filter(html)

        soup = BeautifulSoup(result, "lxml")
        paras = soup.find_all("p")
        # Cooking paragraphs should NOT appear (they're in a separate low-score region)
        for p in paras:
            assert "cooking" not in p.get_text().lower(), (
                f"Cooking block survived: {p.get_text()[:60]}"
            )

    def test_empty_input_returns_empty(self):
        bm25 = BM25Filter()
        assert bm25.filter("") == ""

    def test_short_html_passthrough(self):
        bm25 = BM25Filter()
        html = "<p>Too short</p>"
        assert bm25.filter(html) == html

    def test_no_query_terms_returns_full_html(self):
        """When <title> and <meta> are absent, BM25 returns the input unchanged."""
        html = _long_enough("<p>Some content here.</p>" * 5)
        bm25 = BM25Filter()
        result = bm25.filter(html)
        # Should contain the original content (passed through as fallback)
        assert "Some content" in result

    def test_no_extractable_blocks_returns_full_html(self):
        """When no p/h*/li/td/blockquote/pre tags exist, return input as-is."""
        html = _long_enough("<div>No semantic blocks here at all</div>")
        bm25 = BM25Filter()
        result = bm25.filter(html)
        assert "No semantic blocks" in result


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


class TestContentFilterPipeline:
    """content_filter_pipeline lambda: Pruning then BM25Filter."""

    def test_pipeline_runs_without_error(self):
        html = (
            "<html><head><title>Test article</title></head><body>"
            '<div class="sidebar">Remove me</div>'
            "<article><p>This is the main article content for pipeline testing.</p></article>"
            "</body></html>"
        )
        # The lambda calls BM25Filter().filter(Pruning.prune(html))
        result = content_filter_pipeline(html)
        assert result is not None
        assert isinstance(result, str)

    def test_pipeline_removes_low_value_elements(self):
        html = _long_enough(
            '<div class="sidebar">Sidebar</div>'
            "<article><p>Main content for the pipeline integration test.</p></article>"
            '<div class="footer">Footer</div>'
        )
        result = content_filter_pipeline(html)
        assert "Sidebar" not in result
        assert "Footer" not in result
