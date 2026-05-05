"""爬虫任务编排：提交任务、URL 校验、降级链、入库、后续 AI 触发。"""
import asyncio
import hashlib
import logging
import re
from datetime import date, datetime, timezone
from urllib.parse import urlparse, urlunparse

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.redis import redis as redis_client
from app.core.database import AsyncSessionLocal
from apscheduler.triggers.date import DateTrigger
from app.core.scheduler import scheduler
from app.models.allowed_domain import AllowedDomain
from app.models.article import Article
from app.models.crawler_task import CrawlerTask
from app.modules.crawler.adapters.base import RenderedPage, SpiderAdapter
from app.modules.crawler.adapters.llm_extraction_adapter import LLMExtractionAdapter
from app.modules.crawler.adapters.readability_adapter import ReadabilityAdapter, _has_date_hints, _has_publish_date_hints, _html_to_plaintext
from app.modules.crawler.pagination import find_article_next_page
from app.modules.crawler.progress_bus import ProgressEvent, progress_bus
from app.modules.crawler.rate_limiter import domain_rate_limiter
from app.modules.crawler.renderer import renderer
from app.modules.discovery.service import discover_articles
from app.utils.url_validator import AllowedRule, URLValidationError, validate_url

logger = logging.getLogger(__name__)

_ADAPTERS: list[SpiderAdapter] = [ReadabilityAdapter(), LLMExtractionAdapter()]
_MAX_ARTICLE_PAGES: int = 5

# 任务取消集合
_cancelled_tasks: set[str] = set()

# 自动重试配置
_RETRYABLE_CODE_PREFIXES = (2001, 5001)
_RETRYABLE_KEYWORDS = [
    "timeout", "reset", "refused", "econnrefused", "econnreset",
    "eof", "protocol error", "net::err_", "connection closed",
]

# Blocking types that are retryable (except captcha which requires human intervention)
_RETRYABLE_BLOCK_TYPES = {"cloudflare", "ratelimit", "generic"}

# Per-domain block counters for adaptive delay
_domain_block_counts: dict[str, int] = {}


def _is_retryable(result: dict) -> bool:
    """判断错误是否可重试（网络类临时错误、非验证码拦截可重试，适配器/白名单类不可）。"""
    code = result.get("code", 0)
    if code in _RETRYABLE_CODE_PREFIXES:
        return True
    reason = (result.get("reason") or "").lower()
    # Blocking detection results are retryable (except captcha)
    if reason.startswith("blocked:"):
        block_type = reason.replace("blocked:", "").strip()
        return block_type in _RETRYABLE_BLOCK_TYPES
    for kw in _RETRYABLE_KEYWORDS:
        if kw in reason:
            return True
    return False


async def cancel_task(task_id: str) -> bool:
    """标记任务为取消，移除调度 job。"""
    _cancelled_tasks.add(task_id)
    try:
        scheduler.remove_job(f"crawl:{task_id}")
    except Exception:
        pass  # job 可能已不在调度器中
    async with AsyncSessionLocal() as session:
        t = await session.get(CrawlerTask, task_id)
        if t and t.status in ("running", "pending"):
            t.status = "cancelled"
            t.completed_at = datetime.now(timezone.utc)
            await session.commit()
            logger.info("task cancelled: %s", task_id)
            progress_bus.emit(ProgressEvent(
                task_id=task_id, status="cancelled",
                message="任务已取消",
            ))
            return True
    return False


async def _load_rules(session: AsyncSession) -> list[AllowedRule]:
    res = await session.execute(
        select(AllowedDomain).where(AllowedDomain.deleted_at.is_(None), AllowedDomain.enabled.is_(True))
    )
    rules = []
    for row in res.scalars().all():
        rules.append(AllowedRule(domain_pattern=row.domain_pattern, match_mode=row.match_mode))
    return rules


