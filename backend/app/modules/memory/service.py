"""记忆层服务：修改记录与站点渲染统计。

可测逻辑全部抽成纯函数，DB 存取只做最薄的包装。
"""
import uuid
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import EditRecord, SiteRenderStat

_COUNTERS = ("ff_ok", "ff_fail", "pw_ok", "pw_fail", "ab_ok", "ab_fail")


# ---------- 纯函数 ----------

def build_edit_record(
    *,
    target_type: str,
    target_id: uuid.UUID,
    field: str,
    old_value: Any,
    new_value: Any,
    editor: str | None,
) -> EditRecord:
    return EditRecord(
        target_type=target_type,
        target_id=target_id,
        field=field,
        old_value=old_value,
        new_value=new_value,
        editor=editor,
    )


def summarize_site_stats(rows: list[SiteRenderStat]) -> list[dict]:
    """降级站点排行，按 fail_count 降序，同分按域名升序（保证排序可复现）。"""
    out: list[dict] = []
    for r in rows:
        ok = (r.ff_ok or 0) + (r.pw_ok or 0) + (r.ab_ok or 0)
        fail = (r.ff_fail or 0) + (r.pw_fail or 0) + (r.ab_fail or 0)
        attempts = ok + fail
        out.append({
            "domain": r.domain,
            "attempts": attempts,
            "fail_count": fail,
            "fail_rate": round(fail / attempts, 4) if attempts else 0.0,
        })
    out.sort(key=lambda d: (-d["fail_count"], d["domain"]))
    return out


def build_health_stats(rows: list[SiteRenderStat]) -> dict | None:
    """周报「系统健康度」。无数据返回 None，不造假数据。"""
    if not rows:
        return None
    sites = summarize_site_stats(rows)
    attempts = sum(s["attempts"] for s in sites)
    fails = sum(s["fail_count"] for s in sites)
    return {
        "total_attempts": attempts,
        "fail_count": fails,
        "fail_rate": round(fails / attempts, 4) if attempts else 0.0,
        "degraded_sites": [s for s in sites if s["attempts"] > 0][:10],
    }


# ---------- DB 存取 ----------

async def upsert_stat_deltas(session: AsyncSession, deltas: dict[tuple[str, date], dict[str, int]]) -> None:
    """按 (domain, stat_date) 累加写入。调用方负责吞异常。"""
    for (domain, stat_date), counters in deltas.items():
        values = {"domain": domain, "stat_date": stat_date, **{c: counters.get(c, 0) for c in _COUNTERS}}
        stmt = pg_insert(SiteRenderStat).values(**values)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_site_render_stats_domain_date",
            set_={c: getattr(SiteRenderStat, c) + stmt.excluded[c] for c in _COUNTERS},
        )
        await session.execute(stmt)
    await session.commit()


async def list_edit_records(
    session: AsyncSession,
    *,
    target_type: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[EditRecord], int]:
    conds = []
    if target_type:
        conds.append(EditRecord.target_type == target_type)
    if date_from:
        conds.append(func.date(EditRecord.created_at) >= date_from)
    if date_to:
        conds.append(func.date(EditRecord.created_at) <= date_to)

    stmt = select(EditRecord)
    count_stmt = select(func.count(EditRecord.id))
    if conds:
        stmt = stmt.where(*conds)
        count_stmt = count_stmt.where(*conds)
    stmt = stmt.order_by(EditRecord.created_at.desc()).limit(limit).offset(offset)

    rows = (await session.execute(stmt)).scalars().all()
    total = (await session.execute(count_stmt)).scalar_one()
    return list(rows), total


async def list_site_stats(
    session: AsyncSession, *, date_from: date | None = None, date_to: date | None = None
) -> list[SiteRenderStat]:
    """取 `stat_date` 落在 [date_from, date_to] 内的按域名聚合结果。"""
    stmt = (
        select(
            SiteRenderStat.domain.label("domain"),
            func.max(SiteRenderStat.stat_date).label("stat_date"),
            func.sum(SiteRenderStat.ff_ok).label("ff_ok"),
            func.sum(SiteRenderStat.ff_fail).label("ff_fail"),
            func.sum(SiteRenderStat.pw_ok).label("pw_ok"),
            func.sum(SiteRenderStat.pw_fail).label("pw_fail"),
            func.sum(SiteRenderStat.ab_ok).label("ab_ok"),
            func.sum(SiteRenderStat.ab_fail).label("ab_fail"),
        )
        .group_by(SiteRenderStat.domain)
    )
    if date_from is not None:
        stmt = stmt.where(SiteRenderStat.stat_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(SiteRenderStat.stat_date <= date_to)

    rows = (await session.execute(stmt)).all()
    out = []
    for r in rows:
        s = SiteRenderStat()
        s.domain = r.domain
        s.stat_date = r.stat_date
        for c in _COUNTERS:
            setattr(s, c, int(getattr(r, c) or 0))
        out.append(s)
    return out
