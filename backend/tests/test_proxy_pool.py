"""Tests for app.modules.crawler.proxy_pool: ProxyEntry score & ProxyPool lifecycle."""
import asyncio
from unittest.mock import patch

import pytest

from app.modules.crawler.proxy_pool import ProxyEntry, ProxyPool


class TestProxyEntryScore:
    """ProxyEntry.score property — success_rate * 0.7 + speed_score * 0.3."""

    def test_no_requests_returns_one(self):
        entry = ProxyEntry(server="http://proxy:8080")
        assert entry.score == 1.0

    def test_all_success_low_latency_high_score(self):
        """5/5 success, avg 100 ms → high score."""
        entry = ProxyEntry(
            server="http://proxy:8080",
            success_count=5,
            fail_count=0,
            total_latency=500.0,  # avg = 100 ms
        )
        # success_rate = 1.0
        # avg_latency = 100 ms
        # speed_score = max(0, 1.0 - 100/5000) = 0.98
        # score = 1.0 * 0.7 + 0.98 * 0.3 = 0.994
        expected = 1.0 * 0.7 + 0.98 * 0.3
        assert entry.score == pytest.approx(expected)

    def test_all_fail_low_score(self):
        """0/5 success → score = 0.0 * 0.7 + 1.0 * 0.3 = 0.3."""
        entry = ProxyEntry(
            server="http://proxy:8080",
            success_count=0,
            fail_count=5,
            total_latency=0.0,
        )
        assert entry.score == pytest.approx(0.3)

    def test_mixed_results_mid_score(self):
        """3 success, 2 fail, moderate latency → mid-range score."""
        entry = ProxyEntry(
            server="http://proxy:8080",
            success_count=3,
            fail_count=2,
            total_latency=5000.0,  # avg = 1000 ms
        )
        # success_rate = 3/5 = 0.6
        # avg_latency = 1000 ms
        # speed_score = max(0, 1.0 - 1000/5000) = 0.8
        # score = 0.6 * 0.7 + 0.8 * 0.3 = 0.42 + 0.24 = 0.66
        expected = 0.6 * 0.7 + 0.8 * 0.3
        assert entry.score == pytest.approx(expected)


