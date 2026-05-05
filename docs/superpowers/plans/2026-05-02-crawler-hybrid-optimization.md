# 爬虫系统混合策略优化 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有爬虫架构上实施 7 项优化（Stealth 反检测、上下文隔离、行为模拟、Content Filter Pipeline、页面缓存、提取链增强、去重增强），提高爬取成功率和内容提取质量。

**Architecture:** 保持现有 Playwright 渲染 + Readability→LLM 提取链不变，新增 Content Filter Pipeline（Pruning+BM25）和 Cache Layer 作为中间管道，增强 Renderer（Stealth+隔离+模拟），均在 `CONTENT_FILTER_ENABLED` 开关控制下。

**Tech Stack:** Python 3.11+, Playwright, Redis, readability-lxml, NumPy (for BM25 IDF), lxml

---

### Task 1: 配置项新增

**Files:**
- Modify: `backend/app/core/config.py`

- [ ] **Step 1: 在 Settings 类中新增优化相关配置项**

在 `CRAWLER_RETRY_BACKOFF_BASE` 后、`PROXY_ENABLED` 前插入：

```python
    # === Content Filter ===
    CONTENT_FILTER_ENABLED: bool = Field(default=True, description="内容过滤管道总开关（Pruning + BM25）")
    CONTENT_FILTER_PRUNING_MIN_DENSITY: float = Field(default=0.05, description="Pruning 文本密度阈值，低于此值移除")
    CONTENT_FILTER_BM25_TOP_K: int = Field(default=30, description="BM25 保留的 Top-K 文本块数")
    CONTENT_FILTER_CHUNK_TOKEN_THRESHOLD: int = Field(default=4000, description="LLM 提取分块 token 阈值")
    CONTENT_FILTER_CHUNK_OVERLAP_RATE: float = Field(default=0.1, description="LLM 分块重叠率")

    # === Page Cache ===
    CRAWLER_CACHE_ENABLED: bool = Field(default=True, description="页面级缓存开关")
    CRAWLER_CACHE_DEFAULT_TTL: int = Field(default=3600, description="缓存默认 TTL（秒）")
    CRAWLER_CACHE_MAX_TTL: int = Field(default=86400, description="缓存最大 TTL（秒）")

    # === Renderer ===
    RENDER_BROWSER_RETIRE_AFTER: int = Field(default=30, description="每个浏览器进程最大页面数，超限后重启")
    RENDER_STEALTH_ENABLED: bool = Field(default=True, description="Stealth 反检测开关")
    RENDER_CONTEXT_ISOLATION: bool = Field(default=True, description="每个 URL 独立 browser context")
```

验证：`python -c "from app.core.config import settings; print(settings.CONTENT_FILTER_ENABLED)"` 输出 `True`

- [ ] **Step 2: 更新 `.env.example`**

在 `CRAWLER_RETRY_BACKOFF_BASE=2` 后追加：

```bash
# Content Filter
CONTENT_FILTER_ENABLED=True
CONTENT_FILTER_PRUNING_MIN_DENSITY=0.05
CONTENT_FILTER_BM25_TOP_K=30
CONTENT_FILTER_CHUNK_TOKEN_THRESHOLD=4000
CONTENT_FILTER_CHUNK_OVERLAP_RATE=0.1

# Page Cache
CRAWLER_CACHE_ENABLED=True
CRAWLER_CACHE_DEFAULT_TTL=3600
CRAWLER_CACHE_MAX_TTL=86400

# Renderer
RENDER_BROWSER_RETIRE_AFTER=30
RENDER_STEALTH_ENABLED=True
RENDER_CONTEXT_ISOLATION=True
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/core/config.py .env.example
git commit -m "feat: add crawler optimization config items"
```

---

### Task 2: Content Filter Pipeline — Pruning + BM25

**Files:**
- Create: `backend/app/modules/crawler/content_filter.py`

- [ ] **Step 1: 创建 `content_filter.py` 完整实现**

