"""白名单 CRUD + 系统设置 API。"""
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, UploadFile, File
from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.dependencies.auth import current_admin
from app.models.allowed_domain import AllowedDomain
from app.models.system_config import SystemConfig
from app.utils.response import error, success

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "static", "templates")
TEMPLATE_PATH = os.path.join(TEMPLATE_DIR, "export_template.docx")

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


# ── AI 模型设置 ──────────────────────────────────────────────


def _mask_key(key: str) -> str:
    if not key or len(key) <= 8:
        return "***"
    return key[:8] + "***"


@router.get("/settings/ai")
async def get_ai_settings(
    request: Request,
    _: object = Depends(current_admin),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(SystemConfig).where(SystemConfig.key == "ai_provider")
    )
    cfg = result.scalar_one_or_none()
    if cfg and cfg.value:
        val = dict(cfg.value)
        val["api_key"] = _mask_key(val.get("api_key", ""))
        return success(val, request=request)
    return success({"provider": "kimi", "api_key": "", "base_url": "", "model": ""}, request=request)


@router.put("/settings/ai")
async def update_ai_settings(
    payload: dict,
    request: Request,
    _: object = Depends(current_admin),
    session: AsyncSession = Depends(get_session),
):
    api_key = (payload.get("api_key") or "").strip()
    base_url = (payload.get("base_url") or "").strip()
    model = (payload.get("model") or "").strip()
    provider = (payload.get("provider") or "custom").strip()

    if not api_key:
        return error(1001, "API Key 不能为空", http_status=400, request=request)
    if not base_url:
        return error(1001, "Base URL 不能为空", http_status=400, request=request)
    if not model:
        return error(1001, "Model 不能为空", http_status=400, request=request)

    result = await session.execute(
        select(SystemConfig).where(SystemConfig.key == "ai_provider")
    )
    cfg = result.scalar_one_or_none()
    if cfg:
        cfg.value = {"provider": provider, "api_key": api_key, "base_url": base_url, "model": model}
    else:
        cfg = SystemConfig(
            key="ai_provider",
            value={"provider": provider, "api_key": api_key, "base_url": base_url, "model": model},
        )
        session.add(cfg)
    await session.commit()

    # 清除客户端缓存
    from app.modules.ai.kimi_client import clear_llm_cache
    clear_llm_cache()

    return success({"provider": provider, "base_url": base_url, "model": model}, request=request)


@router.post("/settings/ai/test")
async def test_ai_connection(
    request: Request,
    _: object = Depends(current_admin),
    session: AsyncSession = Depends(get_session),
):
    from app.modules.ai.kimi_client import get_llm_client
    client, model = await get_llm_client()
    if not client:
        return error(2001, "AI API Key 未配置", http_status=400, request=request)

    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "请回复 ok"}],
            max_tokens=10,
        )
        reply = (resp.choices[0].message.content or "").strip()
        return success({"ok": True, "model": model, "reply": reply}, request=request)
    except Exception as e:
        return error(2002, f"连接测试失败：{e!r}", http_status=502, request=request)


# ── 导出模板管理 ──────────────────────────────────────────────


@router.get("/settings/export-template")
async def get_export_template_status(
    request: Request,
    _: object = Depends(current_admin),
):
    """查询当前是否已上传 Word 导出模板。"""
    exists = os.path.isfile(TEMPLATE_PATH)
    stat = os.stat(TEMPLATE_PATH) if exists else None
    return success({
        "exists": exists,
        "filename": "export_template.docx" if exists else None,
        "uploaded_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat() if stat else None,
    }, request=request)


@router.put("/settings/export-template")
async def upload_export_template(
    request: Request,
    _: object = Depends(current_admin),
    file: UploadFile = File(...),
):
    """上传 .docx 模板用于合并导出。"""
    if not file.filename or not file.filename.lower().endswith(".docx"):
        return error(1001, "仅支持 .docx 文件", http_status=400, request=request)

    os.makedirs(TEMPLATE_DIR, exist_ok=True)
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        return error(1001, "模板文件不能超过 10MB", http_status=400, request=request)

    with open(TEMPLATE_PATH, "wb") as f:
        f.write(content)

    return success({"ok": True, "filename": file.filename}, request=request)


@router.delete("/settings/export-template")
async def delete_export_template(
    request: Request,
    _: object = Depends(current_admin),
):
    """删除已上传的导出模板。"""
    if os.path.isfile(TEMPLATE_PATH):
        os.remove(TEMPLATE_PATH)
    return success({"ok": True}, request=request)


# ── 分类标签配置 ──────────────────────────────────────────────

DEFAULT_CATEGORY_LABELS = [
    "最新政策",
    "数字经济",
    "人工智能",
    "数据要素",
    "通信",
    "申报",
    "潜在商机",
    "具身智能",
    "车路云协同",
    "新型工业化",
    "算力",
]


@router.get("/settings/category-labels")
async def get_category_labels(
    request: Request,
    _: object = Depends(current_admin),
    session: AsyncSession = Depends(get_session),
):
    """获取当前分类标签配置。"""
    result = await session.execute(
        select(SystemConfig).where(SystemConfig.key == "category_labels")
    )
    cfg = result.scalar_one_or_none()
    if cfg and cfg.value and isinstance(cfg.value, list):
        return success({"labels": cfg.value}, request=request)
    return success({"labels": DEFAULT_CATEGORY_LABELS}, request=request)


@router.put("/settings/category-labels")
async def update_category_labels(
    request: Request,
    _: object = Depends(current_admin),
    session: AsyncSession = Depends(get_session),
):
    """更新分类标签配置（至少保留 1 个，最多 20 个）。"""
    try:
        payload = await request.json()
    except Exception:
        return error(1001, "请求体必须是 JSON", http_status=400, request=request)
    labels = payload.get("labels", [])
    if not isinstance(labels, list):
        return error(1001, "labels 必须为数组", http_status=400, request=request)
    if len(labels) < 1:
        return error(1001, "至少需要 1 个分类标签", http_status=400, request=request)
    if len(labels) > 20:
        return error(1001, "分类标签最多 20 个", http_status=400, request=request)
    for lbl in labels:
        if not isinstance(lbl, str) or not lbl.strip():
            return error(1001, "分类标签不能为空字符串", http_status=400, request=request)

    # 去重并清理
    cleaned = []
    seen = set()
    for lbl in labels:
        s = lbl.strip()
        if s and s not in seen:
            seen.add(s)
            cleaned.append(s)

    result = await session.execute(
        select(SystemConfig).where(SystemConfig.key == "category_labels")
    )
    cfg = result.scalar_one_or_none()
    if cfg:
        cfg.value = cleaned
    else:
        cfg = SystemConfig(key="category_labels", value=cleaned)
        session.add(cfg)
    await session.commit()

    return success({"labels": cleaned}, request=request)