async def submit_task(
    *,
    session: AsyncSession,
    url_list: list[str],
    target_date: date,
    date_to: date | None = None,
    task_name: str | None,
    callback_url: str | None,
    priority: int,
) -> CrawlerTask:
    """前端提交：URL 校验 → 创建 task（立即可见）→ 后台 discovery + crawl。"""
    if len(url_list) > settings.CRAWLER_MAX_URLS_PER_TASK:
        raise URLValidationError(1001, f"单任务入口 URL 数量不能超过 {settings.CRAWLER_MAX_URLS_PER_TASK}")

    rules = await _load_rules(session)
    entry_urls: list[str] = []
    failed_details: list[dict] = []
    for raw in url_list:
        u = (raw or "").strip()
        if not u or u in entry_urls:
            continue
        try:
            await validate_url(u, rules)
            entry_urls.append(u)
        except URLValidationError as e:
            # 白名单未命中 → 自动加白后重试
            if e.code == 1004:
                hostname = urlparse(u).hostname
                if hostname:
                    entry = AllowedDomain(
                        domain_pattern=hostname,
                        match_mode="suffix",
                        enabled=True,
                        auto_added=True,
                        source="auto",
                    )
                    session.add(entry)
                    await session.flush()
                    rules = await _load_rules(session)
                    try:
                        await validate_url(u, rules)
                        entry_urls.append(u)
                        continue
                    except URLValidationError:
                        pass
            failed_details.append({"url": u, "code": e.code, "reason": e.message, "stage": "validate"})

    # 先创建任务（仅 entry URLs），POST 立即返回，前端立即可见
    task = CrawlerTask(
        task_name=task_name,
        target_date=target_date,
        date_to=date_to,
        url_list=list(entry_urls),
        total_urls=0,
        completed_urls=0,
        failed_urls=len(failed_details),
        failed_details=failed_details,
        status="pending",
        callback_url=callback_url,
        priority=priority,
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)

    if entry_urls:
        scheduler.add_job(
            _run_discovery_and_crawl,
            id=f"discover:{task.id}",
            args=[task.id, entry_urls, target_date, date_to],
            trigger=DateTrigger(),
            replace_existing=True,
        )
    else:
        task.status = "failed"
        task.completed_at = datetime.now(timezone.utc)
        await session.commit()

    return task


async def _run_discovery_and_crawl(
    task_id: str,
    entry_urls: list[str],
    target_date: date,
    date_to: date | None,
):
    """后台：域名发现 → URL 校验 → 更新 task → 启动 crawl。"""
    logger.info("discovery start: task=%s entries=%s", task_id, len(entry_urls))

    async with AsyncSessionLocal() as session:
        rules = await _load_rules(session)

    discovered: set[str] = set()
    failed_details: list[dict] = []

    async def _discover_one(entry: str):
        try:
            links = await discover_articles(
                entry_url=entry,
                max_depth=2,
                max_links=50,
                enable_pagination=True,
                max_pages=5,
            )
            return entry, links, None
        except Exception as e:
            logger.warning("discovery failed for %s: %r", entry, e)
            return entry, [], e

    disc_results = await asyncio.gather(*[_discover_one(e) for e in entry_urls])
    for entry, links, error in disc_results:
        if error:
            failed_details.append({"url": entry, "code": 5001, "reason": f"域名发现失败: {error!r}", "stage": "discovery"})
        else:
            for item in links:
                discovered.add(item["url"])

    # 入口 URL 本身也可能是文章，一并加入
    for entry in entry_urls:
        discovered.add(entry)

    # 校验所有发现到的链接
    valid_urls: list[str] = []
    for u in sorted(discovered):
        try:
            await validate_url(u, rules)
            valid_urls.append(u)
        except URLValidationError as e:
            failed_details.append({"url": u, "code": e.code, "reason": e.message, "stage": "validate"})

    # 限制爬取总数
    if len(valid_urls) > settings.CRAWLER_MAX_URLS_PER_TASK:
        valid_urls = valid_urls[: settings.CRAWLER_MAX_URLS_PER_TASK]

    async with AsyncSessionLocal() as session:
        t = await session.get(CrawlerTask, task_id)
        if not t:
            logger.warning("discovery: task %s not found", task_id)
            return
        t.url_list = valid_urls
        t.total_urls = len(valid_urls)
        t.failed_details = failed_details
        t.failed_urls = len(failed_details)
        t.status = "pending" if valid_urls else ("failed" if failed_details else "pending")
        if not valid_urls:
            t.completed_at = datetime.now(timezone.utc)
        await session.commit()

    if valid_urls:
        scheduler.add_job(
            run_crawl_job,
            id=f"crawl:{task_id}",
            args=[task_id, valid_urls],
            trigger=DateTrigger(),
            replace_existing=True,
        )


