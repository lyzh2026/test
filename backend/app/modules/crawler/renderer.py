"""DynamicRenderer：基于 Playwright 的统一渲染编排层（PRD 2.1.9）。

优化：
  1. Stealth 反检测（navigator.webdriver 隐藏、chrome 对象注入等）
  2. 上下文隔离（每个 URL 独立 browser context + 绑定特定 proxy）
  3. 浏览器退休机制（达到页面数上限后自动重启）
  4. 随机行为模拟（滚动轮数/间隔随机化）
"""
import asyncio
import logging
import os
import random
import time

import psutil
from playwright.async_api import Browser, Page, Playwright, async_playwright

from app.core.config import settings
from app.modules.crawler.proxy_pool import proxy_pool
from app.modules.crawler.anti_detection import build_stealth_scripts, detect_blocking, random_viewport

logger = logging.getLogger(__name__)

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5_2) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Safari/605.1.15",
]


def _random_ua() -> str:
    return random.choice(_USER_AGENTS)


def _process_tree_mem_mb() -> float:
    try:
        proc = psutil.Process(os.getpid())
        total = proc.memory_info().rss
        for child in proc.children(recursive=True):
            try:
                total += child.memory_info().rss
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return total / 1024 / 1024
    except Exception:
        return 0.0


class DynamicRenderer:
    def __init__(self):
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(settings.RENDER_POOL_SIZE)
        self._page_count = 0  # 当前浏览器进程已处理的页面数

    async def startup(self):
        if self._playwright is None:
            self._playwright = await async_playwright().start()
        await self._launch_browser()
        logger.info(
            "DynamicRenderer started, pool=%s, stealth=%s, context_isol=%s",
            settings.RENDER_POOL_SIZE,
            settings.RENDER_STEALTH_ENABLED,
            settings.RENDER_CONTEXT_ISOLATION,
        )

    async def shutdown(self):
        try:
            if self._browser:
                await self._browser.close()
        finally:
            self._browser = None
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None

    async def _launch_browser(self):
        launch_args = [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-blink-features=AutomationControlled",
        ]
        if settings.RENDER_STEALTH_ENABLED:
            launch_args.extend([
                "--enable-webgl",
                "--use-gl=swiftshader",
                "--enable-accelerated-2d-canvas",
            ])
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=launch_args,
        )
        self._page_count = 0
        logger.info("Browser launched (stealth=%s)", settings.RENDER_STEALTH_ENABLED)

    async def _maybe_recycle(self):
        """检查内存阈值和页面计数，必要时重启浏览器。"""
        mem = _process_tree_mem_mb()
        should_recycle = False
        reasons = []

        if mem > settings.RENDER_HARD_MEM_MB:
            should_recycle = True
            reasons.append(f"memory={mem:.0f}MB > hard={settings.RENDER_HARD_MEM_MB}MB")
        elif mem > settings.RENDER_SOFT_MEM_MB:
            logger.info("Soft mem threshold: %.0f MB", mem)

        if self._page_count >= settings.RENDER_BROWSER_RETIRE_AFTER:
            should_recycle = True
            reasons.append(f"page_count={self._page_count} >= retire={settings.RENDER_BROWSER_RETIRE_AFTER}")

        if should_recycle:
            logger.warning("Recycling browser: %s", "; ".join(reasons))
            async with self._lock:
                try:
                    if self._browser:
                        await self._browser.close()
                except Exception:
                    pass
                await self._launch_browser()

    async def render(
        self,
        url: str,
        *,
        wait_selector: str = "body",
        min_content_length: int = 500,
        scroll: bool = True,
        scroll_rounds_range: tuple[int, int] = (5, 10),
    ) -> dict:
        async with self._semaphore:
            start_ts = time.monotonic()
            await self._maybe_recycle()
            if not self._browser or not self._browser.is_connected():
                async with self._lock:
                    if not self._browser or not self._browser.is_connected():
                        await self._launch_browser()

            proxy_str = await proxy_pool.get_proxy() if settings.PROXY_ENABLED else None
            proxy_config = {"server": proxy_str} if proxy_str else None

            # 上下文隔离：每个 URL 独立 context 或共享
            _ua = _random_ua()
            _vp = random_viewport()
            context_kwargs = dict(
                user_agent=_ua,
                viewport=_vp,
                locale="zh-CN",
                proxy=proxy_config,
                timezone_id="Asia/Shanghai",
            )
            context = await self._browser.new_context(**context_kwargs)
            page = await context.new_page()

            # Stealth：注入增强反检测脚本
            response_headers: dict = {}
            if settings.RENDER_STEALTH_ENABLED:
                for script in build_stealth_scripts():
                    await context.add_init_script(script)

            try:
                resp = await page.goto(url, wait_until="domcontentloaded", timeout=settings.RENDER_TIMEOUT_MS)
                try:
                    await page.wait_for_selector(wait_selector, timeout=10_000)
                except Exception:
                    pass
                if scroll:
                    # 随机滚动轮数
                    scroll_rounds = random.randint(*scroll_rounds_range)
                    await self._auto_scroll(page, scroll_rounds)
                try:
                    await page.wait_for_load_state("networkidle", timeout=5_000)
                except Exception:
                    pass
                html = await page.content()
                title = await page.title()
                final_url = page.url
                # 收集响应头用于拦截检测
                if resp:
                    try:
                        response_headers = await resp.all_headers()
                    except Exception:
                        pass
                # 拦截检测
                status_code = resp.status if resp else 200
                detection = detect_blocking(html, status_code=status_code, headers=response_headers)
                if detection.blocked:
                    logger.warning("anti-detection: %s blocked by %s (confidence=%.2f)", url, detection.block_type, detection.confidence)
                    if proxy_str:
                        await proxy_pool.report_fail(proxy_str)
                    return {
                        "html": html,
                        "title": title,
                        "final_url": final_url,
                        "ok": False,
                        "reason": f"BLOCKED:{detection.block_type}",
                        "block_type": detection.block_type,
                        "block_confidence": detection.confidence,
                    }
                elapsed = (time.monotonic() - start_ts) * 1000
                if proxy_str:
                    await proxy_pool.report_success(proxy_str, elapsed)
                if len(html) < min_content_length:
                    return {"html": html, "title": title, "final_url": final_url, "ok": False, "reason": "CONTENT_TOO_SHORT"}
                self._page_count += 1
                return {"html": html, "title": title, "final_url": final_url, "ok": True}
            except Exception:
                if proxy_str:
                    await proxy_pool.report_fail(proxy_str)
                raise
            finally:
                try:
                    await context.close()
                except Exception:
                    pass

    async def _auto_scroll(self, page: Page, rounds: int):
        for i in range(rounds):
            try:
                await page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
            except Exception:
                break
            # 随机间隔 0.5-2s
            await asyncio.sleep(0.5 + random.random() * 1.5)


renderer = DynamicRenderer()