class TestProxyPool:
    """ProxyPool: get_proxy, report_success, report_fail, health check, lifecycle."""

    # ------------------------------------------------------------------
    # get_proxy
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_proxy_returns_none_when_no_proxies(self):
        pool = ProxyPool()
        await pool.startup([])
        result = await pool.get_proxy()
        assert result is None
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_get_proxy_returns_from_available_list(self):
        pool = ProxyPool()
        await pool.startup(["http://proxy1:8080", "http://proxy2:8080"])
        pool._bg_task.cancel()
        result = await pool.get_proxy()
        assert result in ("http://proxy1:8080", "http://proxy2:8080")
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_get_proxy_excludes_disabled(self):
        pool = ProxyPool()
        await pool.startup(["http://proxy1:8080", "http://proxy2:8080"])
        pool._bg_task.cancel()
        pool._proxies[0].disabled = True
        for _ in range(20):
            result = await pool.get_proxy()
            assert result == "http://proxy2:8080"
        await pool.shutdown()

    # ------------------------------------------------------------------
    # report_success
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_report_success_increments_and_resets_fails(self):
        pool = ProxyPool()
        await pool.startup(["http://proxy:8080"])
        pool._bg_task.cancel()
        entry = pool._proxies[0]
        entry.fail_count = 2
        entry.consecutive_fails = 2

        await pool.report_success("http://proxy:8080", latency_ms=200.0)

        assert entry.success_count == 1
        assert entry.total_latency == pytest.approx(200.0)
        assert entry.consecutive_fails == 0
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_report_success_accumulates_latency(self):
        pool = ProxyPool()
        await pool.startup(["http://proxy:8080"])
        pool._bg_task.cancel()
        await pool.report_success("http://proxy:8080", latency_ms=100.0)
        await pool.report_success("http://proxy:8080", latency_ms=300.0)
        entry = pool._proxies[0]
        assert entry.success_count == 2
        assert entry.total_latency == pytest.approx(400.0)
        await pool.shutdown()

    # ------------------------------------------------------------------
    # report_fail
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_report_fail_disables_after_max_consecutive_fails(self):
        pool = ProxyPool(max_consecutive_fails=3)
        await pool.startup(["http://proxy:8080"])
        pool._bg_task.cancel()
        entry = pool._proxies[0]

        for _ in range(3):
            await pool.report_fail("http://proxy:8080")

        assert entry.fail_count == 3
        assert entry.consecutive_fails == 3
        assert entry.disabled is True
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_report_fail_does_not_disable_below_threshold(self):
        pool = ProxyPool(max_consecutive_fails=3)
        await pool.startup(["http://proxy:8080"])
        pool._bg_task.cancel()
        entry = pool._proxies[0]

        await pool.report_fail("http://proxy:8080")
        await pool.report_fail("http://proxy:8080")

        assert entry.fail_count == 2
        assert entry.disabled is False
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_success_resets_consecutive_fail_counter(self):
        """A success in the middle of failures prevents disable."""
        pool = ProxyPool(max_consecutive_fails=3)
        await pool.startup(["http://proxy:8080"])
        pool._bg_task.cancel()
        entry = pool._proxies[0]

        await pool.report_fail("http://proxy:8080")
        await pool.report_fail("http://proxy:8080")
        await pool.report_success("http://proxy:8080", latency_ms=50.0)
        await pool.report_fail("http://proxy:8080")
        await pool.report_fail("http://proxy:8080")

        # consecutive_fails goes 1→2→0→1→2, never reaches 3
        assert entry.disabled is False
        assert entry.consecutive_fails == 2
        await pool.shutdown()

    # ------------------------------------------------------------------
    # Health check — re-enable disabled proxies on cycle
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_health_check_reenables_disabled_proxies(self):
        """Every 3 cycles, disabled proxies should be re-enabled."""
        pool = ProxyPool()
        await pool.startup(["http://proxy1:8080", "http://proxy2:8080"])
        pool._bg_task.cancel()
        pool._proxies[0].disabled = True
        pool._proxies[0].consecutive_fails = 3
        pool._proxies[1].disabled = True
        pool._proxies[1].consecutive_fails = 5

        call_count = 0

        async def controlled_sleep(_duration):
            nonlocal call_count
            call_count += 1
            if call_count > 3:
                raise asyncio.CancelledError()

        with patch.object(asyncio, "sleep", controlled_sleep):
            try:
                await pool._health_check_loop()
            except asyncio.CancelledError:
                pass

        assert not pool._proxies[0].disabled
        assert pool._proxies[0].consecutive_fails == 0
        assert not pool._proxies[1].disabled
        assert pool._proxies[1].consecutive_fails == 0
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_health_check_does_not_reenable_before_cycle_3(self):
        """After 1-2 cycles, disabled proxies stay disabled."""
        pool = ProxyPool()
        await pool.startup(["http://proxy:8080"])
        pool._bg_task.cancel()
        pool._proxies[0].disabled = True
        pool._proxies[0].consecutive_fails = 3

        call_count = 0

        async def controlled_sleep(_duration):
            nonlocal call_count
            call_count += 1
            if call_count > 1:
                raise asyncio.CancelledError()

        with patch.object(asyncio, "sleep", controlled_sleep):
            try:
                await pool._health_check_loop()
            except asyncio.CancelledError:
                pass

        assert pool._proxies[0].disabled is True
        assert pool._proxies[0].consecutive_fails == 3
        await pool.shutdown()

    # ------------------------------------------------------------------
    # Lifecycle: startup / shutdown
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_startup_loads_from_list(self):
        pool = ProxyPool()
        await pool.startup(["http://p1:8080", "http://p2:8080", ""])
        assert pool.count == 2  # empty string filtered out
        assert pool._proxies[0].server == "http://p1:8080"
        assert pool._proxies[1].server == "http://p2:8080"
        assert pool._bg_task is not None
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_startup_empty_list_does_not_create_bg_task(self):
        pool = ProxyPool()
        await pool.startup([])
        assert pool.count == 0
        assert pool._bg_task is None
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_shutdown_cancels_bg_task(self):
        pool = ProxyPool()
        await pool.startup(["http://proxy:8080"])
        assert pool._bg_task is not None
        assert not pool._bg_task.done()
        await pool.shutdown()
        assert pool._bg_task is None

    @pytest.mark.asyncio
    async def test_shutdown_idempotent(self):
        pool = ProxyPool()
        await pool.startup(["http://proxy:8080"])
        await pool.shutdown()
        await pool.shutdown()  # second call should not raise
        assert pool._bg_task is None

    # ------------------------------------------------------------------
    # Edge cases
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_proxy_unknown_server_does_not_raise(self):
        pool = ProxyPool()
        await pool.startup(["http://proxy:8080"])
        pool._bg_task.cancel()
        await pool.report_success("http://unknown:8080", latency_ms=10.0)
        await pool.report_fail("http://unknown:8080")
        # no exception — silent ignore
        await pool.shutdown()
