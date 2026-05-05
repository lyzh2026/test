"""pytest 公共配置：mock 所有外部依赖（DB、Redis、Playwright、网络请求）。"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def mock_redis():
    """全局 mock Redis 客户端，避免依赖实际 Redis 实例。"""
    mock_redis = AsyncMock()
    mock_redis.sismember = AsyncMock(return_value=False)
    mock_redis.sadd = AsyncMock()
    mock_redis.expire = AsyncMock()
    mock_redis.smembers = AsyncMock(return_value=set())
    mock_redis.exists = AsyncMock(return_value=False)
    mock_redis.setex = AsyncMock()
    mock_redis.ttl = AsyncMock(return_value=-1)
    with patch("app.core.redis.redis", mock_redis):
        yield mock_redis


@pytest.fixture(autouse=True)
def mock_settings():
    """确保 settings 有测试用的默认值。"""
    with patch("app.core.config.settings") as mock:
        mock.CRAWLER_DOMAIN_CONCURRENCY = 2
        mock.CRAWLER_DOMAIN_DELAY_MIN = 0.01   # 测试用最小值，避免等待
        mock.CRAWLER_DOMAIN_DELAY_MAX = 0.05
        mock.CRAWLER_MAX_RETRIES = 1
        mock.RENDER_POOL_SIZE = 2
        mock.RENDER_TIMEOUT_MS = 30000
        mock.RENDER_SOFT_MEM_MB = 1024
        mock.RENDER_HARD_MEM_MB = 1536
        mock.RENDER_BROWSER_RETIRE_AFTER = 30
        mock.RENDER_STEALTH_ENABLED = True
        mock.RENDER_CONTEXT_ISOLATION = True
        mock.CONTENT_FILTER_ENABLED = True
        mock.CRAWLER_CACHE_ENABLED = False
        mock.PROXY_ENABLED = False
        yield mock


@pytest.fixture(autouse=True)
def mock_database():
    """mock AsyncSessionLocal，测试中不应发起真实 DB 查询。"""
    with patch("app.core.database.AsyncSessionLocal") as mock:
        yield mock


@pytest.fixture(autouse=True)
def mock_playwright():
    """mock Playwright 渲染器，测试中不启动真实浏览器。"""
    try:
        import app.modules.crawler.renderer  # noqa: F401
        target = "app.modules.crawler.renderer.renderer.render"
    except (ImportError, ModuleNotFoundError):
        yield AsyncMock()
        return
    with patch(target, new_callable=AsyncMock) as mock:
        mock.return_value = {
            "ok": True,
            "html": "<html><body><article><h1>Test Title</h1><p>Content</p></article></body></html>",
            "title": "Test Title",
            "final_url": "https://example.com/page",
        }
        yield mock


@pytest.fixture(autouse=True)
def mock_scheduler():
    """mock APScheduler，避免异步任务调度。"""
    try:
        import app.core.scheduler  # noqa: F401
        target = "app.core.scheduler.scheduler.add_job"
    except (ImportError, ModuleNotFoundError):
        yield MagicMock()
        return
    with patch(target) as mock:
        yield mock
