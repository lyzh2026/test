"""测试 WebhookAdapter（飞书）。"""
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from app.modules.distribution.adapters.webhook_adapter import WebhookAdapter, _build_feishu_card
from app.modules.distribution.schemas import ArticleItem, CategoryGroup, ReportStats, WeeklyReport


@pytest.fixture
def sample_report():
    return WeeklyReport(
        year_week="2026-W18",
        date_range_start=date(2026, 4, 27),
        date_range_end=date(2026, 5, 3),
        categories=[
            CategoryGroup(
                name="政策法规",
                articles=[
                    ArticleItem(title="政策A", summary="摘要A", url="https://a.com", publish_date=date(2026, 4, 28), source_unit="来源A"),
                ],
            ),
        ],
        stats=ReportStats(total_articles=1, total_categories=1),
    )


class TestBuildFeishuCard:
    def test_card_structure(self, sample_report):
        card = _build_feishu_card(sample_report)
        assert card["msg_type"] == "interactive"
        assert "拾讯周报 2026-W18" in card["card"]["header"]["title"]["content"]
        assert len(card["card"]["elements"]) > 0

    def test_header_contains_date(self, sample_report):
        card = _build_feishu_card(sample_report)
        header = card["card"]["header"]["title"]["content"]
        assert "2026-04-27" in header
        assert "2026-05-03" in header


class TestWebhookAdapterSend:
    @pytest.mark.asyncio
    async def test_send_success(self, sample_report):
        adapter = WebhookAdapter()
        config = {"url": "https://open.feishu.cn/webhook/test", "platform": "feishu"}
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = mock_client.return_value.__aenter__.return_value
            resp = AsyncMock()
            resp.status_code = 200
            mock_instance.post = AsyncMock(return_value=resp)
            result = await adapter.send(sample_report, config)
            assert result is True

    @pytest.mark.asyncio
    async def test_send_http_error(self, sample_report):
        adapter = WebhookAdapter()
        config = {"url": "https://invalid.url", "platform": "feishu"}
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = mock_client.return_value.__aenter__.return_value
            resp = AsyncMock()
            resp.status_code = 403
            resp.text = "forbidden"
            mock_instance.post = AsyncMock(return_value=resp)
            with pytest.raises(RuntimeError, match="HTTP 403"):
                await adapter.send(sample_report, config)

    @pytest.mark.asyncio
    async def test_empty_url(self, sample_report):
        adapter = WebhookAdapter()
        with pytest.raises(ValueError, match="Webhook URL 为空"):
            await adapter.send(sample_report, {"url": "", "platform": "feishu"})