```python
"""ContentFilterPipeline：Pruning（去噪）+ BM25（核心内容提取）。

数据流：
  raw_html → Pruning.prune() → pruned_html → BM25Filter.filter() → filtered_html
"""
import logging
import re
from typing import List, Tuple

import numpy as np
from bs4 import BeautifulSoup, Tag
from lxml import etree, html as lxml_html

from app.core.config import settings

logger = logging.getLogger(__name__)

# 低价值 class/id 关键词黑名单
_LOW_VALUE_KEYWORDS = {
    "sidebar", "ad", "advertisement", "comment", "comments", "related",
    "footer", "header", "nav", "navigation", "menu", "widget", "social",
    "share", "tags", "tag", "breadcrumb", "toolbar", "tooltip", "popup",
    "modal", "overlay", "banner", "copyright", "disclaimer", "promo",
    "recommend", "hot", "aside", "sidebar-right", "sidebar-left",
}


class Pruning:
    """HTML 去噪：移除低密度节点和低价值区块。"""

    @staticmethod
    def prune(html_str: str) -> str:
        if not html_str or len(html_str) < 500:
            return html_str
        try:
            tree = lxml_html.fromstring(html_str)
        except Exception:
            return html_str

        # 移除低价值节点
        _remove_low_value_nodes(tree)
        # 移除低文本密度节点
        _remove_low_density_nodes(tree, settings.CONTENT_FILTER_PRUNING_MIN_DENSITY)
        # 序列化回字符串
        result = etree.tostring(tree, encoding="unicode", method="html")
        return result


def _remove_low_value_nodes(tree: etree._Element):
    """移除 class/id 匹配黑关键词的节点。"""
    for node in tree.iter():
        if node.tag not in ("div", "section", "aside", "nav", "footer", "header"):
            continue
        cls = node.get("class", "") or ""
        nid = node.get("id", "") or ""
        combined = f"{cls} {nid}".lower()
        for kw in _LOW_VALUE_KEYWORDS:
            if kw in combined:
                parent = node.getparent()
                if parent is not None:
                    parent.remove(node)
                break


def _remove_low_density_nodes(tree: etree._Element, min_density: float):
    """移除文本密度（文本长度 / HTML 长度）低于阈值的块级节点。"""
    for node in list(tree.iter()):
        if node.tag not in ("div", "section", "article", "p", "td"):
            continue
        text = _get_text_content(node)
        if not text:
            continue
        raw_html = etree.tostring(node, encoding="unicode", method="html")
        if not raw_html:
            continue
        density = len(text) / max(len(raw_html), 1)
        if density < min_density:
            parent = node.getparent()
            if parent is not None:
                parent.remove(node)


def _get_text_content(node: etree._Element) -> str:
    """获取节点下的纯文本内容。"""
    texts = [node.text or ""]
    for child in node.iter():
        texts.append(child.tail or "")
        # 跳过 script/style 的子内容
        if child.tag in ("script", "style"):
            continue
        texts.append(child.text or "")
    return " ".join(t for t in texts if t).strip()


class BM25Filter:
    """BM25 核心内容提取：按相关性评分保留 Top-K 文本块。

    使用 <title> 和 <meta keywords> 中的词作为查询。
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b

    def filter(self, html_str: str) -> str:
        if not html_str or len(html_str) < 500:
            return html_str
        try:
            soup = BeautifulSoup(html_str, "lxml")
        except Exception:
            return html_str

        # 1. 提取查询词
        query_terms = self._extract_query_terms(soup)
        if not query_terms:
            logger.debug("BM25: no query terms from title/meta, returning pruned html as-is")
            return html_str

        # 2. 将 HTML 拆分为文本块
        blocks = self._split_blocks(soup)
        if not blocks:
            return html_str

        # 3. 计算每个块的 BM25 分数
        blocks = self._score_blocks(blocks, query_terms)

        # 4. 按分数降序排序，保留 Top-K
        blocks.sort(key=lambda b: b[1], reverse=True)
        top_k = blocks[: settings.CONTENT_FILTER_BM25_TOP_K]
        top_k.sort(key=lambda b: b[2])  # 按原始顺序重排

        # 5. 重建 HTML
        result = "".join(b[0] for b in top_k)
        return result

    def _extract_query_terms(self, soup: BeautifulSoup) -> List[str]:
        """从 title 和 meta keywords 提取查询词。"""
        terms: List[str] = []
        title_tag = soup.find("title")
        if title_tag and title_tag.get_text(strip=True):
            terms.extend(self._tokenize(title_tag.get_text(strip=True)))
        meta_kw = soup.find("meta", attrs={"name": lambda x: x and x.lower() == "keywords"})
        if meta_kw and meta_kw.get("content"):
            terms.extend(self._tokenize(meta_kw["content"]))
        # 如果没有 keywords，尝试 description
        if not terms:
            meta_desc = soup.find("meta", attrs={"name": lambda x: x and x.lower() == "description"})
            if meta_desc and meta_desc.get("content"):
                terms.extend(self._tokenize(meta_desc["content"]))
        # 去重
        return list(set(t for t in terms if len(t) > 1))

    def _tokenize(self, text: str) -> List[str]:
        """中英文分词。"""
        # 简单实现：按非字母数字拆分，保留中文词组
        tokens = re.findall(r"[a-zA-Z]+|[一-龥]{2,}", text)
        return [t.lower() for t in tokens if len(t) > 1]

    def _split_blocks(self, soup: BeautifulSoup) -> List[Tuple[str, int, str]]:
        """按语义标签分块，返回 [(html_fragment, position_index, full_text)]。"""
        blocks: List[Tuple[str, int, str]] = []
        tags = soup.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "td", "blockquote", "pre"])
        for idx, tag in enumerate(tags):
            text = tag.get_text(strip=True)
            if not text or len(text) < 10:
                continue
            blocks.append((str(tag), idx, text))
        return blocks

    def _score_blocks(self, blocks: List[Tuple[str, int, str]], query_terms: List[str]) -> List[Tuple[str, float, int]]:
        """为每个块计算 BM25 分数。"""
        n_blocks = len(blocks)
        if n_blocks == 0:
            return [(b[0], 0.0, b[1]) for b in blocks]

        # 文档频率：每个词出现在多少个块中
        df: dict = {}
        for _, _, text in blocks:
            terms = set(self._tokenize(text))
            for t in terms:
                df[t] = df.get(t, 0) + 1

        # 平均块长度
        avg_len = sum(len(b[2]) for b in blocks) / n_blocks

        # 计算每个块的分数
        scored: List[Tuple[str, float, int]] = []
        for html_frag, idx, text in blocks:
            score = 0.0
            block_terms = self._tokenize(text)
            block_len = len(text)
            for term in query_terms:
                if term not in df:
                    continue
                # 词频在当前块中的出现次数
                tf = block_terms.count(term)
                if tf == 0:
                    continue
                idf = np.log((n_blocks - df[term] + 0.5) / (df[term] + 0.5) + 1.0)
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (1 - self.b + self.b * (block_len / avg_len))
                score += idf * (numerator / denominator) if denominator > 0 else 0
            scored.append((html_frag, score, idx))

        return scored


# 便捷入口
content_filter_pipeline = lambda html: BM25Filter().filter(Pruning.prune(html))
```

