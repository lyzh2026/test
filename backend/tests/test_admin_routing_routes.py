"""渲染路由后台接口的序列化契约与路由行为。"""
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.database import get_session
from app.dependencies.auth import current_admin
from app.main import app
from app.models.routing import RenderRoutePolicy
from app.models.system_config import SystemConfig
from app.modules.admin.routes import _serialize_render_policy


def test_serialize_render_policy():
    item = MagicMock()
    item.id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    item.domain = "slow.com"
    item.mode = "always_aibrowser"
    item.source = "auto"
    item.reason = "近 7 天成功率 80%（4/5）"
    item.promoted_at = datetime(2026, 9, 23, 3, 17, tzinfo=timezone.utc)
    item.enabled = True
    item.created_at = datetime(2026, 9, 23, 3, 17, tzinfo=timezone.utc)

    out = _serialize_render_policy(item)
    assert out["id"] == "11111111-1111-1111-1111-111111111111"
    assert out["domain"] == "slow.com"
    assert out["mode"] == "always_aibrowser"
    assert out["source"] == "auto"
    assert out["reason"] == "近 7 天成功率 80%（4/5）"
    assert out["promoted_at"] == "2026-09-23T03:17:00+00:00"
    assert out["enabled"] is True
    assert out["created_at"] == "2026-09-23T03:17:00+00:00"


def test_serialize_render_policy_manual_row_has_null_promoted_at():
    item = MagicMock()
    item.id = uuid.UUID("22222222-2222-2222-2222-222222222222")
    item.domain = "hand.com"
    item.mode = "always_aibrowser"
    item.source = "manual"
    item.reason = None
    item.promoted_at = None
    item.enabled = True
    item.created_at = None

    out = _serialize_render_policy(item)
    assert out["promoted_at"] is None
    assert out["reason"] is None
    assert out["created_at"] is None


# ── 路由行为（替代 brief Step 5 里被延后的 curl 手工验证） ──────

_FIXED_NOW = datetime(2026, 9, 23, 3, 17, tzinfo=timezone.utc)


class _FakeResult:
    def __init__(self, one=None, many=None):
        self._one = one
        self._many = many

    def scalar_one_or_none(self):
        return self._one

    def scalars(self):
        return self

    def all(self):
        if self._many is not None:
            return self._many
        return [] if self._one is None else [self._one]


class _FakeSession:
    """只实现 handler 实际调用的那几个方法，并保证 refresh 后能用真属性序列化。"""

    def __init__(self):
        self.config = None
        self.policies = []

    async def execute(self, stmt):
        entity = stmt.column_descriptions[0]["entity"]
        if entity is SystemConfig:
            return _FakeResult(one=self.config)
        if stmt.whereclause is None:  # 列表查询（只有 order_by）
            return _FakeResult(many=list(self.policies))
        # 局限：忽略 where 条件，任何带条件的查询都返回 policies[0]。
        # 今天够用（重复域名测试在删掉查重后确实会失败），但将来若 POST 另一个域名并再去查重，会误报 409。
        return _FakeResult(one=self.policies[0] if self.policies else None)

    def add(self, obj):
        if isinstance(obj, SystemConfig):
            self.config = obj
            return
        if obj.id is None:
            obj.id = uuid.uuid4()
        if obj.created_at is None:
            obj.created_at = _FIXED_NOW
        self.policies.append(obj)

    async def commit(self):
        pass

    async def refresh(self, obj):
        # 真实 DB 在 flush 时填 default；这里补上，否则 id/created_at 序列化不出来
        if obj.id is None:
            obj.id = uuid.uuid4()
        if obj.created_at is None:
            obj.created_at = _FIXED_NOW

    async def get(self, model, item_id):
        for policy in self.policies:
            if str(policy.id) == str(item_id):
                return policy
        return None

    async def delete(self, obj):
        self.policies.remove(obj)


@pytest.fixture
def client():
    session = _FakeSession()

    async def _override_session():
        yield session

    app.dependency_overrides[current_admin] = lambda: object()
    app.dependency_overrides[get_session] = _override_session
    # 不用 with TestClient(app)：那会跑 lifespan（启调度器、要 Postgres/Redis）
    try:
        yield TestClient(app), session
    finally:
        app.dependency_overrides.clear()


