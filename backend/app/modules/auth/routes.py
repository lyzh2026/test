"""登录 / 退出 / 获取当前用户。"""
import secrets

from fastapi import APIRouter, Request, Response

from app.core.config import settings
from app.core.redis import redis as redis_client
from app.core.security import create_session_token
from app.dependencies.auth import current_admin
from app.schemas.auth import CurrentUser, LoginRequest
from app.utils.response import error, success
from fastapi import Depends

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

_LOGIN_MAX_FAILS = 5
_LOGIN_WINDOW_SEC = 900  # 15 分钟


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/login")
async def login(payload: LoginRequest, request: Request, response: Response):
    ip = _client_ip(request)
    key = f"login_fail:{ip}"

    # 检查是否超限
    try:
        fails = await redis_client.get(key)
        if fails and int(fails) >= _LOGIN_MAX_FAILS:
            return error(4290, "登录失败次数过多，请 15 分钟后重试", http_status=429, request=request)
    except Exception:
        pass  # Redis 不可用时跳过限流

    if payload.username != settings.ADMIN_USERNAME:
        return error(4001, "用户名或密码错误", http_status=401, request=request)
    if not secrets.compare_digest(payload.password, settings.ADMIN_PASSWORD):
        # 记录失败次数
        try:
            pipe = redis_client.pipeline()
            pipe.incr(key)
            pipe.expire(key, _LOGIN_WINDOW_SEC)
            await pipe.execute()
        except Exception:
            pass
        return error(4001, "用户名或密码错误", http_status=401, request=request)

    # 登录成功，清除失败计数
    try:
        await redis_client.delete(key)
    except Exception:
        pass

    token = create_session_token(payload.username)
    resp = success({"username": payload.username}, request=request)
    resp.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return resp


@router.post("/logout")
async def logout(request: Request):
    resp = success({"ok": True}, request=request)
    resp.delete_cookie(settings.SESSION_COOKIE_NAME, path="/")
    return resp


@router.get("/me")
async def me(request: Request, user: CurrentUser = Depends(current_admin)):
    return success({"username": user.username}, request=request)
