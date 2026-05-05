"""Test domain rate limiter at app.modules.crawler.rate_limiter."""
import asyncio
import time
from unittest.mock import patch

import pytest

from app.modules.crawler.rate_limiter import DomainRateLimiter, domain_rate_limiter


class TestDomainRateLimiter:
    """Tests for DomainRateLimiter."""

    # ── synchronous tests (no asyncio needed) ──────────────────────────

    def test_fresh_instance(self):
        """DomainRateLimiter() creates a fresh instance, not the singleton."""
        fresh = DomainRateLimiter()
        assert fresh is not domain_rate_limiter
        assert isinstance(fresh, DomainRateLimiter)

    def test_singleton_exists(self):
        """Module-level domain_rate_limiter singleton exists."""
        from app.modules.crawler.rate_limiter import domain_rate_limiter as drl

        assert drl is not None
        assert isinstance(drl, DomainRateLimiter)

    def test_get_domain(self):
        """_get_domain correctly extracts hostname from URLs."""
        limiter = DomainRateLimiter()

        # Normal URL
        assert limiter._get_domain("https://example.com/page") == "example.com"

        # URL with port (parsed hostname does NOT include port)
        assert limiter._get_domain("https://example.com:8080/page") == "example.com"

        # Subdomain
        assert limiter._get_domain("https://sub.example.com/page") == "sub.example.com"

        # www subdomain
        assert limiter._get_domain("https://www.example.com/page") == "www.example.com"

        # Invalid URL → urlparse gives empty hostname → fallback to "unknown"
        assert limiter._get_domain("not-a-url") == "unknown"

    # ── async tests ───────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_same_domain_sequential_acquire_release(self):
        """Two URLs on the same domain acquire/release correctly (sequential)."""
        limiter = DomainRateLimiter()
        url1 = "https://example.com/page1"
        url2 = "https://example.com/page2"

        await limiter.acquire(url1)
        await limiter.acquire(url2)

        await limiter.release(url1)
        await limiter.release(url2)

    @pytest.mark.asyncio
    async def test_different_domains_dont_block(self):
        """Two URLs on different domains don't block each other."""
        limiter = DomainRateLimiter()
        url1 = "https://example.com/page"
        url2 = "https://other.com/page"

        await limiter.acquire(url1)
        await limiter.acquire(url2)

        await limiter.release(url1)
        await limiter.release(url2)

    @pytest.mark.asyncio
    async def test_same_domain_concurrent_limit(self):
        """Concurrent acquires on same domain respect concurrency limit."""
        with patch("app.modules.crawler.rate_limiter.settings") as mock_settings:
            mock_settings.CRAWLER_DOMAIN_CONCURRENCY = 2
            mock_settings.CRAWLER_DOMAIN_DELAY_MIN = 0.01
            mock_settings.CRAWLER_DOMAIN_DELAY_MAX = 0.01

            limiter = DomainRateLimiter()

            async def hold(url):
                await limiter.acquire(url)
                # hold without releasing — keep semaphore occupied

            # Two concurrent acquires on the same domain should succeed
            t1 = asyncio.create_task(hold("https://example.com/a"))
            t2 = asyncio.create_task(hold("https://example.com/b"))
            await asyncio.wait_for(asyncio.gather(t1, t2), timeout=0.5)

            # Third concurrent acquire should block (concurrency=2 already used)
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(
                    limiter.acquire("https://example.com/c"),
                    timeout=0.1,
                )

    @pytest.mark.asyncio
    async def test_acquire_waits_min_interval(self):
        """Acquire waits for minimum interval between requests on same domain."""
        with patch("app.modules.crawler.rate_limiter.settings") as mock_settings:
            mock_settings.CRAWLER_DOMAIN_CONCURRENCY = 2
            mock_settings.CRAWLER_DOMAIN_DELAY_MIN = 0.05
            mock_settings.CRAWLER_DOMAIN_DELAY_MAX = 0.05

            limiter = DomainRateLimiter()
            url1 = "https://example.com/a"
            url2 = "https://example.com/b"

            # First request: acquire + release sets _last_release for domain
            await limiter.acquire(url1)
            await limiter.release(url1)

            # Second request on same domain must wait for the minimum interval
            t0 = time.monotonic()
            await limiter.acquire(url2)
            elapsed = time.monotonic() - t0

            # Should have waited at least ~0.05 s (allow ~0.02 s tolerance)
            assert elapsed >= 0.03, (
                f"Expected at least 0.03 s delay, got {elapsed:.3f}s"
            )
