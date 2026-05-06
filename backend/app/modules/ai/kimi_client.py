"""LLM 客户端工厂：从 system_config 读取 AI 提供商配置，fallback 到环境变量。"""
import hashlib
import logging
from typing import Optional

from openai import AsyncOpenAI
from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.system_config import SystemConfig

logger = logging.getLogger(__name__)

# 内存缓存：避免每次调用都查 DB
_cached_hash: Optional[str] = None
_client: Optional[AsyncOpenAI] = None
_model: str = ""
_api_key: str = ""


def _config_hash(api_key: str, base_url: str, model: str) -> str:
    return hashlib.md5(f"{api_key}:{base_url}:{model}".encode()).hexdigest()


async def _load_ai_config() -> dict:
    """从 DB 加载 AI 配置，失败时 fallback 到环境变量。"""
    try:
        async with AsyncSessionLocal() as session:
            row = await session.execute(
                select(SystemConfig).where(SystemConfig.key == "ai_provider")
            )
            cfg = row.scalar_one_or_none()
            if cfg and cfg.value:
                return cfg.value
    except Exception:
        logger.debug("system_config 表不可用，fallback 到环境变量")
    # fallback
    return {
        "provider": "kimi",
        "api_key": settings.MOONSHOT_API_KEY,
        "base_url": settings.MOONSHOT_BASE_URL,
        "model": settings.MOONSHOT_MODEL,
    }


async def get_llm_client() -> tuple[Optional[AsyncOpenAI], str]:
    """返回 (client, model)；未配置 API Key 时 client 为 None。"""
    global _cached_hash, _client, _model, _api_key

    cfg = await _load_ai_config()
    api_key = cfg.get("api_key", "")
    base_url = cfg.get("base_url", settings.MOONSHOT_BASE_URL)
    model = cfg.get("model", settings.MOONSHOT_MODEL)

    h = _config_hash(api_key, base_url, model)
    if h != _cached_hash:
        _client = None
        _cached_hash = h
        _api_key = api_key
        _model = model

    if not api_key:
        return None, model

    if _client is None:
        _client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        _model = model
        logger.info("LLM client 已创建: base_url=%s, model=%s", base_url, model)

    return _client, _model


def clear_llm_cache():
    """清除客户端缓存（配置更新后调用）。"""
    global _cached_hash, _client
    _cached_hash = None
    _client = None


# 平滑过渡：保留旧函数名
get_kimi_client = get_llm_client


async def get_ai_config() -> dict:
    """返回完整 AI 配置 dict（含 provider 字段）。"""
    return await _load_ai_config()


def get_web_search_tools(provider: str) -> list[dict]:
    """根据 provider 返回对应的联网搜索 tools 参数。"""
    p = provider.lower()
    if p in ("kimi", "moonshot", "deepseek"):
        return [{"type": "builtin_function", "function": {"name": "$web_search"}}]
    if p in ("zhipu", "qwen"):
        return [{"type": "builtin_function", "function": {"name": "web_search"}}]
    if p == "openai":
        return [{"type": "function", "function": {
            "name": "web_search",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        }}]
    # 默认 Kimi 风格
    return [{"type": "builtin_function", "function": {"name": "$web_search"}}]
