"""白名单自动晋升条件。纯函数，不连 DB。"""
from app.modules.crawler.promotion import select_promotions


class _Stat:
    def __init__(self, domain, ab_ok, ab_fail):
        self.domain = domain
        self.ab_ok = ab_ok
        self.ab_fail = ab_fail


def test_promotes_when_rate_and_volume_sufficient():
    rows = [_Stat("good.com", ab_ok=4, ab_fail=1)]  # 80%, 5 次
    out = select_promotions(rows)
    assert [c["domain"] for c in out] == ["good.com"]
    assert out[0]["rate"] == 0.8
    assert "80%" in out[0]["reason"]


def test_skips_below_min_attempts():
    rows = [_Stat("few.com", ab_ok=4, ab_fail=0)]  # 100% 但只有 4 次
    assert select_promotions(rows) == []


def test_skips_below_min_rate():
    rows = [_Stat("bad.com", ab_ok=2, ab_fail=3)]  # 40%
    assert select_promotions(rows) == []


def test_zero_attempts_skipped():
    rows = [_Stat("none.com", ab_ok=0, ab_fail=0)]
    assert select_promotions(rows) == []


def test_rate_exactly_at_threshold_promotes():
    rows = [_Stat("edge.com", ab_ok=3, ab_fail=2)]  # 60%, 5 次
    assert [c["domain"] for c in select_promotions(rows)] == ["edge.com"]


def test_none_counters_treated_as_zero():
    rows = [_Stat("none2.com", ab_ok=None, ab_fail=None)]
    assert select_promotions(rows) == []


def test_thresholds_overridable():
    rows = [_Stat("x.com", ab_ok=1, ab_fail=1)]
    out = select_promotions(rows, min_attempts=2, min_rate=0.5)
    assert [c["domain"] for c in out] == ["x.com"]
