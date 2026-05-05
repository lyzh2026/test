"""ReadabilityAdapter：默认通用方案。"""
import re
from datetime import date, datetime
from typing import Optional

from bs4 import BeautifulSoup
from readability import Document

from app.modules.crawler.adapters.base import ArticleDraft, RenderedPage, SpiderAdapter


def _strip_html(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    return soup.get_text(separator="\n", strip=True)


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
    text = _strip_html(html)[:20000]
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
    text = _strip_html(html)[:2000]
    m = re.search(r"(?:发布单位|来源|来源单位)[::]\s*([一-龥A-Za-z0-9·\s]{2,40})", text)
    if m:
        return m.group(1).strip()
    return None


_DATE_KEYWORDS = {
    "今天", "昨天", "明天", "前天", "后天",
    "日前", "近日", "同年", "当月", "去年", "今年", "明年",
    "报道", "讯", "电", "发布时间", "更新于", "发布日期",
}

# 日期相关单字，需结合数字上下文判断
_DATE_CHAR_PATTERN = re.compile(r"\d+[年月]|[昨今明前当去今明]日|\d+日|月\d+")


def _has_date_hints(text: str) -> bool:
    """检测文本中是否包含时间/日期相关关键词（辅助非文章判断）。"""
    for kw in _DATE_KEYWORDS:
        if kw in text:
            return True
    if _DATE_CHAR_PATTERN.search(text):
        return True
    return False


class ReadabilityAdapter(SpiderAdapter):
    name = "readability"

    async def extract(self, page: RenderedPage) -> ArticleDraft | None:
        try:
            doc = Document(page.html)
            title = (doc.short_title() or page.title or "").strip()
            content_html = doc.summary(html_partial=True)
            content_text = _strip_html(content_html)
            # 标签密度检测：文本占比过低说明页面主要是导航/链接，非真实文章
            if content_html and len(content_text) / len(content_html) < 0.15:
                return None
            # 链接密度检测：文本中来自 <a> 标签的占比过高 → 列表页
            if content_html:
                soup = BeautifulSoup(content_html, "lxml")
                link_text_len = sum(len(a.get_text(strip=True)) for a in soup.find_all("a"))
                if content_text and link_text_len / len(content_text) > 0.5:
                    return None

            publish_date = _guess_publish_date(page.html)
            # 没提取到日期，且正文缺少时间线索 → 非文章，交给 LLM 二次确认
            if not publish_date and not _has_date_hints(content_text):
                return None

            return ArticleDraft(
                original_title=title,
                raw_content=content_text,
                source_unit=_guess_source_unit(page.html),
                publish_date=publish_date,
                confidence=0.9,
            )
        except Exception:
            return None