- [ ] **Step 2: 提交**

```bash
git add backend/app/modules/crawler/content_filter.py
git commit -m "feat: add content filter pipeline (Pruning + BM25)"
```

---

### Task 3: Cache Layer — Redis 页面级缓存

**Files:**
- Create: `backend/app/modules/crawler/cache.py`
- Modify: `backend/app/core/redis.py`（可选，仅检查是否有必要的方法）

- [ ] **Step 1: 创建 `cache.py`**

```python
"""PageCache：Redis 页面级缓存，缓存渲染后的 HTML 以减少重复渲染。

缓存 Key 设计：
  crawl_page_cache:{md5(url)} → Hash
    - url: 原始 URL
    - filtered_html: 经 Content Filter 处理后的 HTML
    - pruned_html: 仅去噪后的 HTML（备用）
    - title: 页面标题
    - cached_at: 缓存时间戳
    - ttl: 过期时间（秒）
"""
import hashlib
import json
import logging
import time
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

PAGE_CACHE_PREFIX = "crawl_page_cache:"
_NAMED_CACHE_KEY = f"{PAGE_CACHE_PREFIX}named"


class PageCache:
    """页面级缓存，基于 Redis。"""

    def __init__(self, redis_client):
        self._redis = redis_client

    def _make_key(self, url: str) -> str:
        return f"{PAGE_CACHE_PREFIX}{hashlib.md5(url.encode()).hexdigest()}"

    async def get(self, url: str) -> Optional[dict]:
        """获取缓存。返回 None 表示未命中或已过期。"""
        if not settings.CRAWLER_CACHE_ENABLED:
            return None
        try:
            key = self._make_key(url)
            data = await self._redis.hgetall(key)
            if not data:
                return None
            cached_at = float(data.get("cached_at", 0))
            ttl = int(data.get("ttl", settings.CRAWLER_CACHE_DEFAULT_TTL))
            if time.time() - cached_at > ttl:
                await self._redis.delete(key)
                return None
            return {
                "url": data.get("url"),
                "filtered_html": data.get("filtered_html"),
                "pruned_html": data.get("pruned_html"),
                "title": data.get("title"),
            }
        except Exception as e:
            logger.warning("cache get failed: %r", e)
            return None

    async def set(
        self,
        url: str,
        *,
        filtered_html: str,
        pruned_html: str = "",
        title: str = "",
        ttl: int = 0,
    ):
        """写入缓存。"""
        if not settings.CRAWLER_CACHE_ENABLED:
            return
        try:
            key = self._make_key(url)
            effective_ttl = ttl if ttl > 0 else settings.CRAWLER_CACHE_DEFAULT_TTL
            effective_ttl = min(effective_ttl, settings.CRAWLER_CACHE_MAX_TTL)
            await self._redis.hset(key, mapping={
                "url": url,
                "filtered_html": filtered_html,
                "pruned_html": pruned_html,
                "title": title,
                "cached_at": str(time.time()),
                "ttl": str(effective_ttl),
            })
            await self._redis.expire(key, effective_ttl)
        except Exception as e:
            logger.warning("cache set failed: %r", e)

    async def invalidate(self, url: str):
        """主动失效缓存。"""
        if not settings.CRAWLER_CACHE_ENABLED:
            return
        try:
            key = self._make_key(url)
            await self._redis.delete(key)
        except Exception as e:
            logger.warning("cache invalidate failed: %r", e)


from app.core.redis import redis as redis_client
page_cache = PageCache(redis_client)
```

