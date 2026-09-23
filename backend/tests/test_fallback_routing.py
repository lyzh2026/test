"""_crawl_one 的直连短路与重试耗尽后兜底标记。不连 DB。"""
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from app.modules.crawler import service


@pytest.mark.asyncio
async def test_whitelist_direct_connect_skips_retries():
    """白名单域名：即使错误码可重试，也第一次尝试即返回，不重试。"""
    attempts = AsyncMock(return_value={
        "ok": False, "code": 2001, "direct_fallback": True,
        "reason": "whitelist", "stage": "render",
    })
    # code=2001 可重试且 MAX_RETRIES=2：没有 direct_fallback 短路时循环会走满 2 次。
    with patch.object(service.settings, "CRAWLER_MAX_RETRIES", 2), \
            patch.object(service, "_crawl_one_attempt", attempts):
        res = await service._crawl_one(
            "t1", "https://wl.com/a", target_date=date(2026, 9, 23),
            aibrowser_enabled=True, route_policy={"wl.com": "always_aibrowser"},
        )
    assert res["direct_fallback"] is True
    assert attempts.await_count == 1


@pytest.mark.asyncio
async def test_render_failure_marked_fallback_after_retries():
    """三层全失败：返回带 fallback 标记的结果。"""
    attempts = AsyncMock(return_value={
        "ok": False, "fallback": True, "code": 2001, "reason": "RENDER_FAILED", "stage": "render",
    })
    with patch.object(service.settings, "CRAWLER_MAX_RETRIES", 1), \
            patch.object(service, "_crawl_one_attempt", attempts):
        res = await service._crawl_one(
            "t1", "https://slow.com/a", target_date=date(2026, 9, 23),
            aibrowser_enabled=True,
        )
    assert res.get("fallback") is True
    assert attempts.await_count == 1


@pytest.mark.asyncio
async def test_switch_off_returns_plain_failure_without_retrying_forever():
    """开关关闭：没有任何 fallback 标记，走既有重试路径直到耗尽。"""
    attempts = AsyncMock(return_value={
        "ok": False, "code": 2001, "reason": "RENDER_FAILED", "stage": "render",
    })
    # MAX_RETRIES=2：只有真的把既有重试循环跑满 2 次（含第一次退避），这个断言才有牙。
    # 若写成 1，循环体在**任何**代码路径上都只跑一次，断言恒真。
    with patch.object(service.settings, "CRAWLER_MAX_RETRIES", 2), \
            patch.object(service, "_crawl_one_attempt", attempts):
        res = await service._crawl_one(
            "t1", "https://slow.com/a", target_date=date(2026, 9, 23),
        )
    assert "fallback" not in res
    assert "direct_fallback" not in res
    assert res["ok"] is False
    assert attempts.await_count == 2


def test_render_failure_marks_fallback_only_when_enabled():
    """纯 helper：开关开启打 fallback 标记；关闭时不打，且返回体与改动前逐键相同。"""
    off = service._render_failure("RENDER_FAILED", False, code=2001)
    assert off == {"ok": False, "code": 2001, "reason": "RENDER_FAILED", "stage": "render"}
    assert "fallback" not in off

    on = service._render_failure("RENDER_FAILED", True, code=2001)
    assert on == {
        "ok": False, "code": 2001, "reason": "RENDER_FAILED", "stage": "render", "fallback": True,
    }
