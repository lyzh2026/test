"""定时爬取引擎：管理 ScheduledCrawl 的调度、执行和邮件推送。"""
import asyncio
import logging
from datetime import date, datetime, timedelta, timezone

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.core.database import AsyncSessionLocal
from app.core.scheduler import scheduler
from app.models.article import Article
from app.models.crawler_task import CrawlerTask
from app.models.distribution import DistributionConfig
from app.models.scheduled_crawl import ScheduledCrawl

logger = logging.getLogger("shixun.scheduled_crawl")


async def restore_scheduled_crawls():
    """启动时从 DB 恢复所有启用的定时爬取任务，并补跑错过的执行。"""
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(ScheduledCrawl).where(ScheduledCrawl.enabled.is_(True))
        )
        items = res.scalars().all()

    today = date.today()
    catch_up_count = 0

    for sc in items:
        _register_job(sc.id, sc.weekdays)

        # 补跑检查：上次执行日到今天之间是否有错过的执行日
        if sc.weekdays:
            missed = _find_missed_run_day(sc.weekdays, sc.last_run_at, today)
            if missed is not None:
                logger.info("定时爬取补跑: %s (错过的执行日: %s)", sc.name, missed.isoformat())
                scheduler.add_job(
                    run_scheduled_crawl,
                    id=f"catchup_scheduled_crawl:{sc.id}:{missed.isoformat()}",
                    args=[str(sc.id)],
                    trigger=DateTrigger(run_date=datetime.now(timezone.utc)),
                    replace_existing=True,
                )
                catch_up_count += 1

    if items:
        logger.info("已恢复 %d 个定时爬取任务，补跑 %d 个", len(items), catch_up_count)


def _find_missed_run_day(weekdays: list, last_run_at, today: date) -> date | None:
    """检查上次执行到今天之间是否有错过的执行日。返回最近一个错过的日期，或 None。"""
    weekdays_set = set(weekdays)

    if last_run_at is None:
        # 从未执行过，如果今天是执行日则补跑
        if today.isoweekday() % 7 in weekdays_set:  # isoweekday: 1=mon..7=sun → 0=sun..6=sat
            return today
        return None

    # last_run_at 可能是带 timezone 的 datetime
    last_run_date = last_run_at.date() if hasattr(last_run_at, 'date') else last_run_at

    # 已经今天跑过了，不需要补跑
    if last_run_date >= today:
        return None

    # 检查 last_run_date（不含）到 today（含）之间的每一天
    check = last_run_date + timedelta(days=1)
    missed_days = []
    while check <= today:
        # date.isoweekday(): 1=Mon..7=Sun → 我们的编码: 0=Sun,1=Mon..6=Sat
        our_weekday = check.isoweekday() % 7
        if our_weekday in weekdays_set:
            missed_days.append(check)
        check += timedelta(days=1)

    # 返回最近一个错过的执行日（只补跑一次，不重复补跑多天）
    return missed_days[-1] if missed_days else None


def _register_job(schedule_id, weekdays: list):
    """为定时爬取注册 APScheduler CronTrigger job。"""
    if not weekdays:
        return
    # APScheduler CronTrigger day_of_week: 0=mon..6=sun, 我们存储 0=sun..6=sat
    # 转换: 0(sun)→6, 1(mon)→0, 2(tue)→1, ... 6(sat)→5
    ap_days = []
    for d in weekdays:
        ap_days.append(str((d - 1) % 7))
    day_of_week = ",".join(ap_days)

    scheduler.add_job(
        run_scheduled_crawl,
        id=f"scheduled_crawl:{schedule_id}",
        args=[str(schedule_id)],
        trigger=CronTrigger(day_of_week=day_of_week, hour=8, minute=0),
        replace_existing=True,
    )


def sync_schedule_job(schedule_id, weekdays: list, enabled: bool):
    """创建/编辑/启用禁用时同步 APScheduler job。"""
    job_id = f"scheduled_crawl:{schedule_id}"
    try:
        scheduler.remove_job(job_id)
    except Exception:
        pass
    if enabled and weekdays:
        _register_job(schedule_id, weekdays)


async def run_scheduled_crawl(schedule_id: str):
    """APScheduler 入口：创建爬取任务 → 等待完成 → 逐篇发送邮件。"""
    logger.info("定时爬取触发: %s", schedule_id)

    async with AsyncSessionLocal() as session:
        sc = await session.get(ScheduledCrawl, schedule_id)
        if not sc or not sc.enabled:
            logger.warning("定时任务不存在或已禁用: %s", schedule_id)
            return

        url_list = sc.url_list or []
        if not url_list:
            logger.warning("定时任务无 URL: %s", schedule_id)
            return

        # 获取邮件通道配置
        cfg = await session.get(DistributionConfig, sc.email_config_id)
        if not cfg or not cfg.enabled:
            logger.warning("邮件通道不存在或已禁用: %s", sc.email_config_id)
            return

        smtp_config = cfg.config

        # 复用现有爬取链路
        from app.modules.crawler.service import submit_task

        try:
            task = await submit_task(
                session=session,
                url_list=url_list,
                target_date=date.today(),
                task_name=f"定时爬取 - {sc.name}",
                callback_url=None,
            )
        except Exception as e:
            logger.error("定时爬取创建任务失败: %s %r", schedule_id, e)
            return

        # 更新定时任务状态
        sc.last_run_at = datetime.now(timezone.utc)
        sc.last_task_id = task.id
        await session.commit()

    # 注册后处理：等待爬取完成后逐篇发送邮件
    scheduler.add_job(
        _post_crawl_send,
        id=f"post_crawl_send:{schedule_id}",
        args=[str(schedule_id), str(task.id), smtp_config],
        trigger=DateTrigger(run_date=datetime.now(timezone.utc)),
        replace_existing=True,
    )


async def _post_crawl_send(schedule_id: str, task_id: str, smtp_config: dict):
    """等待爬取完成后，逐篇发送新文章邮件。"""
    # 轮询等待任务完成（最多等 30 分钟）
    for _ in range(180):
        await asyncio.sleep(10)
        async with AsyncSessionLocal() as session:
            task = await session.get(CrawlerTask, task_id)
            if not task:
                return
            if task.status in ("completed", "partial_failed", "failed", "cancelled"):
                break
    else:
        logger.warning("定时爬取等待超时: schedule=%s task=%s", schedule_id, task_id)
        return

    # 查询该任务关联的新文章
    async with AsyncSessionLocal() as session:
        sc = await session.get(ScheduledCrawl, schedule_id)
        if not sc:
            return

        res = await session.execute(
            select(Article)
            .options(joinedload(Article.ai_analysis))
            .where(Article.task_id == task_id)
        )
        articles = res.unique().scalars().all()

    if not articles:
        logger.info("定时爬取无新文章: schedule=%s task=%s", schedule_id, task_id)
        return

    # 逐篇发送邮件
    from app.modules.distribution.service import send_article_email

    sent, failed = 0, 0
    for article in articles:
        try:
            await send_article_email(article, smtp_config)
            sent += 1
            logger.info("定时推送邮件成功: %s", article.original_title[:50])
        except Exception as e:
            failed += 1
            logger.error("定时推送邮件失败: %s %r", article.original_title[:50], e)

    logger.info(
        "定时爬取邮件推送完成: schedule=%s task=%s 发送=%d 失败=%d",
        schedule_id, task_id, sent, failed,
    )