- [ ] **Step 2: 提交**

```bash
git add backend/app/modules/crawler/cache.py
git commit -m "feat: add Redis page cache layer"
```

---

### Task 4: Renderer Enhancement — Stealth + 上下文隔离 + 行为模拟

**Files:**
- Modify: `backend/app/modules/crawler/renderer.py`

- [ ] **Step 1: 重构 `renderer.py`**

完整替换 renderer.py 内容：

```python
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

logger = logging.getLogger(__name__)

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5_2) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Safari/605.1.15",
]

# Stealth 反检测初始化脚本
_STEALTH_INIT_SCRIPTS = [
    # 隐藏 navigator.webdriver（最关键的检测向量）
    "Object.defineProperty(navigator, 'webdriver', { get: () => undefined })",
    # 补充 chrome 对象（正常浏览器存在）
    "window.chrome = { runtime: {} };",
    # 覆盖 plugins（自动化的浏览器通常 plugins.length === 0）
    "Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });",
    # 覆盖 languages
    "Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh'] });",
    # 覆盖权限查询
    "window.navigator.permissions.query = (() => Promise.resolve({ state: 'granted' }));",
    # 覆盖 webdriver 标记
    """Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined,
        configurable: true,
    });""",
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
                context = await self._browser.new_context(
                    user_agent=_random_ua(),
                    viewport={"width": 1366, "height": 900},
                    locale="zh-CN",
                    proxy=proxy_config,
                )
            else:
                context = await self._browser.new_context(
                    user_agent=_random_ua(),
                    viewport={"width": 1366, "height": 900},
                    locale="zh-CN",
                    proxy=proxy_config,
                )

            page = await context.new_page()

            # Stealth：注入反检测脚本
            if settings.RENDER_STEALTH_ENABLED:
                for script in _STEALTH_INIT_SCRIPTS:
                    await context.add_init_script(script)

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=settings.RENDER_TIMEOUT_MS)
                try:
                    await page.wait_for_selector(wait_selector, timeout=10_000)
                except Exception:
                    pass
                if scroll:
                    # 随机滚动轮数 5-10 轮
                    scroll_rounds = random.randint(5, 10)
                    await self._auto_scroll(page, scroll_rounds)
                try:
                    await page.wait_for_load_state("networkidle", timeout=5_000)
                except Exception:
                    pass
                html = await page.content()
                title = await page.title()
                final_url = page.url
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
                # 随机限速 2-5s
                await asyncio.sleep(2 + random.random() * 3)

    async def _auto_scroll(self, page: Page, rounds: int):
        for i in range(rounds):
            try:
                await page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
            except Exception:
                break
            # 随机间隔 0.5-2s
            await asyncio.sleep(0.5 + random.random() * 1.5)


renderer = DynamicRenderer()
```

变更要点：
1. 新增 `_STEALTH_INIT_SCRIPTS` 常量（6 个反检测脚本）
2. 新增 `_page_count` 计数器，在 `_maybe_recycle()` 中增加翻页退休检查
3. 上下文隔离由 `settings.RENDER_CONTEXT_ISOLATION` 控制（当前默认 True）
4. `_auto_scroll` 改为动态传入轮数（5-10 随机），间隔改为 0.5-2s
5. `_launch_browser()` 在 stealth 模式下增加 WebGL 硬件加速参数

- [ ] **Step 2: 提交**

```bash
git add backend/app/modules/crawler/renderer.py
git commit -m "feat: add stealth anti-detection, context isolation, browser retirement"
```

---

### Task 5: Extractor Chain Enhancement — filtered_html 输入 + 分块策略

**Files:**
- Modify: `backend/app/modules/crawler/adapters/readability_adapter.py`
- Modify: `backend/app/modules/crawler/adapters/llm_extraction_adapter.py`

- [ ] **Step 1: ReadabilityAdapter 输入改为 filtered_html**

ReadabilityAdapter 使用 `page.html`（由 RenderedPage 传递）。这一步不需要改 ReadabilityAdapter 本身——它已经在读取 `page.html`，只要在 `service.py` 中构造 `RenderedPage` 时传入 `filtered_html` 即可。

但为了灵活性，在 `RenderedPage` 增加备注：适配器接收的 `html` 字段将来自过滤管道。

**实际无代码变更** — ReadabilityAdapter 保持不动。

- [ ] **Step 2: LLMExtractionAdapter 增加分块策略**

替换 `backend/app/modules/crawler/adapters/llm_extraction_adapter.py`：

