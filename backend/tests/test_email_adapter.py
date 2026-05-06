"""测试 EmailAdapter。"""
from datetime import date
from unittest.mock import patch

import pytest

from app.modules.distribution.adapters.email_adapter import EmailAdapter, _build_html
from app.modules.distribution.schemas import ArticleItem, CategoryGroup, ReportStats, WeeklyReport


@pytest.fixture
def sample_report():
    return WeeklyReport(
        year_week="2026-W18",
        date_range_start=date(2026, 4, 27),
        date_range_end=date(2026, 5, 3),
        categories=[
            CategoryGroup(
                name="最新政策",
                articles=[
                    ArticleItem(title="政策A", summary="摘要A", url="https://a.com", publish_date=date(2026, 4, 28), source_unit="来源A"),
                    ArticleItem(title="政策B", summary="摘要B", url="https://b.com", publish_date=date(2026, 4, 29), source_unit="来源B"),
                ],
            ),
        ],
        stats=ReportStats(total_articles=2, total_categories=1),
    )


class TestBuildHtml:
    def test_contains_title(self, sample_report):
        html = _build_html(sample_report)
        assert "拾讯周报 2026-W18" in html
        assert "2026-04-27" in html
        assert "2026-05-03" in html
        assert "2" in html
        assert "最新政策" in html
        assert "政策A" in html
        assert "摘要A" in html

    def test_empty_report(self):
        report = WeeklyReport(
            year_week="2026-W18",
            date_range_start=date(2026, 4, 27),
            date_range_end=date(2026, 5, 3),
            categories=[],
            stats=ReportStats(total_articles=0, total_categories=0),
        )
        html = _build_html(report)
        assert "0" in html
        assert "拾讯周报" in html


class TestEmailAdapterSend:
    @pytest.mark.asyncio
    async def test_send_success(self, sample_report):
        adapter = EmailAdapter()
        config = {
            "smtp_host": "smtp.test.com",
            "smtp_port": 465,
            "smtp_user": "user@test.com",
            "smtp_pass": "pass",
            "from_addr": "from@test.com",
            "to_addrs": ["to@test.com"],
            "use_tls": True,
        }
        with patch("smtplib.SMTP_SSL") as mock_smtp:
            mock_instance = mock_smtp.return_value.__enter__.return_value
            result = await adapter.send(sample_report, config)
            assert result is True
            mock_instance.login.assert_called_once_with("user@test.com", "pass")
            mock_instance.sendmail.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_empty_recipients(self, sample_report):
        adapter = EmailAdapter()
        config = {"to_addrs": [], "smtp_host": "x", "smtp_port": 25, "smtp_user": "x", "smtp_pass": "x"}
        with pytest.raises(ValueError, match="收件人列表为空"):
            await adapter.send(sample_report, config)
