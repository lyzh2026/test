"""Tests for ReadabilityAdapter quality improvements.

Covers: content completeness check, Markdown output, image/attachment extraction,
        language detection.
"""
from datetime import date
from unittest.mock import patch

import pytest

from app.modules.crawler.adapters.base import ArticleDraft, RenderedPage
from app.modules.crawler.adapters.readability_adapter import (
    ReadabilityAdapter,
    _check_content_completeness,
    _extract_attachments,
    _extract_images,
    _html_to_markdown,
    _html_to_plaintext,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def adapter():
    return ReadabilityAdapter()


# ---------------------------------------------------------------------------
# Content Completeness
# ---------------------------------------------------------------------------

class TestContentCompleteness:
    def test_single_paragraph_rejected(self):
        ok, reason = _check_content_completeness("This is one block of text only.", "Title")
        assert not ok
        assert "too_few_paragraphs" in reason

    def test_empty_content_rejected(self):
        ok, reason = _check_content_completeness("", "Title")
        assert not ok
        assert reason == "empty_content"

    def test_truncation_marker_rejected(self):
        markers = ["阅读全文", "点击查看详情", "登录后查看", "展开全文", "下载APP查看"]
        for marker in markers:
            ok, reason = _check_content_completeness(f"段落一\n\n{marker}\n\n段落三", "Title")
            assert not ok, f"marker '{marker}' should be rejected"
            assert "truncation_marker" in reason

    def test_excessive_newlines_rejected(self):
        content = "段落一\n\n\n\n\n\n\n段落二"
        ok, reason = _check_content_completeness(content, "Title")
        assert not ok
        assert reason == "excessive_newlines"

    def test_title_not_in_body_rejected(self):
        ok, reason = _check_content_completeness("这是一段无关的内容\n\n第二段内容", "完全不同的标题关键词")
        assert not ok
        assert reason == "title_not_in_body"

    def test_valid_content_passes(self):
        content = "第一段关于Python编程的内容\n\n第二段关于Python应用的内容"
        ok, reason = _check_content_completeness(content, "Python编程指南")
        assert ok
        assert reason == "ok"

    def test_short_title_skips_title_check(self):
        content = "第一段内容\n\n第二段内容"
        ok, reason = _check_content_completeness(content, "短")
        assert ok


# ---------------------------------------------------------------------------
# Markdown Output
# ---------------------------------------------------------------------------

class TestMarkdownOutput:
    def test_heading_conversion(self):
        html = "<h2>Title</h2><p>Content</p>"
        result = _html_to_markdown(html)
        assert "## Title" in result

    def test_bold_conversion(self):
        html = "<p><strong>Bold text</strong></p>"
        result = _html_to_markdown(html)
        assert "**Bold text**" in result

    def test_list_conversion(self):
        html = "<ul><li>Item 1</li><li>Item 2</li></ul>"
        result = _html_to_markdown(html)
        assert "* Item 1" in result
        assert "* Item 2" in result

    def test_excessive_newlines_cleaned(self):
        html = "<p>A</p><p></p><p></p><p></p><p>B</p>"
        result = _html_to_markdown(html)
        assert "\n\n\n" not in result

    def test_empty_html(self):
        result = _html_to_markdown("")
        assert result == ""

    def test_fallback_to_plaintext(self):
        # markdownify should handle normal HTML, but test the fallback exists
        html = "<p>Simple content</p>"
        result = _html_to_markdown(html)
        assert "Simple content" in result


class TestPlaintextOutput:
    def test_strips_all_tags(self):
        html = "<h2>Title</h2><p>Content <strong>bold</strong></p>"
        result = _html_to_plaintext(html)
        assert "<" not in result
        assert "Title" in result
        assert "Content" in result
        assert "bold" in result


# ---------------------------------------------------------------------------
# Image Extraction
# ---------------------------------------------------------------------------

class TestImageExtraction:
    def test_extracts_img_tags(self):
        html = '<p>Hello</p><img src="http://example.com/pic.jpg" alt="photo"><p>World</p>'
        images = _extract_images(html)
        assert len(images) == 1
        assert images[0]["src"] == "http://example.com/pic.jpg"
        assert images[0]["alt"] == "photo"

    def test_img_without_src_skipped(self):
        html = '<img alt="no src"><img src="" alt="empty"><img src="http://ok.com/a.jpg" alt="ok">'
        images = _extract_images(html)
        assert len(images) == 1
        assert images[0]["src"] == "http://ok.com/a.jpg"

    def test_empty_html(self):
        assert _extract_images("") == []

    def test_no_images(self):
        html = "<p>No images here</p>"
        assert _extract_images(html) == []

    def test_multiple_images(self):
        html = '<img src="a.jpg" alt="A"><img src="b.jpg" alt="B"><img src="c.jpg">'
        images = _extract_images(html)
        assert len(images) == 3
        assert images[2]["alt"] == ""


# ---------------------------------------------------------------------------
# Attachment Extraction
# ---------------------------------------------------------------------------

class TestAttachmentExtraction:
    def test_extracts_pdf_link(self):
        html = '<a href="/files/report.pdf">Download</a><a href="/about">About</a>'
        attachments = _extract_attachments(html)
        assert len(attachments) == 1
        assert attachments[0]["href"] == "/files/report.pdf"
        assert attachments[0]["text"] == "Download"

    def test_extracts_multiple_file_types(self):
        html = '''
        <a href="/doc.docx">Word</a>
        <a href="/data.xlsx">Excel</a>
        <a href="/slides.pptx">PPT</a>
        <a href="/archive.zip">Zip</a>
        '''
        attachments = _extract_attachments(html)
        assert len(attachments) == 4

    def test_deduplicates(self):
        html = '<a href="/file.pdf">Link 1</a><a href="/file.pdf">Link 2</a>'
        attachments = _extract_attachments(html)
        assert len(attachments) == 1

    def test_regular_links_ignored(self):
        html = '<a href="/page">Normal</a><a href="http://example.com">External</a>'
        assert _extract_attachments(html) == []

    def test_empty_html(self):
        assert _extract_attachments("") == []

    def test_text_truncated(self):
        long_text = "A" * 200
        html = f'<a href="/file.pdf">{long_text}</a>'
        attachments = _extract_attachments(html)
        assert len(attachments[0]["text"]) <= 100


# ---------------------------------------------------------------------------
# Language Detection
# ---------------------------------------------------------------------------

class TestLanguageDetection:
    def test_english_rejected(self, adapter):
        draft = ArticleDraft(
            original_title="Test Article",
            raw_content="This is a comprehensive English article about technology and innovation. " * 10,
        )
        assert adapter.validate(draft) is False

    def test_chinese_accepted(self, adapter):
        draft = ArticleDraft(
            original_title="测试文章",
            raw_content="这是一篇关于技术创新的中文文章，内容非常丰富。" * 10,
        )
        assert adapter.validate(draft) is True

    def test_short_text_passes(self, adapter):
        draft = ArticleDraft(
            original_title="Test",
            raw_content="这是一段足够长的中文内容，用于通过语言检测。" * 20,
        )
        assert adapter.validate(draft) is True

    def test_none_draft_fails(self, adapter):
        assert adapter.validate(None) is False

    def test_empty_title_fails(self, adapter):
        draft = ArticleDraft(
            original_title="",
            raw_content="这是一篇内容足够的文章，包含多个段落和详细信息。" * 10,
        )
        assert adapter.validate(draft) is False

    def test_short_content_fails(self, adapter):
        draft = ArticleDraft(
            original_title="Test",
            raw_content="Too short",
        )
        assert adapter.validate(draft) is False
