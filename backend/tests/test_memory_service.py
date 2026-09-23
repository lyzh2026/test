"""记忆层纯函数单测。不连 DB。"""
from datetime import date
import uuid

from app.models.memory import EditRecord, SiteRenderStat
from app.modules.memory.service import (
    build_edit_record,
    build_health_stats,
    summarize_site_stats,
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