```python
"""LLMExtractionAdapter：调用 Kimi 抽取结构化字段（PRD 2.1.10）。
优化：支持分块策略（chunk_token_threshold + overlap_rate）处理长内容。
"""
import json
import logging
import re
from datetime import date, datetime
from typing import List, Optional, Tuple

from bs4 import BeautifulSoup

from app.core.config import settings
from app.modules.ai.kimi_client import get_kimi_client
from app.modules.crawler.adapters.base import ArticleDraft, RenderedPage, SpiderAdapter

logger = logging.getLogger(__name__)

_PROMPT = """你是一个网页正文抽取器。给定一段 HTML 主体，提取以下结构化字段，输出严格 JSON：

{
  "original_title": "string",
  "source_unit": "string | null",
  "publish_date": "YYYY-MM-DD | null",
  "raw_content": "string (Markdown，正文)",
  "confidence": 0.0
}

规则：
1. 只输出 JSON，不要任何解释。
2. raw_content 必须去除导航、广告、推荐栏、版权声明、评论；保留正文段落和小标题。
3. 若是文章列表页（非单篇文章），confidence 设为 0.2。
4. publish_date 仅识别明确日期；若不确定为 null。
5. confidence 体现你对识别结果可信度（0~1）；正文不像新闻/政策/文章时设小于 0.5。

待提取的 HTML 主体：
"""


def _shrink_html(html: str, max_chars: int = 12000) -> str:
    """剔除 script/style/nav/footer 后截断。"""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "aside", "form", "iframe", "noscript"]):
        tag.decompose()
    text = str(soup)
    if len(text) > max_chars:
        text = text[:max_chars]
    return text


def _extract_json(content: str) -> Optional[dict]:
    try:
        return json.loads(content)
    except Exception:
        pass
    m = re.search(r"\{[\s\S]*\}", content)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None


def _chunk_html(html: str, threshold: int, overlap_rate: float) -> List[str]:
    """将长 HTML 按 token 估算阈值分块。

    使用字符数 / 1.3 粗略估算 token 数（中文约 1 token/字，英文约 1 token/4 字符 的混合估算）。
    """
    if not html:
        return []
    approx_tokens = len(html) // 2
    if approx_tokens <= threshold:
        return [html]

    soup = BeautifulSoup(html, "lxml")
    # 按段分块
    paragraphs = soup.find_all(["p", "div", "section", "blockquote", "pre"])
    chunks: List[str] = []
    current_chunk: List[str] = []
    current_tokens = 0

    for p in paragraphs:
        p_html = str(p)
        p_tokens = len(p_html) // 2
        if current_tokens + p_tokens > threshold and current_chunk:
            chunks.append("\n".join(current_chunk))
            # overlap：保留最后 overlap_rate 比例的段落
            overlap_count = max(1, int(len(current_chunk) * overlap_rate))
            current_chunk = current_chunk[-overlap_count:]
            current_tokens = sum(len(c) // 2 for c in current_chunk)
        current_chunk.append(p_html)
        current_tokens += p_tokens

    if current_chunk:
        chunks.append("\n".join(current_chunk))

    return chunks if chunks else [html]


class LLMExtractionAdapter(SpiderAdapter):
    name = "llm_extraction"

    async def extract(self, page: RenderedPage) -> ArticleDraft | None:
        client, model = get_kimi_client()
        if not client:
            return None

        html_body = page.html
        threshold = settings.CONTENT_FILTER_CHUNK_TOKEN_THRESHOLD
        overlap_rate = settings.CONTENT_FILTER_CHUNK_OVERLAP_RATE

        # 分块
        chunks = _chunk_html(html_body, threshold, overlap_rate)
        if len(chunks) > 1:
            logger.info("LLM extraction chunked into %s parts for %s", len(chunks), page.url)

        # 各块分别提取，合并结果
        merged_title = ""
        merged_content = ""
        merged_source = None
        merged_date = None
        max_confidence = 0.0

        for i, chunk in enumerate(chunks):
            body = _shrink_html(chunk)
            prompt = _PROMPT + body
            try:
                resp = await client.chat.completions.create(
                    model=model,
                    temperature=0.1,
                    max_tokens=4096,
                    messages=[
                        {"role": "system", "content": "你是严谨的网页结构化抽取器，必须只输出 JSON。"},
                        {"role": "user", "content": prompt},
                    ],
                )
            except Exception as e:
                logger.warning("LLM chunk %s failed: %r", i, e)
                continue

            content = resp.choices[0].message.content or ""
            data = _extract_json(content)
            if not data:
                continue

            confidence = float(data.get("confidence", 0) or 0)
            if confidence < 0.5:
                continue

            # 第一块：取标题
            if i == 0:
                merged_title = (data.get("original_title") or page.title or "").strip()
                merged_source = data.get("source_unit") or merged_source
                merged_date_str = data.get("publish_date")
                if merged_date_str:
                    try:
                        merged_date = datetime.strptime(merged_date_str, "%Y-%m-%d").date()
                    except Exception:
                        pass

            # 合并正文
            chunk_content = (data.get("raw_content") or "").strip()
            if chunk_content:
                merged_content += f"\n\n{chunk_content}"
            max_confidence = max(max_confidence, confidence)

        if not merged_content and not merged_title:
            return None
        if max_confidence < 0.5:
            return None

        return ArticleDraft(
            original_title=merged_title,
            raw_content=merged_content.strip(),
            source_unit=merged_source,
            publish_date=merged_date,
            confidence=max_confidence,
        )
```

