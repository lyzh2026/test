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
import logging
import time
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

PAGE_CACHE_PREFIX = "crawl_page_cache:"


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
