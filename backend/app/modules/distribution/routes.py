"""分发配置和发送日志 API。"""
import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.dependencies.auth import current_admin
from app.models.distribution import DistributionConfig, DistributionLog
from app.utils.response import error, success

logger = logging.getLogger("shixun.distribution")

router = APIRouter(prefix="/api/v1/distribution", tags=["distribution"])


def _serialize_config(item: DistributionConfig) -> dict:
    return {
        "id": str(item.id),
        "channel_type": item.channel_type,
        "name": item.name,
        "config": item.config,
        "enabled": item.enabled,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def _serialize_log(item: DistributionLog) -> dict:
    return {
        "id": str(item.id),
        "config_name": item.config_name,
        "channel_type": item.channel_type,
        "report_week": item.report_week,
        "status": item.status,
        "article_count": item.article_count,
        "category_count": item.category_count,
        "error_message": item.error_message,
        "sent_at": item.sent_at.isoformat() if item.sent_at else None,
    }


# === 通道配置 CRUD ===

@router.get("/configs")
async def list_configs(
    request: Request,
    _: object = Depends(current_admin),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(DistributionConfig).order_by(DistributionConfig.created_at.desc())
    )
    items = result.scalars().all()
    return success({"items": [_serialize_config(item) for item in items]}, request=request)


@router.post("/configs")
async def create_config(
    payload: dict,
    request: Request,
    _: object = Depends(current_admin),
    session: AsyncSession = Depends(get_session),
):
    channel_type = payload.get("channel_type", "").strip()
    name = payload.get("name", "").strip()
    config = payload.get("config", {})
    enabled = payload.get("enabled", True)

    if not channel_type:
        return error(1001, "channel_type 不能为空", http_status=400, request=request)
    if channel_type not in ("email", "webhook"):
        return error(1001, "channel_type 必须为 email 或 webhook", http_status=400, request=request)
    if not name:
        return error(1001, "name 不能为空", http_status=400, request=request)
    if not config:
        return error(1001, "config 不能为空", http_status=400, request=request)

    item = DistributionConfig(
        channel_type=channel_type,
        name=name,
        config=config,
        enabled=enabled,
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return success(_serialize_config(item), request=request)


@router.put("/configs/{item_id}")
async def update_config(
    item_id: str,
    payload: dict,
    request: Request,
    _: object = Depends(current_admin),
    session: AsyncSession = Depends(get_session),
):
    item = await session.get(DistributionConfig, item_id)
    if not item:
        return error(1002, "配置不存在", http_status=404, request=request)

    if "name" in payload and payload["name"]:
        item.name = payload["name"].strip()
    if "config" in payload and payload["config"]:
        item.config = payload["config"]
    if "enabled" in payload:
        item.enabled = bool(payload["enabled"])
    if "channel_type" in payload:
        item.channel_type = payload["channel_type"]
    item.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(item)
    return success(_serialize_config(item), request=request)


@router.delete("/configs/{item_id}")
async def delete_config(
    item_id: str,
    request: Request,
    _: object = Depends(current_admin),
    session: AsyncSession = Depends(get_session),
):
    item = await session.get(DistributionConfig, item_id)
    if not item:
        return error(1002, "配置不存在", http_status=404, request=request)
    await session.delete(item)
    await session.commit()
    return success({"id": item_id}, request=request)


@router.patch("/configs/{item_id}/toggle")
async def toggle_config(
    item_id: str,
    request: Request,
    _: object = Depends(current_admin),
    session: AsyncSession = Depends(get_session),
):
    item = await session.get(DistributionConfig, item_id)
    if not item:
        return error(1002, "配置不存在", http_status=404, request=request)
    item.enabled = not item.enabled
    item.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(item)
    return success(_serialize_config(item), request=request)


# === 发送日志 ===

@router.get("/logs")
async def list_logs(
    request: Request,
    week: str = "",
    _: object = Depends(current_admin),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(DistributionLog).order_by(DistributionLog.sent_at.desc())
    if week:
        stmt = stmt.where(DistributionLog.report_week == week)
    result = await session.execute(stmt)
    items = result.scalars().all()
    return success({"items": [_serialize_log(item) for item in items]}, request=request)


# === 手动触发 ===

@router.post("/trigger")
async def trigger_dispatch(
    request: Request,
    _: object = Depends(current_admin),
    session: AsyncSession = Depends(get_session),
):
    """手动触发周报分发（调试用）。"""
    from app.modules.distribution.service import dispatch_weekly_report

    try:
        await dispatch_weekly_report()
        return success({"message": "周报分发已触发"}, request=request)
    except Exception as e:
        logger.error("手动触发周报分发失败: %s", e)
        return error(2001, f"触发失败: {str(e)}", http_status=500, request=request)


@router.get("/configs/email-enabled")
async def list_email_configs(
    request: Request,
    _: object = Depends(current_admin),
    session: AsyncSession = Depends(get_session),
):
    """列出已启用的邮件通道（供发送时选择）。"""
    result = await session.execute(
        select(DistributionConfig).where(
            DistributionConfig.enabled == True,
            DistributionConfig.channel_type == "email",
        ).order_by(DistributionConfig.created_at)
    )
    items = result.scalars().all()
    return success({"items": [_serialize_config(item) for item in items]}, request=request)


@router.post("/send-article/{article_id}")
async def send_article(
    article_id: str,
    payload: dict,
    request: Request,
    _: object = Depends(current_admin),
    session: AsyncSession = Depends(get_session),
):
    """通过指定邮件通道发送单篇文章。"""
    from email.mime.text import MIMEText
    import smtplib

    from app.models.article import Article
    from sqlalchemy.orm import joinedload

    config_id = payload.get("config_id", "")
    if not config_id:
        return error(1003, "请指定要使用的邮件通道", http_status=400, request=request)

    article = await session.get(Article, article_id, options=[joinedload(Article.ai_analysis)])
    if not article:
        return error(1002, "文章不存在", http_status=404, request=request)

    cfg = await session.get(DistributionConfig, config_id)
    if not cfg or not cfg.enabled or cfg.channel_type != "email":
        return error(1003, "邮件通道不存在或未启用", http_status=400, request=request)

    c = cfg.config
    summary = ""
    keywords = ""
    if article.ai_analysis:
        summary = article.ai_analysis.summary or ""
        keywords = ", ".join(article.ai_analysis.keywords or [])

    html = f"""\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,sans-serif;padding:20px;background:#f5f5f5;">
<div style="max-width:640px;margin:0 auto;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.1);">
<div style="background:#1a73e8;padding:20px;color:#fff;">
  <h1 style="margin:0;font-size:18px;">{article.original_title}</h1>
</div>
<div style="padding:20px;">
  <p style="font-size:13px;color:#666;margin:0 0 12px;">
    {article.source_unit or '来源未知'} · {article.publish_date}
  </p>
  {f'<p style="font-size:14px;line-height:1.6;color:#333;margin:0 0 16px;">{summary}</p>' if summary else ''}
  {f'<p style="font-size:12px;color:#999;">关键词：{keywords}</p>' if keywords else ''}
  <p style="margin:20px 0 0;">
    <a href="{article.original_link}" style="display:inline-block;background:#1a73e8;color:#fff;text-decoration:none;padding:10px 24px;border-radius:6px;font-size:14px;">查看原文 →</a>
  </p>
</div>
<div style="padding:12px 20px;font-size:11px;color:#999;border-top:1px solid #eee;text-align:center;">
  本邮件由拾讯系统自动发送
</div>
</div>
</body>
</html>"""

    msg = MIMEText(html, "html", "utf-8")
    msg["Subject"] = f"拾讯 - {article.original_title}"
    msg["From"] = c.get("from_addr", c.get("smtp_user", ""))
    to_addrs = c.get("to_addrs", [])
    msg["To"] = ", ".join(to_addrs)

    loop = asyncio.get_running_loop()
    use_tls = c.get("use_tls", True)
    smtp_host = c["smtp_host"]
    smtp_port = c["smtp_port"]

    def _send():
        if use_tls:
            with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
                server.login(c["smtp_user"], c["smtp_pass"])
                server.sendmail(c["smtp_user"], to_addrs, msg.as_string())
        else:
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(c["smtp_user"], c["smtp_pass"])
                server.sendmail(c["smtp_user"], to_addrs, msg.as_string())

    try:
        await loop.run_in_executor(None, _send)
        return success({"message": f"文章已发送至 {len(to_addrs)} 个收件人"}, request=request)
    except Exception as e:
        return error(2002, f"发送失败: {str(e)}", http_status=500, request=request)


@router.get("/preview")
async def preview_dispatch(
    request: Request,
    week: str = "",
    channel_type: str = "email",
    _: object = Depends(current_admin),
    session: AsyncSession = Depends(get_session),
):
    """预览指定周报的渲染效果。"""
    from app.modules.distribution.service import preview_report

    try:
        result = await preview_report(session, week or None, channel_type)
        return success(result, request=request)
    except Exception as e:
        logger.error("周报预览失败: %s", e)
        return error(2001, f"预览失败: {str(e)}", http_status=500, request=request)