async def run_crawl_job(task_id: str, urls: list[str]):
    """APScheduler 入口：单任务整体执行，每完成一个 URL 推送进度事件。"""
    logger.info("crawl job start: task=%s urls=%s", task_id, len(urls))
    async with AsyncSessionLocal() as session:
        task = await session.get(CrawlerTask, task_id)
        if not task:
            logger.warning("crawl job: task %s not found", task_id)
            return
        task.status = "running"
        task.started_at = datetime.now(timezone.utc)
        await session.commit()

    total = len(urls)
    progress_bus.emit(ProgressEvent(
        task_id=task_id, status="running", total=total,
        message=f"开始抓取 {total} 个 URL",
    ))

    completed = 0
    failed = 0

    async def _one(url: str):
        nonlocal completed, failed
        if task_id in _cancelled_tasks:
            return None
        progress_bus.emit(ProgressEvent(
            task_id=task_id, status="running",
            completed=completed, failed=failed, total=total,
            current_url=url,
        ))
        await domain_rate_limiter.acquire(url)
        try:
            res = await _crawl_one(task_id, url, target_date=task.target_date, date_to=task.date_to)
        finally:
            await domain_rate_limiter.release(url)
        if isinstance(res, Exception):
            failed += 1
        elif isinstance(res, dict) and res.get("ok"):
            completed += 1
        elif isinstance(res, dict) and (res.get("dedup") or res.get("filtered")):
            completed += 1
        else:
            failed += 1
        progress_bus.emit(ProgressEvent(
            task_id=task_id, status="running",
            completed=completed, failed=failed, total=total,
            message="完成" if not isinstance(res, Exception) and isinstance(res, dict) and res.get("ok") else "失败",
        ))
        return res

    try:
        results = await asyncio.wait_for(
            asyncio.gather(*[_one(u) for u in urls], return_exceptions=True),
            timeout=max(1800, len(urls) * 60),  # 全局超时：至少 30min 或每 URL 1min
        )
    except asyncio.TimeoutError:
        logger.warning("crawl job timeout: task=%s", task_id)
        results = [{"ok": False, "code": 5001, "reason": "任务全局超时", "stage": "timeout"}] * len(urls)

    async with AsyncSessionLocal() as session:
        t = await session.get(CrawlerTask, task_id)
        if not t:
            return
        details: list = list(t.failed_details or [])
        for url, res in zip(urls, results):
            if isinstance(res, (Exception, BaseException)):
                details.append({"url": url, "code": 5001, "reason": f"内部异常：{res!r}", "stage": "render"})
            elif isinstance(res, dict) and not res.get("ok") and not res.get("dedup") and not res.get("filtered"):
                details.append({"url": url, "code": res.get("code", 2001), "reason": res.get("reason", "未知错误"), "stage": res.get("stage", "")})
        t.completed_urls = completed
        t.failed_urls = len(details)
        t.failed_details = details
        t.completed_at = datetime.now(timezone.utc)
        if task_id in _cancelled_tasks:
            t.status = "cancelled"
            _cancelled_tasks.discard(task_id)
        elif failed == 0:
            t.status = "completed"
        elif completed == 0:
            t.status = "failed"
        else:
            t.status = "partial_failed"
        await session.commit()

    progress_bus.emit(ProgressEvent(
        task_id=task_id, status=t.status,
        completed=completed, failed=failed, total=total,
        message=f"任务{t.status}",
    ))
    logger.info("crawl job end: task=%s status=%s", task_id, t.status)