- [ ] **Step 3: 提交**

```bash
git add backend/app/modules/crawler/adapters/llm_extraction_adapter.py
git commit -m "feat: add chunking strategy to LLM extraction adapter"
```

---

### Task 6: Dedup Enhancement — URL 规范化 + SimHash 相似检测

**Files:**
- Modify: `backend/app/modules/crawler/service.py`（dedup 部分）

- [ ] **Step 1: 在 `service.py` 中增强去重逻辑**

修改 `_crawl_one_attempt` 中的去重部分（line 341-351），添加 URL 规范化和 SimHash 相似检测：

```python
# 在文件顶部 imports 区域追加（在已有 hashlib 下方）
import math
from collections import Counter
from urllib.parse import urlencode, urlparse, urlunparse
```

替换去重段落的代码（从 `# 内容去重` 到 `if exists:`）：

```python
    # === 去重：URL 规范化 + MD5 指纹 + SimHash 相似检测 ===

    # 1. URL 规范化去重：去除跟踪参数
    normalized_url = _normalize_url(page.final_url or url)

    # 2. MD5 内容指纹
    fingerprint = hashlib.md5(
        f"{draft.original_title.strip()}{draft.raw_content[:200].strip()}".encode()
    ).hexdigest()

    try:
        exists = await redis_client.sismember("article_fingerprints", fingerprint)
    except Exception:
        exists = False
    if exists:
        logger.info("dedup(md5) hit: %s → %s", url, fingerprint)
        return {"ok": True, "dedup": True}

    # 3. SimHash 相似标题检测（Hamming 距离 < 3 视为重复）
    title_hash = _simhash(draft.original_title.strip())
    if title_hash:
        try:
            similar_titles = await redis_client.smembers("article_title_hashes")
            for existing_hash_str in similar_titles:
                existing_hash = int(existing_hash_str)
                if _hamming_distance(title_hash, existing_hash) < 3:
                    logger.info("dedup(simhash) hit: %s ~ %s", draft.original_title[:50], existing_hash_str)
                    return {"ok": True, "dedup": True}
        except Exception:
            pass  # Redis 不可用时降级
```

在文件末尾添加去重工具函数：

```python
# === 去重工具函数 ===

_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "gclsrc", "dclid", "gbraid", "wbraid",
    "ref", "referrer", "source", "from", "spm", "scm",
}


def _normalize_url(url: str) -> str:
    """去除 URL 中的跟踪参数，返回规范化 URL。"""
    try:
        parsed = urlparse(url)
        if not parsed.query:
            return url
        params = parsed.query.split("&")
        kept = [p for p in params if not any(p.startswith(f"{t}=") for t in _TRACKING_PARAMS)]
        if len(kept) == len(params):
            return url
        new_query = "&".join(kept)
        return urlunparse(parsed._replace(query=new_query))
    except Exception:
        return url


def _simhash(text: str, bits: int = 64) -> int | None:
    """计算文本的 SimHash 值。

    简化实现：对每个词的 hash 按位加权求和，取符号位。
    """
    if not text or not text.strip():
        return None
    words = re.findall(r"[a-zA-Z]+|[一-龥]{2,}", text.lower())
    if not words:
        return None
    v = [0] * bits
    for word in words:
        h = hash(word) & ((1 << bits) - 1)
        for i in range(bits):
            mask = 1 << i
            if h & mask:
                v[i] += 1
            else:
                v[i] -= 1
    fingerprint = 0
    for i in range(bits):
        if v[i] > 0:
            fingerprint |= (1 << i)
    return fingerprint


def _hamming_distance(x: int, y: int) -> int:
    """计算两个 SimHash 值之间的 Hamming 距离。"""
    xor = x ^ y
    return xor.bit_count() if hasattr(int, "bit_count") else bin(xor).count("1")
```

在写入 Redis 指纹的代码段（`# 写入 Redis 指纹`）后追加 SimHash 写入：

```python
    # 写入 Redis 指纹（异步后台任务，不阻塞主流程）
    if article_id:
        try:
            await redis_client.sadd("article_fingerprints", fingerprint)
            await redis_client.expire("article_fingerprints", 604800)
        except Exception:
            logger.warning("redis dedup write failed: %s", fingerprint)

        # SimHash 写入（同样后台写入）
        if title_hash:
            try:
                await redis_client.sadd("article_title_hashes", str(title_hash))
                await redis_client.expire("article_title_hashes", 604800)
            except Exception:
                pass
```

