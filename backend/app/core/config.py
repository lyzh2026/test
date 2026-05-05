"""读取环境变量到 Settings 单例。"""
from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://shixun:shixun@postgres:5432/shixun"
    DATABASE_URL_SYNC: str = "postgresql+psycopg2://shixun:shixun@postgres:5432/shixun"

    # Auth
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin123"
    SESSION_SECRET: str = "please_replace_with_random_64_char_string"
    SESSION_COOKIE_NAME: str = "shixun_session"
    SESSION_MAX_AGE: int = 60 * 60 * 24 * 7  # 7 天

    # AI - Kimi (Moonshot)
    MOONSHOT_API_KEY: str = ""
    MOONSHOT_BASE_URL: str = "https://api.moonshot.cn/v1"
    MOONSHOT_MODEL: str = "moonshot-v1-32k"

    # 白名单 seed（仅在 allowed_domains 表为空时生效）
    ALLOWED_DOMAINS: str = ""

    # Crawler
    RENDER_POOL_SIZE: int = 3              # PRD 单 worker 上限 3
    RENDER_TIMEOUT_MS: int = 30000         # 单页面渲染硬上限 30s
    RENDER_SOFT_MEM_MB: int = 1024         # 软阈值 1.0 GB
    RENDER_HARD_MEM_MB: int = 1536         # 硬阈值 1.5 GB
    RENDER_IDLE_RECYCLE_SEC: int = 300     # 空闲 5 分钟回收
    CRAWLER_DOMAIN_CONCURRENCY: int = 2    # 单域名并发
    CRAWLER_DOMAIN_DELAY_MIN: float = 3.0   # 同域名请求最小间隔（秒）
    CRAWLER_DOMAIN_DELAY_MAX: float = 6.0   # 同域名请求最大间隔（抖动用，秒）
    CRAWLER_MAX_URLS_PER_TASK: int = 100   # PRD 单任务上限
    CRAWLER_MAX_RETRIES: int = 3            # 单 URL 最大重试次数
    CRAWLER_RETRY_BACKOFF_BASE: int = 2     # 退避基数（秒）

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

    # Redis
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379

    # Proxy Pool
    PROXY_ENABLED: bool = False
    PROXY_LIST: str = ""
    PROXY_MAX_CONSECUTIVE_FAILS: int = 3

    # AI 状态机超时
    AI_ANALYZING_TIMEOUT_SEC: int = 300    # 5 分钟超时

    @property
    def allowed_domains_list(self) -> List[str]:
        return [d.strip() for d in self.ALLOWED_DOMAINS.split(",") if d.strip()]

    @property
    def proxy_list_parsed(self) -> List[str]:
        return [p.strip() for p in self.PROXY_LIST.split(",") if p.strip()]


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
