"""ProxyPool：代理池管理——健康检测、评分排序、自动轮换。"""
import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Optional

import psutil

logger = logging.getLogger(__name__)


@dataclass
class ProxyEntry:
    server: str
    success_count: int = 0
    fail_count: int = 0
    total_latency: float = 0.0
    consecutive_fails: int = 0
    disabled: bool = False

    @property
    def score(self) -> float:
        total = self.success_count + self.fail_count
        if total == 0:
            return 1.0
        success_rate = self.success_count / total
        avg_latency = self.total_latency / total
        speed_score = max(0.0, 1.0 - avg_latency / 5000.0)
        return success_rate * 0.7 + speed_score * 0.3


class ProxyPool:
    def __init__(self, max_consecutive_fails: int = 3):
        self._proxies: list[ProxyEntry] = []
        self._lock = asyncio.Lock()
        self._bg_task: Optional[asyncio.Task] = None
        self._max_consecutive_fails = max_consecutive_fails

    async def startup(self, proxy_list: list[str]):
        self._proxies = [ProxyEntry(server=p) for p in proxy_list if p]
        logger.info("ProxyPool loaded %s proxies", len(self._proxies))
        if self._proxies:
            self._bg_task = asyncio.create_task(self._health_check_loop())

    async def shutdown(self):
        if self._bg_task:
            self._bg_task.cancel()
            try:
                await self._bg_task
            except asyncio.CancelledError:
                pass
            self._bg_task = None

    @property
    def count(self) -> int:
        return len(self._proxies)

    async def get_proxy(self) -> Optional[str]:
        """按评分加权随机选一个可用代理。"""
        async with self._lock:
            available = [p for p in self._proxies if not p.disabled]
            if not available:
                return None
            scores = [p.score for p in available]
            total = sum(scores)
            if total <= 0:
                chosen = random.choice(available)
            else:
                r = random.uniform(0, total)
                cum = 0.0
                chosen = available[0]
                for p, s in zip(available, scores):
                    cum += s
                    if r <= cum:
                        chosen = p
                        break
            return chosen.server

    async def report_success(self, server: str, latency_ms: float):
        async with self._lock:
            entry = self._find(server)
            if entry:
                entry.success_count += 1
                entry.total_latency += latency_ms
                entry.consecutive_fails = 0

    async def report_fail(self, server: str):
        async with self._lock:
            entry = self._find(server)
            if entry:
                entry.fail_count += 1
                entry.consecutive_fails += 1
                if entry.consecutive_fails >= self._max_consecutive_fails:
                    entry.disabled = True
                    logger.warning("proxy %s disabled after %s consecutive fails",
                                   server, entry.consecutive_fails)

    def _find(self, server: str) -> Optional[ProxyEntry]:
        for p in self._proxies:
            if p.server == server:
                return p
        return None

    async def _health_check_loop(self):
        """每 120 秒遍历代理，禁用满 3 个周期的尝试重激活。"""
        cycle = 0
        while True:
            await asyncio.sleep(120)
            cycle += 1
            async with self._lock:
                # 每 3 个周期（6 分钟）尝试恢复被禁用的代理
                if cycle % 3 == 0:
                    for p in self._proxies:
                        if p.disabled:
                            p.disabled = False
                            p.consecutive_fails = 0
                            logger.info("proxy %s re-enabled for retry", p.server)
                active = sum(1 for p in self._proxies if not p.disabled)
            logger.debug("proxy health check: %s/%s active", active, len(self._proxies))


proxy_pool = ProxyPool()
