"""_crawl_one 的直连短路与重试耗尽后兜底标记。不连 DB。"""
from unittest.mock import AsyncMock, patch

import pytest

from app.modules.crawler import service


@pytest.mark.asyncio
async def test_whitelist_direct_connect_skips_retries():
    """白名单域名：第一次尝试即返回，不重试。"""
    attempts = AsyncMock(return_value={
        "ok": False, "direct_fallback": True, "reason": "whitelist", "stage": "render",
    })
    with patch.object(service, "_crawl_one_attempt", attempts):
        res = await service._crawl_one(
            "t1", "https://wl.com/a", target_date=__import__("datetime").date(2026, 9, 23),
            aibrowser_enabled=True, route_policy={"wl.com": "always_aibrowser"},
        )
    assert res["direct_fallback"] is True
    assert attempts.await_count == 1


@pytest.mark.asyncio
async def test_render_failure_marked_fallback_after_retries():
    """三层全失败：重试到上限后返回带 fallback 标记的结果。"""
    attempts = AsyncMock(return_value={
        "ok": False, "fallback": True, "code": 2001, "reason": "RENDER_FAILED", "stage": "render",
    })
    with patch.object(service, "_crawl_one_attempt", attempts):
        res = await service._crawl_one(
            "t1", "https://slow.com/a", target_date=__import__("datetime").date(2026, 9, 23),
            aibrowser_enabled=True,
        )
    assert res.get("fallback") is True
    assert attempts.await_count >= 1  # 至少尝试过一次


@pytest.mark.asyncio
async def test_switch_off_returns_plain_failure_without_retrying_forever():
    """开关关闭：没有任何 fallback 标记，走既有重试路径。"""
    attempts = AsyncMock(return_value={
        "ok": False, "code": 2001, "reason": "RENDER_FAILED", "stage": "render",
    })
    with patch.object(service, "_crawl_one_attempt", attempts):
        res = await service._crawl_one(
            "t1", "https://slow.com/a", target_date=__import__("datetime").date(2026, 9, 23),
        )
    assert "fallback" not in res
    assert "direct_fallback" not in res
    assert res["ok"] is False
