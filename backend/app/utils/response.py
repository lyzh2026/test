"""统一响应格式（PRD 3.1）。"""
from typing import Any
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse


def make_response(
    data: Any = None,
    code: int = 0,
    message: str = "success",
    request_id: str | None = None,
    http_status: int = 200,
) -> JSONResponse:
    body = {
        "code": code,
        "message": message,
        "data": data,
        "request_id": request_id or str(uuid4()),
    }
    return JSONResponse(content=body, status_code=http_status)


def success(data: Any = None, request: Request | None = None, http_status: int = 200) -> JSONResponse:
    rid = getattr(request.state, "request_id", None) if request else None
    return make_response(data=data, code=0, message="success", request_id=rid, http_status=http_status)


def error(
    code: int,
    message: str,
    http_status: int = 400,
    data: Any = None,
    request: Request | None = None,
) -> JSONResponse:
    rid = getattr(request.state, "request_id", None) if request else None
    return make_response(data=data, code=code, message=message, request_id=rid, http_status=http_status)
