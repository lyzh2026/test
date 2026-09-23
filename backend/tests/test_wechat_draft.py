"""推文草稿版本策略单测。不连 DB。"""
from app.models.memory import TweetDraft
from app.modules.wechat_format.service import draft_to_data, next_version


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
