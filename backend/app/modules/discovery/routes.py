"""站点发现 API：扫描入口页自动发现文章链接，并支持一键转爬取任务。"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.dependencies.auth import current_admin
from app.modules.crawler import service as crawler_service
from app.modules.discovery import service as discovery_service
from app.schemas.discovery import DiscoveryScanRequest, DiscoveryTaskCreate
from app.utils.response import error, success

router = APIRouter(prefix="/api/v1/discovery", tags=["discovery"])


@router.post("/scan")
async def scan_links(
    payload: DiscoveryScanRequest,
    request: Request,
    _: object = Depends(current_admin),
):
    """扫描入口页，返回发现到的文章链接列表（不创建任务）。"""
    links = await discovery_service.discover_articles(
        entry_url=payload.entry_url,
        max_depth=payload.max_depth,
        max_links=payload.max_links,
        enable_pagination=payload.enable_pagination,
        max_pages=payload.max_pages,
    )
    return success(
        {
            "entry_url": payload.entry_url,
            "links": links,
            "count": len(links),
        },
        request=request,
    )


@router.post("/task")
async def create_discovery_task(
    payload: DiscoveryTaskCreate,
    request: Request,
    _: object = Depends(current_admin),
    session: AsyncSession = Depends(get_session),
):
    """扫描入口页发现链接，直接创建爬取任务。"""
    links = await discovery_service.discover_articles(
        entry_url=payload.entry_url,
        max_depth=payload.max_depth,
        max_links=payload.max_links,
        enable_pagination=payload.enable_pagination,
        max_pages=payload.max_pages,
    )
    if not links:
        return error(
            3001,
            "未发现符合条件的文章链接",
            http_status=400,
            request=request,
        )

    url_list = [item["url"] for item in links]
    try:
        task = await crawler_service.submit_task(
            session=session,
            url_list=url_list,
            target_date=payload.target_date,
            date_to=payload.date_to,
            task_name=payload.task_name,
            callback_url=None,
            priority=payload.priority,
        )
    except Exception as e:
        return error(
            3002,
            f"创建爬取任务失败：{e!r}",
            http_status=500,
            request=request,
        )

    return success(
        {
            "task_id": str(task.id),
            "discovered_count": len(links),
            "total_urls": task.total_urls,
            "status": task.status,
        },
        request=request,
    )
