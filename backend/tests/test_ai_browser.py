"""渲染路由判定与开关读取。不连 DB、不装 browser-use。"""
import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.crawler.ai_browser import (
    MODE_ALWAYS_AIBROWSER,
    browse_with_ai,
    domain_of,
    is_ai_browser_enabled,
    load_route_policy,
    should_direct_connect,
)


class TestDomainOf:
    def test_extracts_hostname_lowercased(self):
        assert domain_of("https://WWW.Example.COM/a/b?c=1") == "www.example.com"

    def test_invalid_url_returns_empty(self):
        assert domain_of("not a url") == ""

    def test_strips_port(self):
        assert domain_of("https://example.com:8443/x") == "example.com"


class TestShouldDirectConnect:
    def test_whitelisted_and_enabled(self):
        policy = {"example.com": MODE_ALWAYS_AIBROWSER}
        assert should_direct_connect("https://example.com/a", policy, True) is True

    def test_whitelisted_but_switch_off(self):
        policy = {"example.com": MODE_ALWAYS_AIBROWSER}
        assert should_direct_connect("https://example.com/a", policy, False) is False

    def test_not_in_policy(self):
        assert should_direct_connect("https://other.com/a", {"example.com": MODE_ALWAYS_AIBROWSER}, True) is False

    def test_other_mode_does_not_direct_connect(self):
        assert should_direct_connect("https://example.com/a", {"example.com": "always_static"}, True) is False

    def test_subdomain_not_matched(self):
        policy = {"example.com": MODE_ALWAYS_AIBROWSER}
        assert should_direct_connect("https://news.example.com/a", policy, True) is False


class TestIsAiBrowserEnabled:
    @pytest.mark.asyncio
    async def test_missing_config_defaults_false(self):
        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result)
        assert await is_ai_browser_enabled(session) is False

    @pytest.mark.asyncio
    async def test_reads_enabled_true(self):
        session = AsyncMock()
        cfg = MagicMock()
        cfg.value = {"enabled": True}
        result = MagicMock()
        result.scalar_one_or_none.return_value = cfg
        session.execute = AsyncMock(return_value=result)
        assert await is_ai_browser_enabled(session) is True

    @pytest.mark.asyncio
    async def test_non_dict_value_defaults_false(self):
        session = AsyncMock()
        cfg = MagicMock()
        cfg.value = True
        result = MagicMock()
        result.scalar_one_or_none.return_value = cfg
        session.execute = AsyncMock(return_value=result)
        assert await is_ai_browser_enabled(session) is False

    @pytest.mark.asyncio
    async def test_db_error_defaults_false(self):
        session = AsyncMock()
        session.execute = AsyncMock(side_effect=RuntimeError("db down"))
        assert await is_ai_browser_enabled(session) is False


class TestLoadRoutePolicy:
    @pytest.mark.asyncio
    async def test_maps_domain_to_mode(self):
        session = AsyncMock()
        a = MagicMock(); a.domain = "A.com"; a.mode = MODE_ALWAYS_AIBROWSER
        b = MagicMock(); b.domain = "b.com"; b.mode = "auto"
        result = MagicMock()
        result.scalars.return_value.all.return_value = [a, b]
        session.execute = AsyncMock(return_value=result)
        assert await load_route_policy(session) == {"a.com": MODE_ALWAYS_AIBROWSER, "b.com": "auto"}

    @pytest.mark.asyncio
    async def test_db_error_returns_empty(self):
        session = AsyncMock()
        session.execute = AsyncMock(side_effect=RuntimeError("db down"))
        assert await load_route_policy(session) == {}


class TestBrowseWithAi:
    @pytest.mark.asyncio
    async def test_non_dict_json_output_returns_ok_false(self, monkeypatch):
        """AI 返回合法 JSON 但不是对象（如数组）时必须收敛为 ok=False，不抛异常。"""

        class _FakeHistory:
            def final_result(self):
                return '["a", "b"]'

        class _FakeAgent:
            def __init__(self, task=None, llm=None):
                pass

            async def run(self, *a, **k):
                return _FakeHistory()

        class _FakeChatOpenAI:
            def __init__(self, **kwargs):
                pass

        fake_module = types.ModuleType("browser_use")
        fake_module.Agent = _FakeAgent
        fake_module.ChatOpenAI = _FakeChatOpenAI
        monkeypatch.setitem(sys.modules, "browser_use", fake_module)

        res = await browse_with_ai("https://example.com/x", api_key="k", base_url="", model="m")

        assert isinstance(res, dict)
        assert res["ok"] is False
        assert res["reason"] == "AI Browser 输出无法解析为 JSON"