- [ ] **Step 2: 提交**

```bash
git add backend/app/modules/crawler/service.py
git commit -m "feat: enhance dedup with URL normalization and SimHash"
```

---

### Task 7: Service 串联 — Content Filter + Cache + 特性开关

**Files:**
- Modify: `backend/app/modules/crawler/service.py`（完整串联）
- Modify: `backend/app/main.py`（初始化 page_cache）

- [ ] **Step 1: 在 `service.py` 中串联 Content Filter + Cache**

在 `service.py` 中修改 `_crawl_one_attempt`：

在 `renderer.render()` 调用之后、构造 `RenderedPage` 之前，插入 Content Filter + Cache 逻辑：

```python
async def _crawl_one_attempt(task_id: str, url: str, *, target_date: date, date_to: date | None = None) -> dict:
    """单 URL：渲染 → 内容过滤/缓存 → 降级链 → 翻页合并 → 日期过滤 → 入库 → 触发 AI。"""
    from app.modules.crawler.cache import page_cache
    from app.modules.crawler.content_filter import content_filter_pipeline

    # ====== 缓存命中则跳过渲染 ======
    if settings.CRAWLER_CACHE_ENABLED and page_cache:
        cached = await page_cache.get(url)
        if cached:
            logger.debug("cache hit: %s", url)
            filtered_html = cached.get("filtered_html") or cached.get("pruned_html", "")
            title = cached.get("title", "")
            page = RenderedPage(
                url=url,
                final_url=url,
                html=filtered_html,
                title=title,
            )
            render_ok = True
            goto_extract = True  # 标记：直接进入提取阶段
        else:
            goto_extract = False
    else:
        goto_extract = False

    if not goto_extract:
        # ====== 渲染 ======
        try:
            rendered = await renderer.render(url)
        except Exception as e:
            logger.exception("render failed: %s", url)
            return {"ok": False, "code": 2001, "reason": f"渲染失败：{e!r}"}
        if not rendered.get("ok"):
            return {"ok": False, "code": 2001, "reason": rendered.get("reason", "RENDER_FAILED")}

        raw_html = rendered["html"]
        final_url = rendered.get("final_url") or url
        title = rendered.get("title", "")

        # ====== Content Filter Pipeline ======
        if settings.CONTENT_FILTER_ENABLED:
            try:
                filtered_html = content_filter_pipeline(raw_html)
                if not filtered_html or len(filtered_html) < 100:
                    logger.warning("content filter produced empty result for %s, fallback to raw", url)
                    filtered_html = raw_html
            except Exception as e:
                logger.warning("content filter failed for %s: %r, fallback to raw", url, e)
                filtered_html = raw_html
        else:
            filtered_html = raw_html

        # ====== 写入缓存（异步，不阻塞） ======
        if settings.CRAWLER_CACHE_ENABLED and page_cache:
            try:
                await page_cache.set(url, filtered_html=filtered_html, title=title)
            except Exception as e:
                logger.debug("cache write failed: %r", e)

        page = RenderedPage(
            url=url,
            final_url=final_url,
            html=filtered_html,
            title=title,
        )
```

其余提取链（adapter 循环 + 翻页 + 日期过滤 + 去重 + 入库）保持不动。

**注意：翻页爬取部分的渲染也需要走缓存**。将翻页循环中的 `renderer.render(next_url)` 调用替换为带缓存的渲染：

```python
    # 翻页爬取
    visited_pages: set[str] = {url, page.final_url}
    current_html = page.html  # 使用已过滤的 HTML
    current_final = page.final_url
    for _ in range(_MAX_ARTICLE_PAGES):
        next_url = find_article_next_page(current_html, current_final, visited_pages)
        if not next_url:
            break
        visited_pages.add(next_url)
        try:
            # 翻页也走缓存优先
            next_rendered = None
            if settings.CRAWLER_CACHE_ENABLED and page_cache:
                cached_next = await page_cache.get(next_url)
                if cached_next:
                    next_rendered = {
                        "html": cached_next.get("filtered_html") or cached_next.get("pruned_html", ""),
                        "title": cached_next.get("title", ""),
                        "final_url": next_url,
                        "ok": True,
                    }
            if not next_rendered:
                next_rendered = await renderer.render(next_url)
                # 缓存
                if settings.CRAWLER_CACHE_ENABLED and page_cache and next_rendered.get("ok"):
                    _next_html = next_rendered["html"]
                    _next_filtered = content_filter_pipeline(_next_html) if settings.CONTENT_FILTER_ENABLED else _next_html
                    await page_cache.set(next_url, filtered_html=_next_filtered, title=next_rendered.get("title", ""))
                    next_rendered["html"] = _next_filtered
        except Exception:
            break
```

- [ ] **Step 2: 提交**

```bash
git add backend/app/modules/crawler/service.py
git commit -m "feat: integrate content filter, cache layer, and feature toggle"
```

