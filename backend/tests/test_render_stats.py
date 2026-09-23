"""渲染统计缓冲单测。不连 DB。"""
from datetime import date

import pytest

from app.modules.crawler.renderer import DynamicRenderer


@pytest.mark.asyncio
async def test_ff_success_and_failure_accumulate():
    r = DynamicRenderer()
    r.record_ff_success("https://a.com/1")
    r.record_ff_success("https://a.com/2")
    await r.record_ff_failure("https://a.com/3")
    deltas = r.take_stat_deltas()
    counters = deltas[("a.com", date.today())]
    assert counters["ff_ok"] == 2
    assert counters["ff_fail"] == 1


def test_pw_result_recorded():
    r = DynamicRenderer()
    r.record_pw_result("https://b.com/x", True)
    r.record_pw_result("https://b.com/y", False)
    counters = r.take_stat_deltas()[("b.com", date.today())]
    assert counters["pw_ok"] == 1
    assert counters["pw_fail"] == 1


def test_ab_result_recorded():
    r = DynamicRenderer()
    r.record_ab_result("https://c.com/x", True)
    counters = r.take_stat_deltas()[("c.com", date.today())]
    assert counters["ab_ok"] == 1


def test_take_deltas_clears_buffer():
    r = DynamicRenderer()
    r.record_ff_success("https://a.com/1")
    r.take_stat_deltas()
    assert r.take_stat_deltas() == {}


@pytest.mark.asyncio
async def test_domain_fingerprint_still_works():
    """既有域名指纹行为不能被破坏：连续 3 次失败即单向闩锁 DYNAMIC，成功不清闩。"""
    r = DynamicRenderer()
    for _ in range(3):
        await r.record_ff_failure("https://slow.com/1")
    assert r.needs_playwright("https://slow.com/2") is True
    r.record_ff_success("https://slow.com/3")
    # DYNAMIC 是单向闩锁：成功只重置失败计数，不清除标记；命中后不再走 fast_fetch，
    # 故生产中不会再调到这里。断言 True 即为守护这一既有语义。
    assert r.needs_playwright("https://slow.com/4") is True
