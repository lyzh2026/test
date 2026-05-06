"""WebSocket 路由：任务进度实时推送。"""
import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import settings
from app.core.security import verify_session_token
from app.modules.crawler.progress_bus import progress_bus

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/crawler", tags=["crawler-ws"])


@router.websocket("/ws/task/{task_id}")
async def task_progress_ws(websocket: WebSocket, task_id: str):
    # 鉴权：从 cookie 读取 session token
    token = websocket.cookies.get(settings.SESSION_COOKIE_NAME)
    if not token or not verify_session_token(token):
        await websocket.close(code=4001)
        return

    await websocket.accept()
    logger.info("ws connected: task=%s", task_id)

    def send(data: str):
        try:
            asyncio.ensure_future(websocket.send_text(data))
        except Exception:
            pass

    progress_bus.subscribe(task_id, send)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        logger.info("ws disconnected: task=%s", task_id)
    finally:
        progress_bus.unsubscribe(task_id, send)
