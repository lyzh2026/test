"""统计驱动的白名单自动晋升：AI Browser 成功率够高的域名晋升为直连（spec §9）。

只增不减——已存在的条目（含 manual）一律跳过，不做自动降级。
"""
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.modules.crawler.ai_browser import MODE_ALWAYS_AIBROWSER
from app.modules.memory.service import list_site_stats

logger = logging.getLogger(__name__)

WINDOW_DAYS = 7
MIN_ATTEMPTS = 5
MIN_RATE = 0.6


def select_promotions(
    rows, *, min_attempts: int = MIN_ATTEMPTS, min_rate: float = MIN_RATE
) -> list[dict]:
    """从站点统计里挑出应晋升的域名。row 只需有 domain / ab_ok / ab_fail 三个属性。"""
    out: list[dict] = []
    for r in rows:
        ab_ok = r.ab_ok or 0
        ab_fail = r.ab_fail or 0
        attempts = ab_ok + ab_fail
        if attempts < min_attempts:
            continue
        rate = ab_ok / attempts
        if rate < min_rate:
            continue
        out.append({
            "domain": r.domain,
            "ab_ok": ab_ok,
            "ab_fail": ab_fail,
            "rate": round(rate, 4),
            "reason": f"近 {WINDOW_DAYS} 天 AI Browser 成功率 {rate:.0%}（{ab_ok}/{attempts}）",
        })
    out.sort(key=lambda d: d["rate"], reverse=True)
    return out


async def promote_render_policies() -> int:
    """扫描 site_render_stats 自动晋升。返回新增条数。"""
    from app.models.routing import RenderRoutePolicy

    today = date.today()
    try:
        async with AsyncSessionLocal() as session:
            rows = await list_site_stats(
                session, date_from=today - timedelta(days=WINDOW_DAYS - 1), date_to=today
            )
            candidates = select_promotions(rows)
            if not candidates:
                return 0

            res = await session.execute(select(RenderRoutePolicy.domain))
            existing = {d.lower() for d in res.scalars().all()}

            added = 0
            now = datetime.now(timezone.utc)
            for c in candidates:
                if c["domain"].lower() in existing:
                    continue
                session.add(RenderRoutePolicy(
                    domain=c["domain"],
                    mode=MODE_ALWAYS_AIBROWSER,
                    source="auto",
                    reason=c["reason"],
                    promoted_at=now,
                    enabled=True,
                ))
                added += 1
            if added:
                await session.commit()
                logger.info("auto-promoted %d domains to always_aibrowser", added)
            return added
    except Exception:
        logger.warning("promote_render_policies failed", exc_info=True)
        return 0
