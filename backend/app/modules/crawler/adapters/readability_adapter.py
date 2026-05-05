"""ReadabilityAdapter：默认通用方案。"""
import logging
import re
from datetime import date, datetime
from typing import Optional

from bs4 import BeautifulSoup
from readability import Document

from app.modules.crawler.adapters.base import ArticleDraft, RenderedPage, SpiderAdapter

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# HTML → Markdown / Plaintext
# ---------------------------------------------------------------------------

def _html_to_markdown(html: str) -> str:
    """Convert cleaned HTML to Markdown. Falls back to plain text on error."""
    try:
        from markdownify import markdownify as md
        result = md(html, heading_style="ATX", strip=["img", "script", "style"])
        result = re.sub(r"\n{3,}", "\n\n", result)
        return result.strip()
    except Exception:
        return _html_to_plaintext(html)


def _html_to_plaintext(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    return soup.get_text(separator="\n", strip=True)


# ---------------------------------------------------------------------------
# Date / Source extraction (plain text, not Markdown)
# ---------------------------------------------------------------------------

def _guess_publish_date(html: str) -> Optional[date]:
    # 1. 优先从 HTML meta 标签提取
    soup = BeautifulSoup(html, "lxml")
    meta_attrs = [
        ("meta", {"property": "article:published_time"}),
        ("meta", {"name": "pubdate"}),
        ("meta", {"name": "publishdate"}),
        ("meta", {"name": "citation_publication_date"}),
        ("meta", {"name": "dc.date"}),
        ("meta", {"property": "og:pubdate"}),
        ("meta", {"name": "date"}),
    ]
    for tag_name, attrs in meta_attrs:
        tag = soup.find(tag_name, attrs=attrs)
        if tag and tag.get("content"):
            val = tag["content"].strip()[:10]
            try:
                return datetime.strptime(val, "%Y-%m-%d").date()
            except ValueError:
                try:
                    return datetime.strptime(val, "%Y/%m/%d").date()
                except ValueError:
                    pass

    # 2. 全文搜索日期模式（扩大范围）
    patterns = [
        r"(\d{4})-(\d{1,2})-(\d{1,2})",
        r"(\d{4})/(\d{1,2})/(\d{1,2})",
        r"(\d{4})年(\d{1,2})月(\d{1,2})日",
    ]
    text = _html_to_plaintext(html)[:20000]
    # 优先找发布时间附近的日期（更可能是文章的真实发布日期）
    date_prefix = re.compile(r"(?:发布时间|发布日期|更新日期|发布于|时间[：:]|日期[：:]|发表于|撰稿[：:]|编辑[：:])\s*\S{0,20}", re.IGNORECASE)
    for pm in date_prefix.finditer(text):
        nearby = text[pm.start():pm.end() + 30]
        for p in patterns:
            m = re.search(p, nearby)
            if m:
                try:
                    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                    return date(y, mo, d)
                except ValueError:
                    continue
    # 再全文找第一个合理日期
    for p in patterns:
        m = re.search(p, text)
        if m:
            try:
                y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if 2000 <= y <= 2099 and 1 <= mo <= 12 and 1 <= d <= 31:
                    return date(y, mo, d)
            except ValueError:
                continue
    return None


def _guess_source_unit(html: str) -> Optional[str]:
    # 从 meta 标签或常见关键字附近抓取
    soup = BeautifulSoup(html, "lxml")
    for meta_name in ("og:site_name", "author", "source"):
        tag = soup.find("meta", attrs={"name": meta_name}) or soup.find("meta", attrs={"property": meta_name})
        if tag and tag.get("content"):
            return tag["content"].strip()[:120]
    text = _html_to_plaintext(html)[:2000]
    m = re.search(r"(?:发布单位|来源|来源单位)[::]\s*([一-龥A-Za-z0-9·\s]{2,40})", text)
    if m:
        return m.group(1).strip()
    return None


_DATE_KEYWORDS = {
    "今天", "昨天", "明天", "前天", "后天",
    "日前", "近日", "同年", "当月", "去年", "今年", "明年",
    "报道", "讯", "电", "发布时间", "更新于", "发布日期",
}

_DATE_CHAR_PATTERN = re.compile(r"\d+[年月]|[昨今明前当去今明]日|\d+日|月\d+")


def _has_date_hints(text: str) -> bool:
    """检测文本中是否包含时间/日期相关关键词（辅助非文章判断）。"""
    for kw in _DATE_KEYWORDS:
        if kw in text:
            return True
    if _DATE_CHAR_PATTERN.search(text):
        return True
    return False


# ---------------------------------------------------------------------------
# Content completeness check
# ---------------------------------------------------------------------------

_TRUNCATION_MARKERS = [
    "阅读全文", "点击查看详情", "登录后查看", "请登录后查看",
    "展开全文", "查看更多", "查看全部", "立即登录",
    "注册后查看", "下载APP查看", "查看全文",
]


def _check_content_completeness(content_text: str, title: str) -> tuple[bool, str]:
    """Check if extracted content looks complete. Returns (passed, reason)."""
    if not content_text:
        return False, "empty_content"

    lines = [l for l in content_text.split("\n") if l.strip()]

    # 1. Paragraph count: at least 2 non-empty lines
    if len(lines) < 2:
        return False, f"too_few_paragraphs({len(lines)})"

    # 2. Truncation markers
    for marker in _TRUNCATION_MARKERS:
        if marker in content_text:
            return False, f"truncation_marker({marker})"

    # 3. Excessive consecutive newlines (noise): 5+ blank lines in a row
    if re.search(r"\n{5,}", content_text):
        return False, "excessive_newlines"

    # 4. Title presence check (soft): title should appear in body
    if title and len(title) >= 4:
        if title not in content_text:
            # Softer check: at least one 2-char segment of the title in body
            segments = [title[i:i+2] for i in range(0, len(title) - 1, 2)]
            matched = sum(1 for s in segments if s in content_text)
            if matched == 0:
                return False, "title_not_in_body"

    return True, "ok"


# ---------------------------------------------------------------------------
# Image / Attachment extraction
# ---------------------------------------------------------------------------

def _extract_images(content_html: str) -> list[dict]:
    """Extract <img> tags from content HTML as list of {src, alt}."""
    soup = BeautifulSoup(content_html, "lxml")
    images = []
    for img in soup.find_all("img"):
        src = (img.get("src") or "").strip()
        if not src:
            continue
        alt = (img.get("alt") or "").strip()
        images.append({"src": src, "alt": alt})
    return images


def _extract_attachments(full_html: str) -> list[dict]:
    """Extract <a> tags pointing to file attachments (pdf, doc, xls, etc.)."""
    _FILE_EXTS = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
                  ".zip", ".rar", ".7z", ".csv", ".txt")
    soup = BeautifulSoup(full_html, "lxml")
    attachments = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip().lower()
        if any(href.endswith(ext) for ext in _FILE_EXTS):
            if href not in seen:
                seen.add(href)
                attachments.append({
                    "href": a["href"].strip(),
                    "text": (a.get_text(strip=True) or "")[:100],
                })
    return attachments


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

