"""AI 分析 HTTP 路由：手动触发单篇文章分析。"""
from fastapi import APIRouter, Depends, Request

from app.dependencies.auth import current_admin
from app.modules.ai.service import analyze_article
from app.utils.response import error, success

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])


@router.post("/analyze/{article_id}")
async def trigger_analyze(article_id: str, request: Request, _: object = Depends(current_admin)):
    res = await analyze_article(article_id)
    if not res.get("ok"):
        return error(2002, f"分析失败：{res.get('reason')}", http_status=400, request=request)
    return success(res, request=request)
