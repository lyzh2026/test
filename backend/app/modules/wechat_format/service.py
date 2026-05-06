import json
import re

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.models.article import Article
from app.models.ai_analysis import AIAnalysis
from app.modules.ai.kimi_client import get_llm_client
from .templates import _split_paragraphs, TEMPLATES

# 内存缓存 AI 重写结果，避免切换模板时重复生成
_wechat_rewrite_cache: dict[str, dict] = {}


async def _fetch_article_data(
    session: AsyncSession,
    article_id: str,
) -> dict:
    """Fetch and prepare article + AI analysis data for rendering/exports."""
    stmt = (
        select(Article, AIAnalysis)
        .outerjoin(AIAnalysis, Article.id == AIAnalysis.article_id)
        .where(Article.id == article_id)
    )
    result = await session.execute(stmt)
    row = result.one_or_none()
    if row is None:
        raise ValueError("文章不存在")

    article: Article = row[0]
    analysis: AIAnalysis | None = row[1]

    if not article.raw_content:
        raise ValueError("文章内容为空")

    paragraphs = _split_paragraphs(article.raw_content)
    return {
        "id": str(article.id),
        "title": article.original_title or "(无标题)",
        "source": article.source_unit or "",
        "date": article.publish_date.isoformat() if article.publish_date else "",
        "link": article.original_link or "",
        "summary": analysis.summary.strip() if analysis and analysis.summary else "",
        "keywords": analysis.keywords[:8] if analysis and analysis.keywords else [],
        "categories": analysis.categories[:5] if analysis and analysis.categories else [],
        "paragraphs": paragraphs,
    }


async def _ai_rewrite_for_wechat(data: dict) -> dict:
    """Use Kimi to rewrite the article as a WeChat-style post.

    Falls back to original data if AI is unavailable or fails.
    Caches result per article_id in memory.
    """
    article_id = data["id"]
    if article_id in _wechat_rewrite_cache:
        return _wechat_rewrite_cache[article_id]

    client, model = await get_llm_client()
    if client is None:
        return data

    full_text = "\n\n".join(data["paragraphs"])
    # 截断过长的正文，避免超出 token 限制
    if len(full_text) > 8000:
        full_text = full_text[:8000] + "\n\n...（原文过长已截断）"

    prompt = (
        "你是一个资深微信公众号文章写手。请根据以下原始新闻/文章资料，重新创作一篇适合微信公众号发布的文章。\n\n"
        "## 原始资料\n\n"
        f"标题：{data['title']}\n"
        f"摘要：{data['summary']}\n"
        f"正文：\n{full_text}\n\n"
        "## 写作要求\n\n"
        "1. 标题要吸引点击，适合微信传播（控制在 30 字内，不要标题党）\n"
        "2. 开头写一段引人入胜的导语或场景引入\n"
        "3. 正文重新组织语言，段落简短（每段 2-4 句，适配手机阅读）\n"
        "4. 语言通俗、有对话感，避免官方腔\n"
        "5. 结尾写一段总结，适当引导读者互动\n"
        "6. 整体长度控制在 800-1500 字\n"
        "7. 忽略原文中的图片标注、图注、alt 文字、水印文字、广告等噪音，只保留正文信息\n\n"
        "## 输出格式\n\n"
        "只输出 JSON，不要任何解释：\n\n"
        '{\n'
        '  "title": "新标题",\n'
        '  "paragraphs": ["第一段...", "第二段...", "第三段..."]\n'
        '}'
    )

    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=4096,
        )
        content = resp.choices[0].message.content or ""
        json_match = re.search(r"\{.*\}", content, re.DOTALL)
        if not json_match:
            return data
        result = json.loads(json_match.group())
        if not result.get("title") or not result.get("paragraphs"):
            return data
        new_data = {
            **data,
            "title": result["title"].strip(),
            "paragraphs": result["paragraphs"],
        }
        _wechat_rewrite_cache[article_id] = new_data
        return new_data
    except Exception:
        return data


async def render_article(
    session: AsyncSession,
    article_id: str,
    template_name: str = "green-simple",
) -> dict:
    """Render an article's content as WeChat-compatible styled HTML."""
    render_fn = TEMPLATES.get(template_name)
    if render_fn is None:
        valid = ", ".join(sorted(TEMPLATES))
        raise ValueError(f"未知模板：{template_name}，可选：{valid}")

    data = await _fetch_article_data(session, article_id)
    data = await _ai_rewrite_for_wechat(data)

    html = render_fn(
        title=data["title"],
        paragraphs=data["paragraphs"],
        summary=data["summary"],
        keywords=data["keywords"],
        source=data["source"],
        date_str=data["date"],
        link=data["link"],
    )

    return {
        "article_id": data["id"],
        "title": data["title"],
        "html": html,
        "template": template_name,
    }


def build_markdown(data: dict) -> str:
    """Build plain markdown from article data."""
    lines: list[str] = []
    a = lines.append

    a(f"# {data['title']}")
    a("")
    meta = []
    if data["source"]:
        meta.append(f"来源：{data['source']}")
    if data["date"]:
        meta.append(f"日期：{data['date']}")
    if meta:
        a(f"> {' ｜ '.join(meta)}")
    a("")

    if data["summary"]:
        a("## AI 摘要")
        a("")
        a(data["summary"])
        a("")

    if data["keywords"]:
        a("## 关键词")
        a("")
        a(" ".join(f"`{kw}`" for kw in data["keywords"]))
        a("")

    if data["categories"]:
        cats = [c.get("label", "") for c in data["categories"]]
        a("## 分类")
        a("")
        a(" ".join(f"`{c}`" for c in cats))
        a("")

    a("---")
    a("")

    for para in data["paragraphs"]:
        a(para)
        a("")

    if data["link"]:
        a("---")
        a("")
        a(f"原文链接：{data['link']}")

    return "\n".join(lines)


def build_html_document(data: dict, template_name: str = "green-simple") -> str:
    """Build a standalone HTML document from article data."""
    render_fn = TEMPLATES.get(template_name)
    if render_fn is None:
        render_fn = TEMPLATES["green-simple"]

    body_html = render_fn(
        title=data["title"],
        paragraphs=data["paragraphs"],
        summary=data["summary"],
        keywords=data["keywords"],
        source=data["source"],
        date_str=data["date"],
        link=data["link"],
    )
    escaped_title = data["title"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{escaped_title}</title>
<base target="_blank">
</head>
<body style="margin:0;padding:0;background:#f5f5f5;">
<div style="max-width:640px;margin:0 auto;background:#fff;min-height:100vh;padding:10px 16px 40px;box-sizing:border-box;">
{body_html}
</div>
</body>
</html>"""


async def export_markdown(
    session: AsyncSession,
    article_id: str,
) -> tuple[str, str]:
    """Export article as markdown. Returns (title, markdown_content)."""
    data = await _fetch_article_data(session, article_id)
    content = build_markdown(data)
    return data["title"], content


async def export_html(
    session: AsyncSession,
    article_id: str,
    template_name: str = "green-simple",
) -> tuple[str, str]:
    """Export article as standalone HTML. Returns (title, html_content)."""
    data = await _fetch_article_data(session, article_id)
    data = await _ai_rewrite_for_wechat(data)
    content = build_html_document(data, template_name)
    return data["title"], content
