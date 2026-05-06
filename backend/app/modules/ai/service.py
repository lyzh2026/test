"""AI 中枢：多模型分类与摘要 + 文章状态机驱动。"""
import asyncio
import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Callable, Optional

import openai
from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.ai_analysis import AIAnalysis
from app.models.article import Article
from app.models.system_config import SystemConfig
from app.modules.ai.kimi_client import get_llm_client

logger = logging.getLogger(__name__)

_DEFAULT_CATEGORY_LABELS = [
    "最新政策", "数字经济", "人工智能", "数据要素", "通信",
    "申报", "潜在商机", "具身智能", "车路云协同", "新型工业化", "算力",
]

CATEGORY_THRESHOLD = 0.6
CATEGORY_TOP_K = 3
FALLBACK_LABEL = "未分类"


async def get_category_labels(session) -> list[str]:
    """从 SystemConfig 读取分类标签，无配置时返回默认值。"""
    from sqlalchemy import select
    result = await session.execute(
        select(SystemConfig).where(SystemConfig.key == "category_labels")
    )
    cfg = result.scalar_one_or_none()
    if cfg and cfg.value and isinstance(cfg.value, list):
        return [str(l).strip() for l in cfg.value if str(l).strip()]
    return list(_DEFAULT_CATEGORY_LABELS)

_CLASSIFY_PROMPT = """你是一个新闻/政务文章分类器。给定标题与正文摘录，从以下 {count} 类中给出每一类的相关度概率（0~1）：

{labels}

输出严格 JSON：
{{
  "scores": {{"{first_label}": 0.0, ...}},
  "keywords": ["关键词1", "关键词2", "关键词3"]
}}

规则：
1. 只输出 JSON，不要解释。
2. scores 必须包含全部 {count} 个标签；不相关的设较低值。
3. keywords 输出 3-5 个最能概括正文的关键词。

文章标题：{title}

正文摘录：
{content}
"""

_SUMMARY_PROMPT = """请基于以下文章生成 150-200 字的中文摘要。要求：
1. 直接输出摘要文本，不要任何前缀或解释。
2. 突出事实与关键数据，避免主观评价。
3. 保持客观、连贯、简洁。

文章标题：{title}

正文：
{content}
"""


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


def _clip(text: str, n: int) -> str:
    text = text or ""
    return text[:n]


def _is_retryable(exc: Exception) -> bool:
    """判断异常是否可重试：429/5xx/超时/连接错误。"""
    if isinstance(exc, openai.APIStatusError):
        return exc.status_code == 429 or exc.status_code >= 500
    return isinstance(exc, (openai.APITimeoutError, openai.APIConnectionError))


async def _retry_call(coro_factory: Callable, max_retries: int = 3):
    """带指数退避的重试包装器。coro_factory 必须返回一个新的协程。"""
    for attempt in range(max_retries):
        try:
            return await coro_factory()
        except Exception as e:
            if _is_retryable(e) and attempt < max_retries - 1:
                wait = 2 ** attempt
                logger.warning("AI 调用失败（可重试），%d/%d 次，等待 %ds: %r", attempt + 1, max_retries, wait, e)
                await asyncio.sleep(wait)
            else:
                raise


async def _classify(client, model, title: str, content: str, labels: list[str]) -> tuple[list[dict], list[str]]:
    prompt = _CLASSIFY_PROMPT.format(
        count=len(labels),
        labels="、".join(labels),
        first_label=labels[0],
        title=_clip(title, 200),
        content=_clip(content, 4000),
    )
    resp = await _retry_call(lambda: client.chat.completions.create(
        model=model,
        temperature=0.3,
        max_tokens=1024,
        messages=[
            {"role": "system", "content": "你是严谨的中文文章分类器，必须只输出 JSON。"},
            {"role": "user", "content": prompt},
        ],
    ))
    raw = resp.choices[0].message.content or ""
    data = _extract_json(raw) or {}
    scores = data.get("scores") or {}
    keywords = data.get("keywords") or []
    items: list[tuple[str, float]] = []
    for label in labels:
        try:
            v = float(scores.get(label, 0) or 0)
        except (TypeError, ValueError):
            v = 0.0
        items.append((label, max(0.0, min(1.0, v))))
    items.sort(key=lambda x: x[1], reverse=True)
    picked = [(lbl, sc) for lbl, sc in items if sc >= CATEGORY_THRESHOLD][:CATEGORY_TOP_K]
    if not picked:
        picked = [(FALLBACK_LABEL, 0.0)]
    cats = [{"label": lbl, "confidence": round(sc, 3)} for lbl, sc in picked]
    if not isinstance(keywords, list):
        keywords = []
    keywords = [str(k).strip() for k in keywords if str(k).strip()][:5]
    return cats, keywords


