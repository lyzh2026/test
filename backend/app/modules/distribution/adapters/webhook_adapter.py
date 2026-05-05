"""飞书 Webhook 通道适配器。"""
import logging

import httpx

from app.modules.distribution.adapters.base import DistributionAdapter
from app.modules.distribution.schemas import WeeklyReport

logger = logging.getLogger("shixun.distribution.webhook")

_MAX_ELEMENTS = 20


def _build_feishu_card(report: WeeklyReport) -> dict:
    """构建飞书消息卡片。"""
    header_text = f"拾讯周报 {report.year_week}（{report.date_range_start} ~ {report.date_range_end}）"

    elements = [
        {
            "tag": "markdown",
            "content": f"本周共采集 **{report.stats.total_articles}** 篇文章，覆盖 **{report.stats.total_categories}** 个分类",
        },
        {"tag": "hr"},
    ]

    for cat in report.categories:
        lines = [f"**📋 {cat.name}（{len(cat.articles)}篇）**"]
        for a in cat.articles[:10]:
            lines.append(f"[{a.title}]({a.url}) · {a.publish_date}")
            lines.append(f"> {a.summary}")
        elements.append({"tag": "markdown", "content": "\n".join(lines)})
        elements.append({"tag": "hr"})

    if len(elements) > _MAX_ELEMENTS:
        elements = elements[:_MAX_ELEMENTS]
        elements.append({"tag": "markdown", "content": f"… 共 {report.stats.total_articles} 篇，完整内容请查看邮件"})

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": header_text},
            },
            "elements": elements,
        },
    }


class WebhookAdapter(DistributionAdapter):
    """通用 Webhook 适配器，按 platform 选择消息格式。"""

    async def send(self, report: WeeklyReport, config: dict) -> bool:
        url = config.get("url", "")
        if not url:
            raise ValueError("Webhook URL 为空")

        platform = config.get("platform", "feishu")

        if platform == "feishu":
            payload = _build_feishu_card(report)
        else:
            raise ValueError(f"不支持的 Webhook 平台: {platform}")

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code >= 400:
                raise RuntimeError(f"Webhook 发送失败: HTTP {resp.status_code} {resp.text[:200]}")

        logger.info("Webhook 周报发送成功: %s", platform)
        return True
