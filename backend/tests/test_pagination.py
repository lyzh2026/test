"""Tests for app.modules.crawler.pagination.

Covers: <link rel="next">, <a rel="next">, class-based, text-based,
        URL pattern (?page=N / _N.html), visited-skip, edge cases.
"""
import pytest

from app.modules.crawler.pagination import find_article_next_page


class TestFindArticleNextPage:
    """find_article_next_page(html, base_url, visited) -> str | None."""

    # ------------------------------------------------------------------ #
    # Edge cases
    # ------------------------------------------------------------------ #

    def test_empty_html_returns_none(self):
        assert find_article_next_page("", "http://example.com/article", set()) is None

    def test_no_next_link_returns_none(self):
        html = "<html><body><p>Single page article with no pagination.</p></body></html>"
        assert find_article_next_page(html, "http://example.com/article", set()) is None

    # ------------------------------------------------------------------ #
    # <link rel="next">
    # ------------------------------------------------------------------ #

    def test_link_rel_next(self):
        html = '<html><head><link rel="next" href="http://example.com/page2"></head></html>'
        result = find_article_next_page(html, "http://example.com/page1", set())
        assert result == "http://example.com/page2"

    def test_link_rel_next_relative_href(self):
        html = '<html><head><link rel="next" href="/page2"></head><body><p>Content</p></body></html>'
        result = find_article_next_page(html, "http://example.com/article", set())
        assert result == "http://example.com/page2"

    # ------------------------------------------------------------------ #
    # <a rel="next">
    # ------------------------------------------------------------------ #

    def test_a_rel_next(self):
        html = '<html><body><a rel="next" href="http://example.com/page2">Next</a></body></html>'
        result = find_article_next_page(html, "http://example.com/page1", set())
        assert result == "http://example.com/page2"

    # ------------------------------------------------------------------ #
    # <a class="next"> and variants
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize("cls", ["next", "pagination-next", "article-next", "page-next"])
    def test_a_class_next_variants(self, cls):
        html = f'<html><body><a class="{cls}" href="http://example.com/page2">Next</a></body></html>'
        result = find_article_next_page(html, "http://example.com/page1", set())
        assert result == "http://example.com/page2"

    # ------------------------------------------------------------------ #
    # Text-based detection
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize("text", ["下一页", "下一頁", "›", "»", "next"])
    def test_text_based_next(self, text):
        html = f'<html><body><a href="http://example.com/page2">{text}</a></body></html>'
        result = find_article_next_page(html, "http://example.com/page1", set())
        assert result == "http://example.com/page2", f"failed for text={text!r}"

    # ------------------------------------------------------------------ #
    # URL pattern detection (?page=N)
    # ------------------------------------------------------------------ #

    def test_url_pattern_page_param(self):
        html = "<html><body><p>Article content page 1.</p></body></html>"
        result = find_article_next_page(
            html,
            "http://example.com/article?page=1",
            set(),
        )
        assert result == "http://example.com/article?page=2"

    def test_url_pattern_page_param_ignores_non_matching(self):
        """?page=N pattern only fires when base_url already has a 'page' query param."""
        html = "<html><body><p>Content</p></body></html>"
        result = find_article_next_page(
            html,
            "http://example.com/article?offset=10",
            set(),
        )
        assert result is None

    # ------------------------------------------------------------------ #
    # URL pattern detection (_N.html)
    # ------------------------------------------------------------------ #

    def test_url_pattern_n_html(self):
        r"""Regex /(\d+)\.html$ requires digits immediately after the slash."""
        html = "<html><body><p>Article content page 1.</p></body></html>"
        result = find_article_next_page(
            html,
            "http://example.com/1.html",
            set(),
        )
        assert result == "http://example.com/2.html"

    def test_url_pattern_n_html_with_path_prefix(self):
        html = "<html><body><p>Content</p></body></html>"
        result = find_article_next_page(
            html,
            "http://example.com/2025/3.html",
            set(),
        )
        assert result == "http://example.com/2025/4.html"

    # ------------------------------------------------------------------ #
    # Visited-URL skip
    # ------------------------------------------------------------------ #

    def test_link_rel_next_already_visited(self):
        html = '<html><head><link rel="next" href="http://example.com/page2"></head></html>'
        visited = {"http://example.com/page2"}
        result = find_article_next_page(html, "http://example.com/page1", visited)
        # No other match patterns exist, so returns None
        assert result is None

    def test_a_rel_next_already_visited(self):
        html = '<html><body><a rel="next" href="http://example.com/page2">Next</a></body></html>'
        visited = {"http://example.com/page2"}
        result = find_article_next_page(html, "http://example.com/page1", visited)
        assert result is None

    def test_text_based_already_visited_falls_to_url_pattern(self):
        """When text-based link URL is visited, falls through to ?page=N pattern."""
        html = '<html><body><a href="http://example.com/article?page=2">下一页</a></body></html>'
        visited = {"http://example.com/article?page=2"}
        result = find_article_next_page(
            html,
            "http://example.com/article?page=1",
            visited,
        )
        # ?page=1 + page param → pattern returns ?page=2, but it's visited → None
        assert result is None

    # ------------------------------------------------------------------ #
    # Edge: bad / malformed HTML
    # ------------------------------------------------------------------ #

    def test_bad_html_does_not_raise(self):
        html = "<<<<<>>>>><<<<>>>>"
        result = find_article_next_page(html, "http://example.com/article", set())
        assert result is None
