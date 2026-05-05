"""Redis 客户端单例。"""
from redis.asyncio import Redis

from app.core.config import settings

redis: Redis = Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    decode_responses=True,
    socket_connect_timeout=3,
)
