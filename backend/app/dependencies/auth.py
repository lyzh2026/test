"""鉴权依赖：从 Cookie 读取 session token 并校验。"""
from fastapi import HTTPException, Request, status

from app.core.config import settings
from app.core.security import verify_session_token
from app.schemas.auth import CurrentUser


async def current_admin(request: Request) -> CurrentUser:
    token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 4001, "message": "未登录"},
        )
    username = verify_session_token(token)
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 4001, "message": "Session 失效"},
        )
    return CurrentUser(username=username)
