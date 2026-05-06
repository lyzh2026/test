"""爬虫任务相关 HTTP 路由（PRD 3.2.1）。"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.scheduler import scheduler
from app.dependencies.auth import current_admin
from app.modules.crawler import service
from app.schemas.crawler import AIBrowseRequest, BatchDeleteRequest, CrawlerTaskCreate
from app.utils.response import error, success
from app.utils.url_validator import URLValidationError

router = APIRouter(prefix="/api/v1/crawler", tags=["crawler"])


def _serialize_task(task) -> dict:
    return {
        "id": str(task.id),
        "task_name": task.task_name,
        "target_date": task.target_date.isoformat() if task.target_date else None,
        "date_to": task.date_to.isoformat() if task.date_to else None,
        "url_list": task.url_list or [],
        "total_urls": task.total_urls,
        "completed_urls": task.completed_urls,
        "failed_urls": task.failed_urls,
        "failed_details": task.failed_details or [],
        "status": task.status,
        "callback_url": task.callback_url,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "created_at": task.created_at.isoformat() if task.created_at else None,
    }


@router.post("/task")
async def create_task(
    payload: CrawlerTaskCreate,
    request: Request,
    _: object = Depends(current_admin),
    session: AsyncSession = Depends(get_session),
):
    try:
        task = await service.submit_task(
            session=session,
            url_list=payload.url_list,
            direct_urls=payload.direct_urls,
            target_date=payload.target_date,
            date_to=payload.date_to,
            task_name=payload.task_name,
            callback_url=payload.callback_url,
        )
    except URLValidationError as e:
        return error(e.code, e.message, http_status=400, request=request)
    return success({"task_id": str(task.id), "status": task.status, "total_urls": task.total_urls,
                    "failed_urls": task.failed_urls}, request=request)


@router.get("/tasks")
async def list_tasks(
    request: Request,
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status: Optional[str] = Query(default=None),
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    keyword: Optional[str] = Query(default=None),
    _: object = Depends(current_admin),
    session: AsyncSession = Depends(get_session),
):
    tasks, total = await service.list_tasks(
        session, limit=limit, offset=offset,
        status=status, date_from=date_from, date_to=date_to, keyword=keyword,
    )
    return success({"items": [_serialize_task(t) for t in tasks], "total": total, "limit": limit, "offset": offset},
                   request=request)


@router.get("/tasks/{task_id}")
async def get_task_detail(
    task_id: str,
    request: Request,
    _: object = Depends(current_admin),
    session: AsyncSession = Depends(get_session),
):
    task = await service.get_task(session, task_id)
    if not task:
        return error(2003, "任务不存在", http_status=404, request=request)
    return success(_serialize_task(task), request=request)


@router.post("/task/{task_id}/cancel")
async def cancel_task(
    task_id: str,
    request: Request,
    _: object = Depends(current_admin),
):
    """取消正在运行或待处理的任务。"""
    ok = await service.cancel_task(task_id)
    if not ok:
        return error(2004, "任务无法取消（不存在、或状态非 running/pending）", http_status=400, request=request)
    return success({"ok": True}, request=request)


@router.post("/task/{task_id}/retry")
async def retry_task(
    task_id: str,
    request: Request,
    _: object = Depends(current_admin),
    session: AsyncSession = Depends(get_session),
):
    """对 partial_failed / failed 状态的任务发起重试（保留已有进度，只重试失败 URL）。"""
    task = await service.retry_failed_urls(task_id, session)
    if not task:
        return error(2004, "任务无法重试（不存在、状态非 failed/partial_failed、或无失败 URL）", http_status=400, request=request)
    return success(_serialize_task(task), request=request)


@router.post("/task/{task_id}/ai-browse")
async def ai_browse_task(
    task_id: str,
    payload: AIBrowseRequest,
    request: Request,
    _: object = Depends(current_admin),
    session: AsyncSession = Depends(get_session),
):
    """用 AI 联网搜索浏览失败 URL，提取内容入库。"""
    task = await service.get_task(session, task_id)
    if not task:
        return error(2003, "任务不存在", http_status=404, request=request)
    result = await service.ai_browse_urls(task_id, payload.urls, session)
    return success(result, request=request)


@router.delete("/task/{task_id}")
async def delete_task_route(
    task_id: str,
    request: Request,
    _: object = Depends(current_admin),
):
    """删除单个任务（先取消，再删除记录）。"""
    ok = await service.delete_task(task_id)
    if not ok:
        return error(2003, "任务不存在", http_status=404, request=request)
    return success({"ok": True}, request=request)


@router.post("/tasks/batch-delete")
async def batch_delete_tasks_route(
    payload: BatchDeleteRequest,
    request: Request,
    _: object = Depends(current_admin),
):
    """批量删除任务（幂等，不存在的 ID 自动跳过）。"""
    result = await service.batch_delete_tasks(payload.task_ids)
    return success(result, request=request)


# ── 定时爬取 CRUD ──────────────────────────────────────────────

from app.models.scheduled_crawl import ScheduledCrawl
from app.modules.crawler.scheduled_service import run_scheduled_crawl, sync_schedule_job


WEEKDAY_LABELS = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"]


def _serialize_sc(sc: ScheduledCrawl) -> dict:
    return {
        "id": str(sc.id),
        "name": sc.name,
        "url_list": sc.url_list or [],
        "weekdays": sc.weekdays or [],
        "weekday_labels": [WEEKDAY_LABELS[d] for d in (sc.weekdays or [])],
        "email_config_id": str(sc.email_config_id),
        "enabled": sc.enabled,
        "last_run_at": sc.last_run_at.isoformat() if sc.last_run_at else None,
        "last_task_id": str(sc.last_task_id) if sc.last_task_id else None,
        "created_at": sc.created_at.isoformat() if sc.created_at else None,
    }


@router.get("/scheduled-crawls")
async def list_scheduled_crawls(
    request: Request,
    _: object = Depends(current_admin),
    session: AsyncSession = Depends(get_session),
):
    res = await session.execute(select(ScheduledCrawl).order_by(ScheduledCrawl.created_at.desc()))
    items = res.scalars().all()
    return success({"items": [_serialize_sc(sc) for sc in items]}, request=request)


@router.post("/scheduled-crawls")
async def create_scheduled_crawl(
    payload: dict,
    request: Request,
    _: object = Depends(current_admin),
    session: AsyncSession = Depends(get_session),
):
    name = (payload.get("name") or "").strip()
    url_list = payload.get("url_list", [])
    weekdays = payload.get("weekdays", [])
    email_config_id = payload.get("email_config_id", "")
    enabled = payload.get("enabled", True)

    if not name:
        return error(1001, "任务名称不能为空", http_status=400, request=request)
    if not url_list or not isinstance(url_list, list):
        return error(1001, "URL 列表不能为空", http_status=400, request=request)
    if not weekdays or not isinstance(weekdays, list):
        return error(1001, "请选择执行日", http_status=400, request=request)
    if not email_config_id:
        return error(1001, "请选择邮件通道", http_status=400, request=request)

    # 校验邮件通道存在且为 email 类型
    from app.models.distribution import DistributionConfig
    cfg = await session.get(DistributionConfig, email_config_id)
    if not cfg or cfg.channel_type != "email":
        return error(1003, "邮件通道不存在", http_status=400, request=request)

    sc = ScheduledCrawl(
        name=name,
        url_list=url_list,
        weekdays=weekdays,
        email_config_id=email_config_id,
        enabled=enabled,
    )
    session.add(sc)
    await session.commit()
    await session.refresh(sc)

    if enabled:
        sync_schedule_job(sc.id, weekdays, True)

    return success(_serialize_sc(sc), request=request)


@router.put("/scheduled-crawls/{sc_id}")
async def update_scheduled_crawl(
    sc_id: str,
    payload: dict,
    request: Request,
    _: object = Depends(current_admin),
    session: AsyncSession = Depends(get_session),
):
    sc = await session.get(ScheduledCrawl, sc_id)
    if not sc:
        return error(2003, "定时任务不存在", http_status=404, request=request)

    if "name" in payload:
        sc.name = payload["name"].strip()
    if "url_list" in payload:
        sc.url_list = payload["url_list"]
    if "weekdays" in payload:
        sc.weekdays = payload["weekdays"]
    if "email_config_id" in payload:
        sc.email_config_id = payload["email_config_id"]
    if "enabled" in payload:
        sc.enabled = payload["enabled"]

    await session.commit()
    await session.refresh(sc)

    sync_schedule_job(sc.id, sc.weekdays, sc.enabled)

    return success(_serialize_sc(sc), request=request)


@router.delete("/scheduled-crawls/{sc_id}")
async def delete_scheduled_crawl(
    sc_id: str,
    request: Request,
    _: object = Depends(current_admin),
    session: AsyncSession = Depends(get_session),
):
    sc = await session.get(ScheduledCrawl, sc_id)
    if not sc:
        return error(2003, "定时任务不存在", http_status=404, request=request)

    sync_schedule_job(sc.id, [], False)
    await session.delete(sc)
    await session.commit()
    return success({"ok": True}, request=request)


@router.post("/scheduled-crawls/{sc_id}/toggle")
async def toggle_scheduled_crawl(
    sc_id: str,
    request: Request,
    _: object = Depends(current_admin),
    session: AsyncSession = Depends(get_session),
):
    sc = await session.get(ScheduledCrawl, sc_id)
    if not sc:
        return error(2003, "定时任务不存在", http_status=404, request=request)

    sc.enabled = not sc.enabled
    await session.commit()
    await session.refresh(sc)

    sync_schedule_job(sc.id, sc.weekdays, sc.enabled)

    return success(_serialize_sc(sc), request=request)


@router.post("/scheduled-crawls/{sc_id}/run")
async def run_scheduled_crawl_now(
    sc_id: str,
    request: Request,
    _: object = Depends(current_admin),
    session: AsyncSession = Depends(get_session),
):
    """立即执行一次定时爬取。"""
    sc = await session.get(ScheduledCrawl, sc_id)
    if not sc:
        return error(2003, "定时任务不存在", http_status=404, request=request)
    if not sc.url_list:
        return error(1001, "URL 列表为空", http_status=400, request=request)

    from apscheduler.triggers.date import DateTrigger
    from datetime import datetime, timezone

    scheduler.add_job(
        run_scheduled_crawl,
        id=f"manual_scheduled_crawl:{sc_id}",
        args=[str(sc_id)],
        trigger=DateTrigger(run_date=datetime.now(timezone.utc)),
        replace_existing=True,
    )
    return success({"message": "已触发立即执行"}, request=request)
