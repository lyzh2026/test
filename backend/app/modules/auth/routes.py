"""登录 / 退出 / 获取当前用户。"""
import secrets

from fastapi import APIRouter, Request, Response

from app.core.config import settings
from app.core.security import create_session_token
from app.dependencies.auth import current_admin
from app.schemas.auth import CurrentUser, LoginRequest
from app.utils.response import error, success
from fastapi import Depends

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login")
async def login(payload: LoginRequest, request: Request, response: Response):
    if payload.username != settings.ADMIN_USERNAME:
        return error(4001, "用户名或密码错误", http_status=401, request=request)
    if not secrets.compare_digest(payload.password, settings.ADMIN_PASSWORD):
        return error(4001, "用户名或密码错误", http_status=401, request=request)

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