async def _summarize(client, model, title: str, content: str) -> str:
    prompt = _SUMMARY_PROMPT.format(title=_clip(title, 200), content=_clip(content, 5000))
    resp = await _retry_call(lambda: client.chat.completions.create(
        model=model,
        temperature=0.3,
        max_tokens=512,
        messages=[
            {"role": "system", "content": "你是严谨的中文新闻摘要生成器，输出简洁客观。"},
            {"role": "user", "content": prompt},
        ],
    ))
    text = (resp.choices[0].message.content or "").strip()
    return text[:400]


async def analyze_article(article_id: str) -> dict:
    """主入口：状态机 raw → analyzing → processed/failed。"""
    started = time.time()

    async with AsyncSessionLocal() as session:
        article = await session.get(Article, article_id)
        if not article:
            return {"ok": False, "reason": "article_not_found"}
        if article.status not in ("raw", "failed_retryable"):
            return {"ok": False, "reason": f"status_skip:{article.status}"}
        article.status = "analyzing"
        await session.commit()

    client, model = await get_llm_client()
    if not client:
        async with AsyncSessionLocal() as session:
            article = await session.get(Article, article_id)
            if article:
                article.status = "failed_permanent"
                article.failed_reason = "AI API Key 未配置"
                await session.commit()
        return {"ok": False, "reason": "no_api_key"}

    title = article.original_title
    content = article.raw_content or ""
    if len(content.strip()) < 100:
        async with AsyncSessionLocal() as session:
            a = await session.get(Article, article_id)
            if a:
                a.status = "failed_permanent"
                a.failed_reason = "正文过短，无法分析"
                await session.commit()
        return {"ok": False, "reason": "content_too_short"}

    async with AsyncSessionLocal() as session:
        labels = await get_category_labels(session)

    try:
        cats, keywords = await _classify(client, model, title, content, labels)
        summary = await _summarize(client, model, title, content)
    except Exception as e:
        logger.exception("AI analyze failed for %s", article_id)
        target_status = "failed_retryable" if _is_retryable(e) else "failed_permanent"
        async with AsyncSessionLocal() as session:
            a = await session.get(Article, article_id)
            if a:
                a.status = target_status
                a.failed_reason = f"AI 调用失败：{e!r}"
                await session.commit()
        return {"ok": False, "reason": f"ai_error:{e!r}"}

    elapsed_ms = int((time.time() - started) * 1000)

    async with AsyncSessionLocal() as session:
        existing = await session.execute(select(AIAnalysis).where(AIAnalysis.article_id == article_id))
        row = existing.scalar_one_or_none()
        if row:
            row.categories = cats
            row.summary = summary
            row.keywords = keywords
            row.model_used = model
            row.processing_time_ms = elapsed_ms
        else:
            row = AIAnalysis(
                article_id=article_id,
                categories=cats,
                summary=summary,
                keywords=keywords,
                model_used=model,
                processing_time_ms=elapsed_ms,
            )
            session.add(row)

        article = await session.get(Article, article_id)
        if article:
            article.status = "processed"
            article.failed_reason = None
        await session.commit()
    return {"ok": True, "categories": cats, "elapsed_ms": elapsed_ms}


async def scan_analyzing_timeouts() -> int:
    """将卡在 analyzing 超过阈值的文章重置为 failed_retryable。"""
    now = datetime.now(timezone.utc)
    from datetime import timedelta
    cutoff = now - timedelta(seconds=settings.AI_ANALYZING_TIMEOUT_SEC)
    moved = 0
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Article).where(Article.status == "analyzing"))
        rows = res.scalars().all()
        for a in rows:
            # 确保 updated_at 带时区后比较
            updated = a.updated_at
            if updated and updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            if updated and updated < cutoff:
                a.status = "failed_retryable"
                a.failed_reason = "analyzing 超时（>5min），自动回退"
                moved += 1
        if moved:
            await session.commit()
    return moved
