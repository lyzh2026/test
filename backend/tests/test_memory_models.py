"""记忆层三张表的模型契约测试（不连 DB，只校验 metadata）。"""
import app.models  # noqa: F401  必须显式导入，否则 Base.metadata 里没有这些表
from app.core.database import Base


def test_tables_registered():
    names = set(Base.metadata.tables.keys())
    assert "edit_records" in names
    assert "tweet_drafts" in names
    assert "site_render_stats" in names


def test_edit_records_columns():
    from app.models.memory import EditRecord

    cols = set(EditRecord.__table__.columns.keys())
    assert {"id", "target_type", "target_id", "field", "old_value", "new_value", "editor", "created_at"} == cols


def test_tweet_drafts_unique_version():
    from app.models.memory import TweetDraft

    cols = set(TweetDraft.__table__.columns.keys())
    assert {"id", "article_id", "title", "body", "template", "version", "created_at", "updated_at"} == cols
    uniques = [c.name for c in TweetDraft.__table__.constraints if c.__class__.__name__ == "UniqueConstraint"]
    assert "uq_tweet_drafts_article_version" in uniques


def test_site_render_stats_columns_and_counts_default_zero():
    from app.models.memory import SiteRenderStat

    cols = set(SiteRenderStat.__table__.columns.keys())
    assert cols == {
        "id", "domain", "stat_date",
        "ff_ok", "ff_fail", "pw_ok", "pw_fail", "ab_ok", "ab_fail",
    }
    for name in ("ff_ok", "ff_fail", "pw_ok", "pw_fail", "ab_ok", "ab_fail"):
        col = SiteRenderStat.__table__.columns[name]
        assert col.default.arg == 0
        assert col.nullable is False
