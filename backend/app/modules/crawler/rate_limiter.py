"""按域名速率限制器：独立信号量 + 请求间隔控制。

替代全局 Semaphore + renderer 内硬编码 sleep 的方案。
"""
import asyncio
import logging
import random
import time
from urllib.parse import urlparse

from app.core.config import settings

logger = logging.getLogger(__name__)


class DomainRateLimiter:
    """每域名独立并发控制 + 请求间隔。"""

    def __init__(self):
        self._semaphores: dict[str, asyncio.Semaphore] = {}
        self._last_release: dict[str, float] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _get_domain(url: str) -> str:
        return urlparse(url).hostname or "unknown"

    async def acquire(self, url: str):
        """获取许可：等待间隔 → 获取信号量。"""
        domain = self._get_domain(url)
        async with self._lock:
            # 惰性清理无界增长的字典
            if len(self._semaphores) > 500:
                cutoff = time.monotonic() - 600
                stale = [d for d, t in self._last_release.items() if t < cutoff]
                for d in stale:
                    self._semaphores.pop(d, None)
                    self._last_release.pop(d, None)
            if domain not in self._semaphores:
                self._semaphores[domain] = asyncio.Semaphore(settings.CRAWLER_DOMAIN_CONCURRENCY)
            last_time = self._last_release.get(domain, 0.0)

        if last_time > 0:
            delay = settings.CRAWLER_DOMAIN_DELAY_MIN + random.random() * (
                settings.CRAWLER_DOMAIN_DELAY_MAX - settings.CRAWLER_DOMAIN_DELAY_MIN
            )
            elapsed = time.monotonic() - last_time
            if elapsed < delay:
                await asyncio.sleep(delay - elapsed)

        await self._semaphores[domain].acquire()

    async def release(self, url: str):
        """释放许可：记录结束时间 → 释放信号量。"""
        domain = self._get_domain(url)
        async with self._lock:
            self._last_release[domain] = time.monotonic()
        sem = self._semaphores.get(domain)
        if sem:
            sem.release()


domain_rate_limiter = DomainRateLimiter()