_EXPECTED_LANGS = {"zh-cn", "zh-tw", "zh"}


def _detect_language(text: str) -> str | None:
    """Detect language code from text. Returns None on failure."""
    try:
        import langdetect
        return langdetect.detect(text)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# ReadabilityAdapter
# ---------------------------------------------------------------------------

class ReadabilityAdapter(SpiderAdapter):
    name = "readability"

    def validate(self, draft: ArticleDraft | None) -> bool:
        if not super().validate(draft):
            return False
        if draft is None:
            return False

        # Language detection (soft check)
        text_sample = (draft.raw_content or "")[:2000]
        if len(text_sample) < 50:
            return True  # Too short to detect reliably, pass through

        detected = _detect_language(text_sample)
        if detected and detected.lower() not in _EXPECTED_LANGS:
            logger.info("language mismatch: expected=zh detected=%s for title=%s",
                        detected, draft.original_title[:50])
            return False  # Reject, let LLM try

        return True

    async def extract(self, page: RenderedPage) -> ArticleDraft | None:
        try:
            doc = Document(page.html)
            title = (doc.short_title() or page.title or "").strip()
            content_html = doc.summary(html_partial=True)
            content_text = _html_to_markdown(content_html)
            # 标签密度检测：文本占比过低说明页面主要是导航/链接，非真实文章
            if content_html and len(content_text) / len(content_html) < 0.15:
                return None
            # 链接密度检测：文本中来自 <a> 标签的占比过高 → 列表页
            if content_html:
                soup = BeautifulSoup(content_html, "lxml")
                link_text_len = sum(len(a.get_text(strip=True)) for a in soup.find_all("a"))
                if content_text and link_text_len / len(content_text) > 0.5:
                    return None

            # 内容完整性校验
            completeness_ok, completeness_reason = _check_content_completeness(content_text, title)
            if not completeness_ok:
                logger.debug("completeness check failed: %s reason=%s", page.url, completeness_reason)
                return None

            publish_date = _guess_publish_date(page.html)
            # 没提取到日期，且正文缺少时间线索 → 非文章，交给 LLM 二次确认
            if not publish_date and not _has_date_hints(content_text):
                return None

            # 图片/附件提取
            images = _extract_images(content_html)
            attachments = _extract_attachments(page.html)

            return ArticleDraft(
                original_title=title,
                raw_content=content_text,
                source_unit=_guess_source_unit(page.html),
                publish_date=publish_date,
                confidence=0.9,
                extra={
                    "content_format": "markdown",
                    "images": images,
                    "attachments": attachments,
                },
            )
        except Exception:
            return None