async def _crawl_one(task_id: str, url: str, *, target_date: date, date_to: date | None = None) -> dict:
    """带自动重试的外层入口：最多重试 CRAWLER_MAX_RETRIES 次，指数退避+拦截应对。"""
    domain = urlparse(url).hostname or "unknown"
    for attempt in range(1, settings.CRAWLER_MAX_RETRIES + 1):
        if task_id in _cancelled_tasks:
            return {"ok": False, "code": 5001, "reason": "任务已取消", "stage": "cancelled"}
        result = await _crawl_one_attempt(task_id, url, target_date=target_date, date_to=date_to)
        ok = result.get("ok", False)
        dedup = result.get("dedup", False)
        filtered = result.get("filtered", False)
        if ok or dedup or filtered:
            return result
        if attempt == settings.CRAWLER_MAX_RETRIES or not _is_retryable(result):
            return result
        reason = (result.get("reason") or "").lower()
        base_wait = settings.CRAWLER_RETRY_BACKOFF_BASE ** attempt
        extra_wait = 0.0
        # Anti-detection counter-measures
        if reason.startswith("blocked:"):
            block_type = reason.replace("blocked:", "").strip()
            _domain_block_counts[domain] = _domain_block_counts.get(domain, 0) + 1
            if block_type == "cloudflare":
                # Cloudflare: recycle browser + longer wait + proxy already rotated by renderer
                extra_wait = random.uniform(5.0, 15.0)
                try:
                    await renderer._maybe_recycle()
                    logger.info("anti-detection: recycled browser for cloudflare block on %s", url)
                except Exception:
                    pass
            elif block_type == "ratelimit":
                # Rate limit: increase domain delay + longer wait
                extra_wait = 5.0 + _domain_block_counts.get(domain, 0) * 3.0
                logger.info("anti-detection: increased delay for ratelimit on %s (domain_blocks=%s)", url, _domain_block_counts.get(domain, 0))
            elif block_type == "generic":
                extra_wait = random.uniform(2.0, 5.0)
        wait = base_wait + extra_wait
        logger.info("retry %s/%s for %s (code=%s, reason=%s) in %.1fs", attempt, settings.CRAWLER_MAX_RETRIES, url, result.get("code"), result.get("reason"), wait)
        await asyncio.sleep(wait)
    return {"ok": False, "code": 5001, "reason": "重试次数耗尽", "stage": "render"}


def _dual_filter_pipeline(html: str) -> str:
    """双管道取长：BM25 管道 vs Pruning 直通，取长策略。

    对多段落文章，BM25 的"最长连续高分区"可能截断严重（132 块→3 块）；
    Pruning 直通可保留 93% 内容。取长后由 ReadabilityAdapter 做第二道防线。
    """
    from app.modules.crawler.content_filter import content_filter_pipeline, Pruning

    # BM25 管道
    try:
        bm25_result = content_filter_pipeline(html)
    except Exception:
        bm25_result = ""

    # Pruning 直通（跳过 BM25）
    try:
        pruned_result = Pruning.prune(html)
    except Exception:
        pruned_result = ""

    # 有效性检查
    bm25_ok = bm25_result and len(bm25_result) >= 100
    prune_ok = pruned_result and len(pruned_result) >= 100

    if not bm25_ok and not prune_ok:
        return html
    if not bm25_ok:
        return pruned_result
    if not prune_ok:
        return bm25_result

    # 取长：如果 Pruning 结果 >= BM25 结果的 80%，选 Pruning（更完整）
    if len(pruned_result) >= len(bm25_result) * 0.8:
        return pruned_result
    return bm25_result


