"""推文草稿版本策略单测。不连 DB。"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.memory import TweetDraft
from app.modules.wechat_format.service import draft_to_data, next_version, save_draft


def _draft(version, title, body, template="green-simple"):
    d = TweetDraft()
    d.version = version
    d.title = title
    d.body = body
    d.template = template
    return d


def test_next_version_from_empty():
    assert next_version([]) == 1


def test_next_version_increments_latest():
    assert next_version([_draft(1, "a", "b"), _draft(3, "c", "d")]) == 4


def test_draft_to_data_overrides_title_and_paragraphs():
    base = {"id": "x", "title": "AI 标题", "paragraphs": ["AI 段1"], "summary": "s"}
    data = draft_to_data(base, _draft(2, "手改标题", "第一段\n\n第二段"))
    assert data["title"] == "手改标题"
    assert data["paragraphs"] == ["第一段", "第二段"]
    assert data["summary"] == "s"  # 其余字段保留
    assert data["id"] == "x"


@pytest.mark.asyncio
async def test_save_draft_version_conflict_raises_value_error():
    """并发保存撞 (article_id, version) 唯一约束 → ValueError，而不是 500。"""
    session = MagicMock()
    session.commit = AsyncMock(side_effect=IntegrityError("stmt", {}, Exception("dup")))
    session.rollback = AsyncMock()

    with pytest.raises(ValueError):
        await save_draft(
            session,
            article_id="11111111-1111-1111-1111-111111111111",
            title="t",
            body="b",
            template="green-simple",
            editor="admin",
            old_title="t",
            old_body="b",
            old_version=1,
        )
    session.rollback.assert_awaited_once()
