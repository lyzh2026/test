"""Kimi (Moonshot) AsyncOpenAI 客户端封装。"""
from openai import AsyncOpenAI

from app.core.config import settings

_client: AsyncOpenAI | None = None


def get_kimi_client() -> tuple[AsyncOpenAI | None, str]:
    """返回 (client, model)；未配置 API Key 时 client 为 None。"""
    global _client
    if not settings.MOONSHOT_API_KEY:
        return None, settings.MOONSHOT_MODEL
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.MOONSHOT_API_KEY,
            base_url=settings.MOONSHOT_BASE_URL,
        )
    return _client, settings.MOONSHOT_MODEL
