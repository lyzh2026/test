"""LLMExtractionAdapter：调用 Kimi 抽取结构化字段（PRD 2.1.10）。
优化：支持分块策略（chunk_token_threshold + overlap_rate）处理长内容。
"""
import json
import logging
import re
from datetime import date, datetime
from typing import List, Optional

from bs4 import BeautifulSoup

from app.core.config import settings
from app.modules.ai.kimi_client import get_kimi_client
from app.modules.crawler.adapters.base import ArticleDraft, RenderedPage, SpiderAdapter

logger = logging.getLogger(__name__)

_PROMPT = """你是一个网页正文抽取器。给定一段 HTML 主体，提取以下结构化字段，输出严格 JSON：

{
  "original_title": "string",
  "source_unit": "string | null",
  "publish_date": "YYYY-MM-DD | null",
  "raw_content": "string (Markdown，正文)",
  "confidence": 0.0
}

规则：
1. 只输出 JSON，不要任何解释。
2. raw_content 必须去除导航、广告、推荐栏、版权声明、评论；保留正文段落和小标题。
3. 若是文章列表页（非单篇文章），confidence 设为 0.2。
4. publish_date 仅识别明确日期；若不确定为 null。
5. confidence 体现你对识别结果可信度（0~1）；正文不像新闻/政策/文章时设小于 0.5。

待提取的 HTML 主体：
"""


def _shrink_html(html: str, max_chars: int = 12000) -> str:
    """剔除 script/style/nav/footer 后截断。"""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "aside", "form", "iframe", "noscript"]):
        tag.decompose()
    text = str(soup)
    if len(text) > max_chars:
        text = text[:max_chars]
    return text


def _extract_json(content: str) -> Optional[dict]:
    try:
        return json.loads(content)
    except Exception:
        pass
    m = re.search(r"\{[\s\S]*\}", content)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None


def _chunk_html(html: str, threshold: int, overlap_rate: float) -> List[str]:
    """将长 HTML 按 token 估算阈值分块。

    使用字符数 / 1.3 粗略估算 token 数（中文约 1 token/字，英文约 1 token/4 字符 的混合估算）。
    """
    if not html:
        return []
    approx_tokens = len(html) // 2
    if approx_tokens <= threshold:
        return [html]

    soup = BeautifulSoup(html, "lxml")
    # 按段分块
    paragraphs = soup.find_all(["p", "div", "section", "blockquote", "pre"])
    chunks: List[str] = []
    current_chunk: List[str] = []
    current_tokens = 0

    for p in paragraphs:
        p_html = str(p)
        p_tokens = len(p_html) // 2
        if current_tokens + p_tokens > threshold and current_chunk:
            chunks.append("\n".join(current_chunk))
            # overlap：保留最后 overlap_rate 比例的段落
            overlap_count = max(1, int(len(current_chunk) * overlap_rate))
            current_chunk = current_chunk[-overlap_count:]
            current_tokens = sum(len(c) // 2 for c in current_chunk)
        current_chunk.append(p_html)
        current_tokens += p_tokens

    if current_chunk:
        chunks.append("\n".join(current_chunk))

    return chunks if chunks else [html]


class LLMExtractionAdapter(SpiderAdapter):
    name = "llm_extraction"

    async def extract(self, page: RenderedPage) -> ArticleDraft | None:
        client, model = get_kimi_client()
        if not client:
            return None

        html_body = page.html
        threshold = settings.CONTENT_FILTER_CHUNK_TOKEN_THRESHOLD
        overlap_rate = settings.CONTENT_FILTER_CHUNK_OVERLAP_RATE

        # 分块
        chunks = _chunk_html(html_body, threshold, overlap_rate)
        if len(chunks) > 1:
            logger.info("LLM extraction chunked into %s parts for %s", len(chunks), page.url)

        # 各块分别提取，合并结果
        merged_title = ""
        merged_content = ""
        merged_source = None
        merged_date = None
        max_confidence = 0.0

        for i, chunk in enumerate(chunks):
            body = _shrink_html(chunk)
            prompt = _PROMPT + body
            try:
                resp = await client.chat.completions.create(
                    model=model,
                    temperature=0.1,
                    max_tokens=4096,
                    messages=[
                        {"role": "system", "content": "你是严谨的网页结构化抽取器，必须只输出 JSON。"},
                        {"role": "user", "content": prompt},
                    ],
                )
            except Exception as e:
                logger.warning("LLM chunk %s failed: %r", i, e)
                continue

            content = resp.choices[0].message.content or ""
            data = _extract_json(content)
            if not data:
                continue

            confidence = float(data.get("confidence", 0) or 0)
            if confidence < 0.5:
                continue

            # 第一块：取标题
            if i == 0:
                merged_title = (data.get("original_title") or page.title or "").strip()
                merged_source = data.get("source_unit") or merged_source
                merged_date_str = data.get("publish_date")
                if merged_date_str:
                    try:
                        merged_date = datetime.strptime(merged_date_str, "%Y-%m-%d").date()
                    except Exception:
                        pass

            # 合并正文
            chunk_content = (data.get("raw_content") or "").strip()
            if chunk_content:
                merged_content += f"\n\n{chunk_content}"
            max_confidence = max(max_confidence, confidence)

        if not merged_content and not merged_title:
            return None
        if max_confidence < 0.5:
            return None

        return ArticleDraft(
            original_title=merged_title,
            raw_content=merged_content.strip(),
            source_unit=merged_source,
            publish_date=merged_date,
            confidence=max_confidence,
        )