def test_get_ai_browser_settings_defaults_false_when_no_row(client):
    tc, _ = client
    resp = tc.get("/api/v1/admin/settings/ai-browser")

    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["enabled"] is False


def test_put_ai_browser_settings_persists_boolean(client):
    tc, session = client
    resp = tc.put("/api/v1/admin/settings/ai-browser", json={"enabled": True})

    assert resp.status_code == 200
    assert resp.json()["data"]["enabled"] is True
    assert session.config is not None
    assert session.config.value == {"enabled": True}


def test_put_ai_browser_settings_rejects_non_boolean(client):
    tc, session = client
    resp = tc.put("/api/v1/admin/settings/ai-browser", json={"enabled": "yes"})

    assert resp.status_code == 400
    assert resp.json()["code"] == 1001
    assert session.config is None


def test_get_ai_browser_settings_reflects_persisted_true(client):
    tc, _ = client
    put_resp = tc.put("/api/v1/admin/settings/ai-browser", json={"enabled": True})
    assert put_resp.status_code == 200
    assert put_resp.json()["data"]["enabled"] is True

    resp = tc.get("/api/v1/admin/settings/ai-browser")

    assert resp.status_code == 200
    assert resp.json()["data"]["enabled"] is True


def test_create_render_policy_defaults_to_manual_always_aibrowser(client):
    tc, _ = client
    resp = tc.post("/api/v1/admin/render-policy", json={"domain": "slow.com"})

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["domain"] == "slow.com"
    assert data["source"] == "manual"
    assert data["mode"] == "always_aibrowser"
    assert data["enabled"] is True


def test_create_render_policy_duplicate_domain_conflicts(client):
    tc, session = client
    assert tc.post("/api/v1/admin/render-policy", json={"domain": "slow.com"}).status_code == 200

    resp = tc.post("/api/v1/admin/render-policy", json={"domain": "slow.com"})

    assert resp.status_code == 409
    assert resp.json()["code"] == 1002
    assert len(session.policies) == 1


def test_create_render_policy_rejects_invalid_mode(client):
    tc, session = client
    resp = tc.post("/api/v1/admin/render-policy", json={"domain": "slow.com", "mode": "nope"})

    assert resp.status_code == 400
    assert resp.json()["code"] == 1001
    assert session.policies == []


def test_list_render_policies_includes_created_row(client):
    tc, _ = client
    tc.post("/api/v1/admin/render-policy", json={"domain": "slow.com"})

    resp = tc.get("/api/v1/admin/render-policy")

    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert [i["domain"] for i in items] == ["slow.com"]
    assert items[0]["id"]


def test_update_render_policy_toggles_enabled(client):
    tc, _ = client
    created = tc.post("/api/v1/admin/render-policy", json={"domain": "slow.com"}).json()["data"]

    resp = tc.put(f"/api/v1/admin/render-policy/{created['id']}", json={"enabled": False})

    assert resp.status_code == 200
    assert resp.json()["data"]["enabled"] is False


def test_update_render_policy_rejects_invalid_mode(client):
    tc, _ = client
    created = tc.post("/api/v1/admin/render-policy", json={"domain": "slow.com"}).json()["data"]

    resp = tc.put(f"/api/v1/admin/render-policy/{created['id']}", json={"mode": "nope"})

    assert resp.status_code == 400
    assert resp.json()["code"] == 1001


def test_update_render_policy_unknown_id_returns_404(client):
    tc, _ = client
    resp = tc.put(
        "/api/v1/admin/render-policy/00000000-0000-0000-0000-000000000000",
        json={"enabled": False},
    )

    assert resp.status_code == 404
    assert resp.json()["code"] == 1002


def test_delete_render_policy_removes_row(client):
    tc, session = client
    created = tc.post("/api/v1/admin/render-policy", json={"domain": "slow.com"}).json()["data"]

    resp = tc.delete(f"/api/v1/admin/render-policy/{created['id']}")

    assert resp.status_code == 200
    assert resp.json()["code"] == 0
    assert resp.json()["data"]["id"] == created["id"]
    assert session.policies == []


def test_delete_render_policy_unknown_id_returns_404(client):
    tc, _ = client
    resp = tc.delete("/api/v1/admin/render-policy/00000000-0000-0000-0000-000000000000")

    assert resp.status_code == 404
    assert resp.json()["code"] == 1002