async def _crawl_one_attempt(task_id: str, url: str, *, target_date: date, date_to: date | None = None) -> dict:
    """单 URL：渲染 → 内容过滤/缓存 → 降级链 → 翻页合并 → 日期过滤 → 入库 → 触发 AI。"""
    from app.modules.crawler.cache import page_cache
    from app.modules.crawler.content_filter import content_filter_pipeline

    # ====== 缓存命中则跳过渲染 ======
    goto_extract = False
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
            goto_extract = True

    if not goto_extract:
        # ====== 渲染 ======
        try:
            rendered = await renderer.render(url)
        except Exception as e:
            logger.exception("render failed: %s", url)
            return {"ok": False, "code": 2001, "reason": f"渲染失败：{e!r}", "stage": "render"}
        if not rendered.get("ok"):
            return {"ok": False, "code": 2001, "reason": rendered.get("reason", "RENDER_FAILED"), "stage": "render"}

        raw_html = rendered["html"]
        final_url = rendered.get("final_url") or url
        title = rendered.get("title", "")

        # ====== Content Filter Pipeline (dual) ======
        if settings.CONTENT_FILTER_ENABLED:
            try:
                filtered_html = await asyncio.to_thread(_dual_filter_pipeline, raw_html)
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

    draft = None
    last_reason = "ALL_ADAPTERS_FAILED"
    for adapter in _ADAPTERS:
        # Readability 失败且页面无日期线索 → 跳过 LLM（避免静态页浪费 API 调用）
        if adapter.name == "llm_extraction" and not _has_publish_date_hints(_html_to_plaintext(page.html)[:5000]):
            last_reason = "llm_skipped_no_date_hints"
            break
        try:
            d = await adapter.extract(page)
            if adapter.validate(d):
                draft = d
                break
            else:
                last_reason = f"{adapter.name}: validate failed"
        except Exception as e:
            logger.warning("adapter %s failed for %s: %r", adapter.name, url, e)
            last_reason = f"{adapter.name}: {e!r}"
    if not draft:
        return {"ok": True, "filtered": True, "code": 2002, "reason": last_reason, "stage": "extract"}

    # 日期过滤：页面有明确日期且在时间段外时跳过
    date_to_val = date_to or target_date
    if draft.publish_date and not (target_date <= draft.publish_date <= date_to_val):
        logger.info("date filter: skip %s (publish=%s, range=%s~%s)", url, draft.publish_date, target_date, date_to_val)
        return {"ok": True, "filtered": True, "stage": "date_filter"}

    # 翻页爬取：检测文章"下一页"，循环渲染并合并内容
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
                    _next_filtered = (await asyncio.to_thread(_dual_filter_pipeline, _next_html)) if settings.CONTENT_FILTER_ENABLED else _next_html
                    await page_cache.set(next_url, filtered_html=_next_filtered, title=next_rendered.get("title", ""))
                    next_rendered["html"] = _next_filtered
        except Exception:
            break
        if not next_rendered.get("ok"):
            break
        current_html = next_rendered["html"]
        current_final = next_rendered.get("final_url") or next_url
        # 用 adapter 提取后续页内容，只合并正文
        next_page = RenderedPage(url=next_url, final_url=current_final, html=current_html)
        for adapter in _ADAPTERS:
            try:
                next_draft = await adapter.extract(next_page)
                if adapter.validate(next_draft):
                    draft.raw_content += f"\n\n{next_draft.raw_content}"
                    # 合并翻页的图片/附件
                    if next_draft.extra.get("images"):
                        draft.extra.setdefault("images", []).extend(next_draft.extra["images"])
                    if next_draft.extra.get("attachments"):
                        draft.extra.setdefault("attachments", []).extend(next_draft.extra["attachments"])
                    break
            except Exception:
                continue

    # === 去重：URL 规范化 + MD5 指纹 + SimHash 相似检测 ===

    # 1. URL 规范化去重：去除跟踪参数（用于 original_link 入库）

    # 2. MD5 内容指纹
    fingerprint = hashlib.md5(
        f"{draft.original_title.strip()}{draft.raw_content[:200].strip()}".encode()
    ).hexdigest()

    try:
        exists = await redis_client.exists(f"af:{fingerprint}")
    except Exception:
        exists = False
    if exists:
        logger.info("dedup(md5) hit: %s → %s", url, fingerprint)
        return {"ok": True, "dedup": True, "stage": "dedup"}

    # 3. SimHash 相似标题检测（Hamming 距离 < 3 视为重复）
    title_hash = _simhash(draft.original_title.strip())
    if title_hash:
        try:
            similar_titles = await redis_client.srandmember("article_title_hashes", 100) or []
            for existing_hash_str in similar_titles:
                existing_hash = int(existing_hash_str)
                if _hamming_distance(title_hash, existing_hash) < 3:
                    logger.info("dedup(simhash) hit: %s ~ %s", draft.original_title[:50], existing_hash_str)
                    return {"ok": True, "dedup": True, "stage": "dedup"}
        except Exception:
            pass  # Redis 不可用时降级

    article_id: str | None = None
    async with AsyncSessionLocal() as session:
        # original_link 存入时已去除 tracking 参数，提高 http/https 变体间的去重率
        original_link = _normalize_url(page.final_url or url)

        # 先查后插：消除绝大多数因并发的 IntegrityError
        existing = await session.execute(
            select(Article).where(Article.original_link == original_link)
        )
        row = existing.scalar_one_or_none()
        if row:
            article_id = row.id
        else:
            article = Article(
                task_id=task_id,
                original_title=draft.original_title[:512],
                source_unit=(draft.source_unit or None),
                original_link=original_link,
                publish_date=draft.publish_date or target_date,
                raw_content=draft.raw_content,
                status="raw",
            )
            session.add(article)
            try:
                await session.commit()
                await session.refresh(article)
                article_id = article.id
            except IntegrityError as exc:
                await session.rollback()
                # 竞态：查和插之间另一协程插入了同 original_link 的记录
                existing = await session.execute(
                    select(Article).where(Article.original_link == original_link)
                )
                row = existing.scalar_one_or_none()
                if row:
                    article_id = row.id
                else:
                    logger.warning("IntegrityError but article not found: original_link=%s url=%s detail=%s", original_link, url, exc.orig)
                    return {"ok": False, "code": 5001, "reason": "DB 唯一约束冲突且无法定位文章", "stage": "validate"}

    # 写入 Redis 指纹（异步后台任务，不阻塞主流程）
    if article_id:
        try:
            await redis_client.setex(f"af:{fingerprint}", 604800, "1")
        except Exception:
            logger.warning("redis dedup write failed: %s", fingerprint)

        # SimHash 写入（同样后台写入）
        if title_hash:
            try:
                await redis_client.sadd("article_title_hashes", str(title_hash))
                remaining = await redis_client.ttl("article_title_hashes")
                if remaining == -1:  # 无过期时间（新 key 或 TTL 已过期）
                    await redis_client.expire("article_title_hashes", 604800)
            except Exception:
                pass

    if article_id:
        try:
            scheduler.add_job(
                _ai_analyze_dispatch,
                id=f"ai_analyze:{article_id}",
                args=[article_id],
                trigger=DateTrigger(),
                replace_existing=True,
            )
        except Exception as e:
            logger.warning("schedule ai_analyze failed: %r", e)

    return {"ok": True, "article_id": article_id}


