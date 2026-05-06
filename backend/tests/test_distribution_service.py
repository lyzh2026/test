"""测试 WeeklyDigestService。"""
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from app.models.article import Article
from app.models.ai_analysis import AIAnalysis
from app.modules.distribution.schemas import WeeklyReport
from app.modules.distribution.service import WeeklyDigestService, _parse_year_week


class TestParseYearWeek:
    def test_2026_w18(self):
        monday, sunday = _parse_year_week("2026-W18")
        assert monday == date(2026, 4, 27)
        assert sunday == date(2026, 5, 3)

    def test_2026_w01(self):
        monday, sunday = _parse_year_week("2026-W01")
        assert monday == date(2025, 12, 29)
        assert sunday == date(2026, 1, 4)


class TestGenerateWeeklyReport:
    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    def _make_article(self, title: str, cat: str, day_offset: int = 0):
        article = MagicMock(spec=Article)
        article.original_title = title
        article.original_link = f"https://example.com/{title}"
        article.publish_date = date(2026, 4, 27 + day_offset)
        article.source_unit = "测试来源"
        article.status = "processed"
        article.ai_analysis = MagicMock(spec=AIAnalysis)
        article.ai_analysis.summary = f"{title}的摘要"
        article.ai_analysis.categories = [cat]
        return article

    @pytest.mark.asyncio
    async def test_happy_path(self, mock_session):
        """正常生成周报：文章按分类分组，降序排列。"""
        articles = [
            self._make_article("文章A", "最新政策", 0),
            self._make_article("文章B", "人工智能", 1),
            self._make_article("文章C", "最新政策", 2),
        ]
        mock_result = MagicMock()
        mock_result.unique.return_value.scalars.return_value.all.return_value = articles
        mock_session.execute = AsyncMock(return_value=mock_result)

        svc = WeeklyDigestService(mock_session)
        report = await svc.generate_weekly_report("2026-W18")

        assert isinstance(report, WeeklyReport)
        assert report.year_week == "2026-W18"
        assert report.stats.total_articles == 3
        cat_names = [c.name for c in report.categories]
        assert "最新政策" in cat_names
        assert "其他" in cat_names
        assert "人工智能" not in cat_names

    @pytest.mark.asyncio
    async def test_empty_week(self, mock_session):
        """无文章时正常返回空列表。"""
        mock_result = MagicMock()
        mock_result.unique.return_value.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        svc = WeeklyDigestService(mock_session)
        report = await svc.generate_weekly_report("2026-W18")

        assert report.stats.total_articles == 0
        assert report.categories == []

    @pytest.mark.asyncio
    async def test_no_ai_analysis(self, mock_session):
        """文章无 AI 分析结果时正确读取。"""
        article = self._make_article("无分析文章", "最新政策", 0)
        article.ai_analysis = None
        mock_result = MagicMock()
        mock_result.unique.return_value.scalars.return_value.all.return_value = [article]
        mock_session.execute = AsyncMock(return_value=mock_result)

        svc = WeeklyDigestService(mock_session)
        report = await svc.generate_weekly_report("2026-W18")

        assert report.stats.total_articles == 1
        assert report.categories[0].articles[0].summary == ""
