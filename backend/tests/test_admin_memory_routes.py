"""后台记忆接口的序列化契约。"""
from unittest.mock import MagicMock
from datetime import datetime, timezone
import uuid

from app.modules.admin.routes import _serialize_edit_record


def test_serialize_edit_record():
    rec = MagicMock()
    rec.id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    rec.target_type = "category"
    rec.target_id = uuid.UUID("22222222-2222-2222-2222-222222222222")
    rec.field = "categories"
    rec.old_value = [{"label": "人工智能"}]
    rec.new_value = [{"label": "数据要素"}]
    rec.editor = "admin"
    rec.created_at = datetime(2026, 9, 23, 10, 0, tzinfo=timezone.utc)

    out = _serialize_edit_record(rec)
    assert out["id"] == "11111111-1111-1111-1111-111111111111"
    assert out["target_type"] == "category"
    assert out["target_id"] == "22222222-2222-2222-2222-222222222222"
    assert out["field"] == "categories"
    assert out["old_value"] == [{"label": "人工智能"}]
    assert out["new_value"] == [{"label": "数据要素"}]
    assert out["editor"] == "admin"
    assert out["created_at"] == "2026-09-23T10:00:00+00:00"
