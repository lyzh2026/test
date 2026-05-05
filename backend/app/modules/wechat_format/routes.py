from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import PlainTextResponse, HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.response import success, error
from app.core.database import get_session
from app.dependencies.auth import current_admin
from .service import render_article, export_markdown, export_html

router = APIRouter(prefix="/api/v1/wechat", tags=["wechat"])


@router.get("/format/{article_id}")
async def format_for_wechat(
    article_id: str,
    request: Request,
    template: str = Query(default="green-simple", max_length=32),
    _: object = Depends(current_admin),
    session: AsyncSession = Depends(get_session),
):
    try:
        result = await render_article(session, article_id, template)
        return success(result, request=request)
    except ValueError as e:
        return error(2004, str(e), http_status=400, request=request)


@router.get("/export/markdown/{article_id}")
async def download_markdown(
    article_id: str,
    _: object = Depends(current_admin),
    session: AsyncSession = Depends(get_session),
):
    try:
        title, content = await export_markdown(session, article_id)
        safe_name = "".join(c if c.isascii() and (c.isalnum() or c in " _-") else "_" for c in title)
        return PlainTextResponse(
            content,
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="{safe_name}.md"'},
        )
    except ValueError as e:
        return error(2004, str(e), http_status=400)


@router.get("/export/html/{article_id}")
async def download_html(
    article_id: str,
    template: str = Query(default="green-simple", max_length=32),
    _: object = Depends(current_admin),
    session: AsyncSession = Depends(get_session),
):
    try:
        title, content = await export_html(session, article_id, template)
        safe_name = "".join(c if c.isascii() and (c.isalnum() or c in " _-") else "_" for c in title)
        return HTMLResponse(
            content,
            media_type="text/html",
            headers={"Content-Disposition": f'attachment; filename="{safe_name}.html"'},
        )
    except ValueError as e:
        return error(2004, str(e), http_status=400)
