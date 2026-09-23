"""兜底路由两张表的模型契约测试（不连 DB，只校验 metadata）。"""
import app.models  # noqa: F401  必须显式导入，否则 Base.metadata 里没有这些表
from app.core.database import Base


def test_tables_registered():
    names = set(Base.metadata.tables.keys())
    assert "render_route_policy" in names
    assert "fallback_queue" in names


def test_render_route_policy_columns():
    from app.models.routing import RenderRoutePolicy

    cols = set(RenderRoutePolicy.__table__.columns.keys())
    assert cols == {
        "id", "domain", "mode", "source", "reason",
        "promoted_at", "enabled", "created_at", "updated_at",
    }
    uniques = [c.name for c in RenderRoutePolicy.__table__.constraints if c.__class__.__name__ == "UniqueConstraint"]
    assert "uq_render_route_policy_domain" in uniques


def test_fallback_queue_columns():
    from app.models.routing import FallbackQueue

    cols = set(FallbackQueue.__table__.columns.keys())
    assert cols == {"id", "task_id", "url", "fail_reason", "state", "created_at", "updated_at"}


def test_crawler_task_has_fallback_counters():
    from app.models.crawler_task import CrawlerTask

    cols = set(CrawlerTask.__table__.columns.keys())
    assert "fallback_total" in cols
    assert "fallback_done" in cols
    assert CrawlerTask.__table__.columns["fallback_total"].default.arg == 0
    assert CrawlerTask.__table__.columns["fallback_done"].default.arg == 0
