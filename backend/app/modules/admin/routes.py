"""白名单 CRUD API。"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.dependencies.auth import current_admin
from app.models.allowed_domain import AllowedDomain
from app.utils.response import error, success

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def _serialize(item: AllowedDomain) -> dict:
    return {
        "id": str(item.id),
        "domain_pattern": item.domain_pattern,
        "match_mode": item.match_mode,
        "enabled": item.enabled,
        "auto_added": item.auto_added,
        "source": item.source,
        "remark": item.remark,
        "created_by": item.created_by,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


@router.get("/allowlist")
async def list_allowed(
    request: Request,
    _: object = Depends(current_admin),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(AllowedDomain)
        .where(AllowedDomain.deleted_at.is_(None))
        .order_by(AllowedDomain.created_at.desc())
    )
    items = result.scalars().all()
    return success({"items": [_serialize(item) for item in items], "total": len(items)}, request=request)


@router.post("/allowlist")
async def create_allowed(
    payload: dict,
    request: Request,
    _: object = Depends(current_admin),
    session: AsyncSession = Depends(get_session),
):
    domain_pattern = (payload.get("domain_pattern") or "").strip()
    match_mode = payload.get("match_mode", "exact")
    remark = payload.get("remark", "")
    enabled = payload.get("enabled", True)

    if not domain_pattern:
        return error(1001, "domain_pattern 不能为空", http_status=400, request=request)
    if match_mode not in ("exact", "suffix", "regex"):
        return error(1001, "match_mode 必须为 exact / suffix / regex 之一", http_status=400, request=request)

    item = AllowedDomain(
        domain_pattern=domain_pattern,
        match_mode=match_mode,
        enabled=enabled,
        remark=remark,
        source="manual",
        created_by="admin",
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return success(_serialize(item), request=request)


@router.put("/allowlist/{item_id}")
async def update_allowed(
    item_id: str,
    payload: dict,
    request: Request,
    _: object = Depends(current_admin),
    session: AsyncSession = Depends(get_session),
):
    item = await session.get(AllowedDomain, item_id)
    if not item or item.deleted_at is not None:
        return error(1002, "白名单条目不存在", http_status=404, request=request)

    if "match_mode" in payload and payload["match_mode"] in ("exact", "suffix", "regex"):
        item.match_mode = payload["match_mode"]
    if "enabled" in payload:
        item.enabled = bool(payload["enabled"])
    if "remark" in payload:
        item.remark = payload["remark"]
    if "domain_pattern" in payload:
        item.domain_pattern = payload["domain_pattern"]
    item.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(item)
    return success(_serialize(item), request=request)


@router.delete("/allowlist/{item_id}")
async def delete_allowed(
    item_id: str,
    request: Request,
    _: object = Depends(current_admin),
    session: AsyncSession = Depends(get_session),
):
    item = await session.get(AllowedDomain, item_id)
    if not item or item.deleted_at is not None:
        return error(1002, "白名单条目不存在", http_status=404, request=request)

    item.deleted_at = datetime.now(timezone.utc)
    await session.commit()
    return success({"id": item_id}, request=request)