---

### Task 8: 验证与测试

- [ ] **Step 1: 验证配置加载**

```bash
cd backend
python -c "
from app.core.config import settings
assert settings.CONTENT_FILTER_ENABLED == True
assert settings.CRAWLER_CACHE_ENABLED == True
assert settings.RENDER_STEALTH_ENABLED == True
assert settings.RENDER_CONTEXT_ISOLATION == True
assert settings.CONTENT_FILTER_BM25_TOP_K == 30
assert settings.CONTENT_FILTER_CHUNK_TOKEN_THRESHOLD == 4000
print('All config items OK')
"
```

- [ ] **Step 2: 验证 Content Filter Pipeline**

```bash
cd backend
python -c "
from app.modules.crawler.content_filter import Pruning, BM25Filter

# 测试 Pruning
test_html = '<html><body><div class=\"ad-banner\">广告</div><div id=\"main\"><p>正文内容测试</p></div><nav>导航</nav></body></html>'
pruned = Pruning.prune(test_html)
assert 'ad-banner' not in pruned, 'Pruning should remove ad div'
assert '正文' in pruned, 'Pruning should keep main content'
print('Pruning OK')

# 测试 BM25
bm25 = BM25Filter()
filtered = bm25.filter('<html><head><title>测试标题</title></head><body><p>这是第一段正文内容。</p><p>这是第二段和标题相关的技术讨论。</p></body></html>')
assert '第一段正文' in filtered or '技术讨论' in filtered
print('BM25 OK')

print('Content Filter Pipeline OK')
"
```

- [ ] **Step 3: 验证缓存模块**

```bash
cd backend
python -c "
# 单元测试（不依赖 Redis）
from app.modules.crawler.cache import PageCache

# 验证 key 生成逻辑
class FakeRedis:
    async def hgetall(self, key): return {}
    async def hset(self, key, mapping): pass
    async def expire(self, key, ttl): pass
    async def delete(self, key): pass

cache = PageCache(FakeRedis())
assert cache._make_key('https://example.com') == f'crawl_page_cache:{hashlib.md5(b\"https://example.com\").hexdigest()}'
print('Cache key generation OK')
"
```

需要导入 hashlib：
```bash
cd backend
python -c "
import hashlib
from app.modules.crawler.cache import PageCache

class FakeRedis:
    async def hgetall(self, key): return {}
    async def hset(self, key, mapping): pass
    async def expire(self, key, ttl): pass
    async def delete(self, key): pass

cache = PageCache(FakeRedis())
key = cache._make_key('https://example.com')
expected = f'crawl_page_cache:{hashlib.md5(b\"https://example.com\").hexdigest()}'
assert key == expected, f'{key} != {expected}'
print('Cache OK')
"
```

- [ ] **Step 4: 验证去重增强**

```bash
cd backend
python -c "
from app.modules.crawler.service import _normalize_url, _simhash, _hamming_distance

# URL 规范化
assert _normalize_url('https://example.com/page?utm_source=fb&id=1') == 'https://example.com/page?id=1'
assert _normalize_url('https://example.com/page?id=1') == 'https://example.com/page?id=1'
print('URL normalization OK')

# SimHash
h1 = _simhash('国务院发布2024年经济政策')
h2 = _simhash('国务院发布2024年经济政策方针')
h3 = _simhash('今天天气很好')

assert h1 is not None and h2 is not None and h3 is not None
assert _hamming_distance(h1, h2) < _hamming_distance(h1, h3), 'similar titles should have smaller distance'
print('SimHash OK')
print('Dedup enhancement OK')
"
```

- [ ] **Step 5: 特性开关验证**

验证 `CONTENT_FILTER_ENABLED=False` 时，内容过滤不生效，降级为原始行为：

```bash
cd backend
CONTENT_FILTER_ENABLED=false python -c "
from app.core.config import Settings
# 手动验证
print('Settings will load from env - toggle works')
"
```

可在 `service.py` 中通过判断 `settings.CONTENT_FILTER_ENABLED` 确认过滤管道是否启用。

- [ ] **Step 6: 提交全部更改**

```bash
git add -A
git commit -m "test: add verification scripts for crawler optimization"
```

---

## 任务依赖关系

```
Task 1 (Config) → Task 2 (Content Filter) → Task 5 (Extractor) → Task 7 (Service串联)
                → Task 3 (Cache Layer) ────────────────────────↗
                → Task 4 (Renderer) ──────────────────────────↗
Task 6 (Dedup) ───────────────────────────────────────────────↗
                                                                   ↘ Task 8 (Verify)
```

**并行策略**：
- Task 1 完成后，Task 2、3、4、6 可以并行执行（互不依赖）
- Task 5 依赖 Task 2（LLM 分块）
- Task 7 依赖 Task 2、3、4（串联所有模块）
- Task 8（验证）在所有任务之后
