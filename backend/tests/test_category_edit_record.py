"""分类修改记录：断言 handler 在事务内追加了 edit_records。"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.article import Article
from app.models.memory import EditRecord


class _FakeSession:
    """最薄 session 替身：只记录 add 调用。"""

    def __init__(self, article, analysis):
        self._article = article
        self._analysis = analysis
        self.added: list[object] = []
        self.committed = False

    async def get(self, model, pk):
        return self._article

    async def execute(self, stmt):
        result = MagicMock()
        result.scalar_one_or_none.return_value = self._analysis
        result.scalars.return_value.all.return_value = []
        return result

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True


@pytest.mark.asyncio
async def test_category_edit_appends_record():
    from app.modules.articles.routes import update_article_categories

    article = MagicMock(spec=Article)
    article.id = "11111111-1111-1111-1111-111111111111"
    article.status = "processed"

    analysis = MagicMock()
    analysis.categories = [{"label": "人工智能"}]

    session = _FakeSession(article, analysis)
    request = MagicMock()
    # success() 会把 request.state.request_id 塞进 JSONResponse；MagicMock 的自动属性
    # 不是 None 而是子 mock，直接传会让 json.dumps 抛 TypeError。必须显式置 None。
    request.state.request_id = None

    with patch("app.modules.articles.routes._get_category_labels", new=AsyncMock(return_value=["人工智能", "数据要素"])):
        await update_article_categories(
            article_id=str(article.id),
            payload={"categories": [{"label": "数据要素"}]},
            request=request,
            user=MagicMock(username="admin"),
            session=session,
        )

    records = [o for o in session.added if isinstance(o, EditRecord)]
    assert len(records) == 1
    rec = records[0]
    assert rec.target_type == "category"
    assert rec.field == "categories"
    assert rec.old_value == [{"label": "人工智能"}]
    assert rec.new_value == [{"label": "数据要素"}]
    assert rec.editor == "admin"


@pytest.mark.asyncio
async def test_category_noop_does_not_append_record():
    """标签未变化时不写记录。"""
    from app.modules.articles.routes import update_article_categories

    article = MagicMock(spec=Article)
    article.id = "11111111-1111-1111-1111-111111111111"
    article.status = "processed"

    analysis = MagicMock()
    analysis.categories = [{"label": "人工智能"}]

    session = _FakeSession(article, analysis)
    request = MagicMock()
    request.state.request_id = None  # 不显式置 None 会让 json.dumps 抛 TypeError

    with patch("app.modules.articles.routes._get_category_labels", new=AsyncMock(return_value=["人工智能"])):
        await update_article_categories(
            article_id=str(article.id),
            payload={"categories": [{"label": "人工智能"}]},
            request=request,
            user=MagicMock(username="admin"),
            session=session,
        )

    assert [o for o in session.added if isinstance(o, EditRecord)] == []
