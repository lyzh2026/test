"""爬虫任务相关 HTTP 路由（PRD 3.2.1）。"""
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.dependencies.auth import current_admin
from app.modules.crawler import service
from app.schemas.crawler import BatchDeleteRequest, CrawlerTaskCreate
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
        "priority": task.priority,
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
            priority=payload.priority,
        )
    except URLValidationError as e:
        return error(e.code, e.message, http_status=400, request=request)
    return success({"task_id": str(task.id), "status": task.status, "total_urls": task.total_urls,
                    "failed_urls": task.failed_urls}, request=request)


@router.get("/tasks")
async def list_tasks(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: object = Depends(current_admin),
    session: AsyncSession = Depends(get_session),
):
    tasks = await service.list_tasks(session, limit=limit, offset=offset)
    return success({"items": [_serialize_task(t) for t in tasks], "limit": limit, "offset": offset},
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
