"""FastAPI 应用入口（PRD 5.1）。"""
import logging
import uuid
from contextlib import asynccontextmanager

from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.scheduler import scheduler
from app.models.allowed_domain import AllowedDomain
from app.modules.admin.routes import router as admin_router
from app.modules.ai.routes import router as ai_router
from app.modules.ai.service import scan_analyzing_timeouts
from app.modules.articles.routes import router as articles_router
from app.modules.auth.routes import router as auth_router
from app.modules.crawler.renderer import renderer
from app.modules.crawler.proxy_pool import proxy_pool
from app.modules.crawler.routes import router as crawler_router
from app.modules.crawler.ws_routes import router as crawler_ws_router
from app.modules.discovery.routes import router as discovery_router
from app.modules.distribution.routes import router as distribution_router
from app.modules.wechat_format.routes import router as wechat_format_router
from app.modules.distribution.service import dispatch_weekly_report

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("shixun")


async def _seed_allowed_domains():
    """allowed_domains 为空时从 ALLOWED_DOMAINS env 注入种子。"""
    seeds = settings.allowed_domains_list
    if not seeds:
        return
    async with AsyncSessionLocal() as session:
        existing = (await session.execute(select(func.count(AllowedDomain.id)))).scalar_one()
        if existing and existing > 0:
            return
        for pattern in seeds:
            session.add(
                AllowedDomain(
                    domain_pattern=pattern,
                    match_mode="suffix",
                    enabled=True,
                    auto_added=False,
                    source="env_seed",
                    remark="initial seed from ALLOWED_DOMAINS env",
                )
            )
        await session.commit()
        logger.info("seeded %s allowed domains from env", len(seeds))


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _seed_allowed_domains()
    await proxy_pool.startup(settings.proxy_list_parsed if settings.PROXY_ENABLED else [])
    await renderer.startup()

    # 启动时清理僵尸任务（上次重启遗留的 running/pending）
    from app.modules.crawler.service import scan_stale_running_tasks
    stale = await scan_stale_running_tasks(timeout_sec=600)
    if stale:
        logger.info("startup: cleaned %s stale running tasks", stale)

    if not scheduler.running:
        scheduler.start()
    scheduler.add_job(
        scan_analyzing_timeouts,
        id="analyzing_timeout_scan",
        trigger=IntervalTrigger(seconds=120),
        replace_existing=True,
    )
    from apscheduler.triggers.cron import CronTrigger
    scheduler.add_job(
        dispatch_weekly_report,
        id="weekly_digest",
        trigger=CronTrigger(day_of_week="mon", hour=8, minute=30),
        replace_existing=True,
    )
    from app.modules.crawler.scheduled_service import restore_scheduled_crawls
    await restore_scheduled_crawls()

    logger.info("shixun backend ready")
    try:
        yield
    finally:
        try:
            scheduler.shutdown(wait=False)
        except Exception:
            pass
        await proxy_pool.shutdown()
        await renderer.shutdown()


app = FastAPI(title="拾讯后端", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    rid = request.headers.get("x-request-id") or str(uuid.uuid4())
    request.state.request_id = rid
    response = await call_next(request)
    response.headers["x-request-id"] = rid
    return response


@app.exception_handler(StarletteHTTPException)
async def http_exc_handler(request: Request, exc: StarletteHTTPException):
    if isinstance(exc.detail, dict) and "code" in exc.detail:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.detail.get("code", exc.status_code),
                "message": exc.detail.get("message", "error"),
                "data": None,
                "request_id": getattr(request.state, "request_id", None),
            },
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.status_code,
            "message": str(exc.detail),
            "data": None,
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exc_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "code": 1002,
            "message": "请求参数校验失败",
            "data": exc.errors(),
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@app.get("/health")
async def health():
    return {"status": "ok", "service": "shixun-backend"}


app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(crawler_router)
app.include_router(crawler_ws_router)
app.include_router(discovery_router)
app.include_router(ai_router)
app.include_router(articles_router)
app.include_router(distribution_router)
app.include_router(wechat_format_router)
