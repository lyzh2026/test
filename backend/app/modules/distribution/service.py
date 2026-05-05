"""周报生成与分发核心服务。"""
import logging
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.ai_analysis import AIAnalysis
from app.models.article import Article
from app.modules.distribution.adapters.base import DistributionAdapter
from app.modules.distribution.schemas import ArticleItem, CategoryGroup, ReportStats, WeeklyReport

logger = logging.getLogger("shixun.distribution")


def _parse_year_week(year_week: str) -> tuple[date, date]:
    """将 '2026-W18' 转换为 (周一日期, 周日日期)。"""
    year = int(year_week[:4])
    week = int(year_week[6:])
    jan4 = date(year, 1, 4)
    start_of_week1 = jan4 - timedelta(days=jan4.isoweekday() - 1)
    monday = start_of_week1 + timedelta(weeks=week - 1)
    sunday = monday + timedelta(days=6)
    return monday, sunday


def _get_current_year_week() -> str:
    """获取上周的 year_week 字符串（因为周报发的是上周数据）。"""
    today = date.today()
    iso = today.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


class WeeklyDigestService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def generate_weekly_report(self, year_week: str | None = None) -> WeeklyReport:
        """生成指定周的周报。"""
        if year_week is None:
            year_week = _get_current_year_week()

        monday, sunday = _parse_year_week(year_week)

        stmt = (
            select(Article)
            .options(joinedload(Article.ai_analysis))
            .where(
                Article.publish_date.between(monday, sunday),
                Article.status == "processed",
            )
            .order_by(Article.publish_date.desc())
        )
        result = await self.session.execute(stmt)
        articles = result.unique().scalars().all()

        category_map: dict[str, list[ArticleItem]] = {}
        for article in articles:
            cats = []
            if article.ai_analysis and article.ai_analysis.categories:
                cats = article.ai_analysis.categories
            cat_name = cats[0] if cats else "其他"

            item = ArticleItem(
                title=article.original_title,
                summary=article.ai_analysis.summary if article.ai_analysis else "",
                url=article.original_link,
                publish_date=article.publish_date,
                source_unit=article.source_unit or "",
            )
            if cat_name not in category_map:
                category_map[cat_name] = []
            category_map[cat_name].append(item)

        sorted_cats = sorted(category_map.items(), key=lambda x: len(x[1]), reverse=True)
        merged: list[CategoryGroup] = []
        others: list[ArticleItem] = []
        for name, items in sorted_cats:
            if len(items) < 2:
                others.extend(items)
            else:
                merged.append(CategoryGroup(name=name, articles=items))

        if others:
            merged.append(CategoryGroup(name="其他", articles=others))

        return WeeklyReport(
            year_week=year_week,
            date_range_start=monday,
            date_range_end=sunday,
            categories=merged,
            stats=ReportStats(
                total_articles=len(articles),
                total_categories=len(merged),
            ),
        )


async def preview_report(session: AsyncSession, week: str | None = None, channel_type: str = "email") -> dict:
    """预览周报渲染效果。"""
    from app.modules.distribution.adapters.email_adapter import _build_html
    from app.modules.distribution.adapters.webhook_adapter import _build_feishu_card

    svc = WeeklyDigestService(session)
    report = await svc.generate_weekly_report(week)

    if channel_type == "webhook":
        return {"channel_type": "webhook", "content": _build_feishu_card(report)}
    html = _build_html(report)
    return {"channel_type": "email", "content": html}


def _get_adapter(channel_type: str) -> DistributionAdapter | None:
    from app.modules.distribution.adapters.email_adapter import EmailAdapter
    from app.modules.distribution.adapters.webhook_adapter import WebhookAdapter

    if channel_type == "email":
        return EmailAdapter()
    elif channel_type == "webhook":
        return WebhookAdapter()
    return None


async def dispatch_weekly_report():
    """APScheduler 入口：生成并分发周报。"""
    from app.core.database import AsyncSessionLocal
    from app.models.distribution import DistributionConfig, DistributionLog

    async with AsyncSessionLocal() as session:
        svc = WeeklyDigestService(session)
        year_week = _get_current_year_week()

        try:
            report = await svc.generate_weekly_report(year_week)
        except Exception as e:
            logger.error("周报生成失败: %s", e)
            return

        result = await session.execute(
            select(DistributionConfig).where(DistributionConfig.enabled == True)
        )
        configs = result.scalars().all()

        if not configs:
            logger.info("无启用的分发通道，周报跳过")
            return

        for cfg in configs:
            adapter = _get_adapter(cfg.channel_type)
            if adapter is None:
                logger.warning("未知通道类型: %s", cfg.channel_type)
                continue

            log_entry = DistributionLog(
                config_id=cfg.id,
                config_name=cfg.name,
                channel_type=cfg.channel_type,
                report_week=year_week,
                date_range_start=report.date_range_start,
                date_range_end=report.date_range_end,
                status="failed",
                article_count=report.stats.total_articles,
                category_count=report.stats.total_categories,
            )

            try:
                await adapter.send(report, cfg.config)
                log_entry.status = "success"
                logger.info("周报分发成功: %s (%s)", cfg.name, cfg.channel_type)
            except Exception as e:
                log_entry.error_message = str(e)[:500]
                logger.error("周报分发失败: %s (%s): %s", cfg.name, cfg.channel_type, e)

            session.add(log_entry)

        await session.commit()
