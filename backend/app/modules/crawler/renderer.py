"""DynamicRenderer：基于 Playwright 的统一渲染编排层（PRD 2.1.9）。

优化：
  1. Stealth 反检测（navigator.webdriver 隐藏、chrome 对象注入等）
  2. 上下文隔离（每个 URL 独立 browser context + 绑定特定 proxy）
  3. 浏览器退休机制（达到页面数上限后自动重启）
  4. 随机行为模拟（滚动轮数/间隔随机化）
  5. httpx 快速请求（静态页面跳过 Playwright）
"""
import asyncio
import logging
import os
import random
import time

import httpx
import psutil
from bs4 import BeautifulSoup
from playwright.async_api import Browser, Page, Playwright, async_playwright

from app.core.config import settings
from app.modules.crawler.proxy_pool import proxy_pool
from app.modules.crawler.anti_detection import build_stealth_scripts, detect_blocking, random_viewport

logger = logging.getLogger(__name__)

# httpx 共享客户端（连接池复用）
_httpx_client: httpx.AsyncClient | None = None

# 判断页面是否需要 JS 渲染的最小标签数阈值
_STATIC_MIN_TAGS = 10

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
        self._shared_context = None  # 非隔离模式下的共享 context

    async def startup(self):
        global _httpx_client
        if _httpx_client is None:
            _httpx_client = httpx.AsyncClient(
                timeout=httpx.Timeout(15.0, connect=10.0),
                follow_redirects=True,
                limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
            )
        if self._playwright is None:
            self._playwright = await async_playwright().start()
        await self._launch_browser()
        logger.info(
            "DynamicRenderer started, pool=%s, stealth=%s, context_isol=%s",
            settings.RENDER_POOL_SIZE,
            settings.RENDER_STEALTH_ENABLED,
            settings.RENDER_CONTEXT_ISOLATION,
        )

    @staticmethod
    async def fast_fetch(url: str, *, min_content_length: int = 500) -> dict | None:
        """httpx 快速请求：静态页面直接返回 HTML，跳过 Playwright。

        返回 None 表示需要 JS 渲染（降级到 Playwright）。
        返回 dict 表示成功获取，格式同 render()。
        """
        global _httpx_client
        if _httpx_client is None:
            return None
        try:
            resp = await _httpx_client.get(url, headers={"User-Agent": _random_ua()})
            if resp.status_code != 200:
                return None
            html = resp.text
            if len(html) < min_content_length:
                return None
            # 检测是否为 JS 渲染页面：标签数过少说明内容靠 JS 生成
            tag_count = html.count("<") + html.count("</")
            if tag_count < _STATIC_MIN_TAGS:
                return None
            # 检测常见 JS 渲染框架的空壳标记
            lower = html.lower()
            if any(marker in lower for marker in [
                "id=\"__next\"", "id=\"__nuxt\"", "id=\"app\"", "id=\"root\"",
                "<noscript>", "window.__INITIAL_STATE__",
            ]):
                # 有 JS 框架标记但标签数够多，可能是 SSR 页面，仍可尝试
                # 如果 body 内文本过短则降级
                soup = await asyncio.to_thread(BeautifulSoup, html, "lxml")
                body = soup.find("body")
                if body and len(body.get_text(strip=True)) < 100:
                    return None
            title = ""
            try:
                soup = await asyncio.to_thread(BeautifulSoup, html, "lxml")
                t = soup.find("title")
                if t:
                    title = t.get_text(strip=True)
            except Exception:
                pass
            return {"html": html, "title": title, "final_url": str(resp.url), "ok": True}
        except Exception:
            return None

    async def shutdown(self):
        global _httpx_client
        try:
            if _httpx_client:
                await _httpx_client.aclose()
                _httpx_client = None
            if self._shared_context:
                await self._shared_context.close()
                self._shared_context = None
            if self._browser:
                await self._browser.close()
        finally:
            self._browser = None
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None

    async def _launch_browser(self):
        self._shared_context = None  # 浏览器重启时清除共享上下文
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
        scroll_rounds_range: tuple[int, int] = (2, 3),
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
            if settings.RENDER_CONTEXT_ISOLATION:
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
            else:
                if self._shared_context is None or self._shared_context.is_closed():
                    self._shared_context = await self._browser.new_context(
                        user_agent=_random_ua(),
                        viewport=random_viewport(),
                        locale="zh-CN",
                        timezone_id="Asia/Shanghai",
                    )
                context = self._shared_context
            page = await context.new_page()

            # Stealth：注入增强反检测脚本
            response_headers: dict = {}
            if settings.RENDER_STEALTH_ENABLED:
                for script in build_stealth_scripts():
                    await context.add_init_script(script)

            try:
                resp = await page.goto(url, wait_until="domcontentloaded", timeout=settings.RENDER_TIMEOUT_MS)
                if scroll:
                    # 随机滚动轮数
                    scroll_rounds = random.randint(*scroll_rounds_range)
                    await self._auto_scroll(page, scroll_rounds)
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
                    if settings.RENDER_CONTEXT_ISOLATION:
                        await context.close()
                    else:
                        await page.close()
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
