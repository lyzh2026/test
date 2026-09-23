"""渲染路由判定与开关读取。不连 DB、不装 browser-use。"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.crawler.ai_browser import (
    MODE_ALWAYS_AIBROWSER,
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