async def _ai_analyze_dispatch(article_id: str):
    """延迟导入避免 ai 模块循环依赖。"""
    from app.modules.ai.service import analyze_article
    await analyze_article(article_id)


async def retry_failed_urls(task_id: str, session: AsyncSession) -> CrawlerTask | None:
    """读取原任务 failed_details，保留已有进度，只重试失败 URL。"""
    task = await session.get(CrawlerTask, task_id)
    if not task:
        return None
    if task.status not in ("partial_failed", "failed"):
        logger.warning("retry skipped: task %s status=%s (require partial_failed|failed)", task_id, task.status)
        return None

    failed_urls_list = [d["url"] for d in (task.failed_details or []) if d.get("url")]
    if not failed_urls_list:
        return None

    # 清零失败计数器，保留 completed_urls
    task.failed_urls = 0
    task.failed_details = []
    task.status = "running"
    task.started_at = datetime.now(timezone.utc)
    task.completed_at = None
    await session.commit()

    scheduler.add_job(
        run_crawl_job,
        id=f"crawl:{task.id}",
        args=[task.id, failed_urls_list],
        trigger=DateTrigger(),
        replace_existing=True,
    )

    logger.info("retry task=%s: %s urls", task_id, len(failed_urls_list))
    return task


async def delete_task(task_id: str) -> bool:
    """取消任务，解绑关联文章，并从数据库删除 CrawlerTask 记录。"""
    await cancel_task(task_id)
    async with AsyncSessionLocal() as session:
        t = await session.get(CrawlerTask, task_id)
        if not t:
            return False
        # 先解绑文章的外键关联，再删除任务记录
        from sqlalchemy import update
        await session.execute(
            update(Article).where(Article.task_id == t.id).values(task_id=None)
        )
        await session.delete(t)
        await session.commit()
        logger.info("task deleted: %s", task_id)
        return True


async def batch_delete_tasks(task_ids: list[str]) -> dict:
    """批量删除任务：遍历每个 ID，取消→删除，不存在的 ID 忽略。"""
    deleted = 0
    skipped = 0
    for tid in task_ids:
        ok = await delete_task(tid)
        if ok:
            deleted += 1
        else:
            skipped += 1
    return {"deleted": deleted, "skipped": skipped}


async def list_tasks(session: AsyncSession, *, limit: int = 50, offset: int = 0) -> list[CrawlerTask]:
    res = await session.execute(
        select(CrawlerTask).order_by(CrawlerTask.created_at.desc()).limit(limit).offset(offset)
    )
    return list(res.scalars().all())


async def get_task(session: AsyncSession, task_id: str) -> CrawlerTask | None:
    return await session.get(CrawlerTask, task_id)


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
        h = int(hashlib.md5(word.encode()).hexdigest(), 16) & ((1 << bits) - 1)
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
