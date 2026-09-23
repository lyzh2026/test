"""记忆层纯函数单测。不连 DB。"""
from datetime import date
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from app.models.memory import EditRecord, SiteRenderStat
from app.modules.memory.service import (
    build_edit_record,
    build_health_stats,
    list_site_stats,
    summarize_site_stats,
    upsert_stat_deltas,
)


def _stat(domain: str, ff_ok=0, ff_fail=0, pw_ok=0, pw_fail=0):
    s = SiteRenderStat()
    s.domain = domain
    s.stat_date = date(2026, 9, 23)
    s.ff_ok = ff_ok
    s.ff_fail = ff_fail
    s.pw_ok = pw_ok
    s.pw_fail = pw_fail
    return s


def test_build_edit_record_maps_fields():
    aid = uuid.uuid4()
    rec = build_edit_record(
        target_type="category",
        target_id=aid,
        field="categories",
        old_value=[{"label": "人工智能"}],
        new_value=[{"label": "数据要素"}],
        editor="admin",
    )
    assert isinstance(rec, EditRecord)
    assert rec.target_type == "category"
    assert rec.target_id == aid
    assert rec.field == "categories"
    assert rec.old_value == [{"label": "人工智能"}]
    assert rec.new_value == [{"label": "数据要素"}]
    assert rec.editor == "admin"


def test_summarize_counts_attempts_and_rate():
    rows = [
        _stat("a.com", ff_ok=8, ff_fail=2, pw_ok=1, pw_fail=1),
        _stat("b.com", ff_ok=0, ff_fail=5, pw_ok=0, pw_fail=0),
    ]
    out = summarize_site_stats(rows)
    assert [r["domain"] for r in out] == ["b.com", "a.com"]  # 按 fail_count 降序
    a = next(r for r in out if r["domain"] == "a.com")
    assert a["attempts"] == 12
    assert a["fail_count"] == 3
    assert a["fail_rate"] == 0.25


def test_summarize_zero_attempts_is_safe():
    out = summarize_site_stats([_stat("c.com")])
    assert out[0]["attempts"] == 0
    assert out[0]["fail_rate"] == 0.0


def test_health_stats_none_when_no_rows():
    assert build_health_stats([]) is None


def test_health_stats_totals_and_top10():
    rows = [_stat(f"d{i}.com", ff_fail=i + 1) for i in range(12)]
    health = build_health_stats(rows)
    assert health is not None
    assert health["fail_count"] == sum(range(1, 13))
    assert health["total_attempts"] == sum(range(1, 13))
    assert len(health["degraded_sites"]) == 10
    assert health["degraded_sites"][0]["domain"] == "d11.com"


def test_health_stats_empty_domain_rows_excluded():
    """全零统计（无失败也无成功）不应产生降级站点条目。"""
    health = build_health_stats([_stat("e.com")])
    assert health == {
        "total_attempts": 0,
        "fail_count": 0,
        "fail_rate": 0.0,
        "degraded_sites": [],
    }


def test_summarize_ties_broken_by_domain():
    """fail_count 相同时按域名升序，保证周报 Top10 与后续路由决策可复现。"""
    rows = [_stat("z.com", ff_fail=3), _stat("a.com", ff_fail=3)]
    assert [r["domain"] for r in summarize_site_stats(rows)] == ["a.com", "z.com"]


_AGG_COUNTERS = ("ff_ok", "ff_fail", "pw_ok", "pw_fail", "ab_ok", "ab_fail")


def _agg_row(domain, stat_date, **counters):
    row = MagicMock()
    row.domain = domain
    row.stat_date = stat_date
    for c in _AGG_COUNTERS:
        setattr(row, c, counters.get(c, 0))
    return row


@pytest.mark.asyncio
async def test_list_site_stats_carries_real_max_stat_date():
    """聚合后 stat_date 必须是区间内真实最大值，不能伪造为今天。"""
    result = MagicMock()
    result.all.return_value = [_agg_row("slow.com", date(2026, 9, 1), ff_ok=2, ff_fail=4)]
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)

    out = await list_site_stats(session, date_from=date(2026, 8, 25), date_to=date(2026, 9, 1))
    assert out[0].domain == "slow.com"
    assert out[0].stat_date == date(2026, 9, 1)
    assert out[0].ff_fail == 4


@pytest.mark.asyncio
async def test_list_site_stats_sql_aggregates_max_stat_date():
    """mock 能骗过映射断言，故直接查编译后的 SQL，确认真取了 max(stat_date)。"""
    captured = {}
    result = MagicMock()
    result.all.return_value = []

    async def _fake_execute(stmt):
        captured["sql"] = str(stmt.compile(dialect=postgresql.dialect()))
        return result

    session = MagicMock()
    session.execute = _fake_execute
    await list_site_stats(session, date_from=date(2026, 8, 25), date_to=date(2026, 9, 1))

    sql = captured["sql"].lower()
    assert "max(" in sql
    assert "group by" in sql


@pytest.mark.asyncio
async def test_upsert_stat_deltas_uses_on_conflict_accumulation():
    """累加语义必须落在 SQL 上（后续计划依赖它），mock 骗不过，故查编译后的 SQL。"""
    captured = []

    async def _fake_execute(stmt):
        captured.append(str(stmt.compile(dialect=postgresql.dialect())))

    session = MagicMock()
    session.execute = _fake_execute
    session.commit = AsyncMock()

    await upsert_stat_deltas(session, {("a.com", date(2026, 9, 23)): {"ff_ok": 2, "ff_fail": 1}})

    sql = captured[0].lower()
    assert "on conflict" in sql
    assert "do update" in sql
    assert "ff_ok" in sql
