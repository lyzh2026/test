"""APScheduler 单例（PRD 5.5 / 2.2.7 配置）。"""
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import settings

_jobstores = {
    "default": SQLAlchemyJobStore(url=settings.DATABASE_URL_SYNC, tablename="apscheduler_jobs"),
}

_executors = {
    "default": AsyncIOExecutor(),
}

_job_defaults = {
    "coalesce": False,
    "misfire_grace_time": 300,
    "max_instances": 4,
    "replace_existing": True,
}

scheduler = AsyncIOScheduler(
    jobstores=_jobstores,
    executors=_executors,
    job_defaults=_job_defaults,
    timezone="Asia/Shanghai",
)
