"""AI Browser 兜底（渲染链第 ④ 层）与渲染路由策略读取。

browser-use 依赖重且要求 Python >=3.11，因此**只在真正调用时懒加载**：
未安装时 browse_with_ai 返回失败原因，兜底功能整体失效，其余链路不受影响。
"""
import logging
from urllib.parse import urlparse

from sqlalchemy import select

logger = logging.getLogger(__name__)

AI_BROWSER_ENABLED_KEY = "ai_browser_enabled"
AI_PROVIDER_KEY = "ai_provider"

MODE_AUTO = "auto"
MODE_ALWAYS_AIBROWSER = "always_aibrowser"
MODE_ALWAYS_STATIC = "always_static"

VALID_MODES = (MODE_AUTO, MODE_ALWAYS_AIBROWSER, MODE_ALWAYS_STATIC)

_AIBROWSER_PROMPT = """打开这个页面并提取文章正文：{url}

要求：
1. 只输出一个 JSON 对象，不要任何解释、不要 markdown 代码围栏。
2. 字段：original_title（页面标题）、raw_content（完整正文纯文本，保留段落换行）、
   source（发布单位，找不到填空字符串）、date_str（发布日期 YYYY-MM-DD，找不到填空字符串）。
3. raw_content 必须是正文，去掉导航、页脚、广告、相关推荐。
4. 如果无法访问或没有正文，输出 {{"original_title": "", "raw_content": "", "error": "原因"}}。
"""


def domain_of(url: str) -> str:
    """取小写主机名（不含端口）；解析失败返回空串。"""
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def should_direct_connect(url: str, policy: dict[str, str], enabled: bool) -> bool:
    """白名单直连：开关开启且域名 mode=always_aibrowser 时跳过前三层直走兜底层。"""
    if not enabled:
        return False
    return policy.get(domain_of(url)) == MODE_ALWAYS_AIBROWSER


async def is_ai_browser_enabled(session) -> bool:
    """读 system_config.ai_browser_enabled。缺失或读失败一律返回 False（默认关闭）。"""
    from app.models.system_config import SystemConfig

    try:
        res = await session.execute(
            select(SystemConfig).where(SystemConfig.key == AI_BROWSER_ENABLED_KEY)
        )
        cfg = res.scalar_one_or_none()
    except Exception:
        logger.warning("read ai_browser_enabled failed, assuming disabled", exc_info=True)
        return False
    if not cfg or not isinstance(cfg.value, dict):
        return False
    return bool(cfg.value.get("enabled", False))


async def load_route_policy(session) -> dict[str, str]:
    """加载 enabled 的路由策略，返回 {小写域名: mode}。读失败返回空表（全部走常规三层）。"""
    from app.models.routing import RenderRoutePolicy

    try:
        res = await session.execute(
            select(RenderRoutePolicy).where(RenderRoutePolicy.enabled.is_(True))
        )
        return {r.domain.lower(): r.mode for r in res.scalars().all()}
    except Exception:
        logger.warning("load render route policy failed, assuming empty", exc_info=True)
        return {}


async def load_ai_browser_config() -> dict:
    """读 AI 提供商配置（system_config.ai_provider），browser-use 与现有链路口径一致。"""
    from app.core.database import AsyncSessionLocal
    from app.models.system_config import SystemConfig

    cfg = {"api_key": "", "base_url": "", "model": ""}
    try:
        async with AsyncSessionLocal() as session:
            res = await session.execute(
                select(SystemConfig).where(SystemConfig.key == AI_PROVIDER_KEY)
            )
            row = res.scalar_one_or_none()
            if row and isinstance(row.value, dict):
                cfg["api_key"] = row.value.get("api_key", "") or ""
                cfg["base_url"] = row.value.get("base_url", "") or ""
                cfg["model"] = row.value.get("model", "") or ""
    except Exception:
        logger.warning("read ai_provider failed for ai browser", exc_info=True)
    return cfg


async def browse_with_ai(url: str, *, api_key: str, base_url: str, model: str) -> dict:
    """用 browser-use 打开页面并提取正文。

    返回 {"ok": bool, "title": str, "content": str, "source": str, "date_str": str, "reason": str}。
    任何异常都在此收敛为 ok=False，绝不向上抛。
    """
    from app.modules.crawler.service import _extract_json_simple

    if not api_key or not model:
        return {"ok": False, "reason": "AI 未配置 api_key/model"}

    try:
        from browser_use import Agent
        from browser_use import ChatOpenAI
    except ImportError as e:
        return {"ok": False, "reason": f"browser-use 不可用：{e!r}"}

    try:
        llm = ChatOpenAI(model=model, api_key=api_key, base_url=base_url or None)
        agent = Agent(task=_AIBROWSER_PROMPT.format(url=url), llm=llm)
        history = await agent.run()
        text = history.final_result() if hasattr(history, "final_result") else str(history)
    except Exception as e:
        logger.warning("ai browser run failed: %s (%r)", url, e)
        return {"ok": False, "reason": f"AI Browser 执行失败：{e!r}"}

    data = _extract_json_simple(text or "")
    if not isinstance(data, dict):
        return {"ok": False, "reason": "AI Browser 输出无法解析为 JSON"}

    content = (data.get("raw_content") or "").strip()
    if len(content) < 100:
        return {"ok": False, "reason": data.get("error") or "AI Browser 未取回有效正文"}

    return {
        "ok": True,
        "title": (data.get("original_title") or "").strip(),
        "content": content,
        "source": (data.get("source") or "").strip() or None,
        "date_str": (data.get("date_str") or "").strip() or None,
        "reason": "",
    }
