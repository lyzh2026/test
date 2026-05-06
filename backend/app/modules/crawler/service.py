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
    direct_urls: list[str] | None = None,
    target_date: date,
    date_to: date | None = None,
    task_name: str | None,
    callback_url: str | None,
) -> CrawlerTask:
    """前端提交：URL 校验 → 创建 task（立即可见）→ 后台 discovery + crawl。

    direct_urls: 精确文章 URL，跳过发现直接爬取。
    url_list: 入口页 URL，先发现再爬取。
    """
    direct_urls = direct_urls or []
    if len(url_list) + len(direct_urls) > settings.CRAWLER_MAX_URLS_PER_TASK:
        raise URLValidationError(1001, f"单任务 URL 总数不能超过 {settings.CRAWLER_MAX_URLS_PER_TASK}")

    rules = await _load_rules(session)
    entry_urls: list[str] = []
    valid_direct_urls: list[str] = []
    failed_details: list[dict] = []

    async def _validate_url(raw: str, dest: list[str], seen: set[str]):
        nonlocal rules
        u = (raw or "").strip()
        if not u or u in seen:
            return
        seen.add(u)
        try:
            await validate_url(u, rules)
            dest.append(u)
        except URLValidationError as e:
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
                        dest.append(u)
                        return
                    except URLValidationError:
                        pass
            failed_details.append({"url": u, "code": e.code, "reason": e.message, "stage": "validate"})

    seen: set[str] = set()
    for raw in url_list:
        await _validate_url(raw, entry_urls, seen)
    for raw in direct_urls:
        await _validate_url(raw, valid_direct_urls, seen)

    # 先创建任务，POST 立即返回，前端立即可见
    all_urls = list(entry_urls) + list(valid_direct_urls)
    task = CrawlerTask(
        task_name=task_name,
        target_date=target_date,
        date_to=date_to,
        url_list=all_urls,
        total_urls=0,
        completed_urls=0,
        failed_urls=len(failed_details),
        failed_details=failed_details,
        status="pending",
        callback_url=callback_url,
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)

    if entry_urls:
        scheduler.add_job(
            _run_discovery_and_crawl,
            id=f"discover:{task.id}",
            args=[task.id, entry_urls, valid_direct_urls, target_date, date_to],
            trigger=DateTrigger(),
            replace_existing=True,
        )
    elif valid_direct_urls:
        # 只有精确 URL，跳过发现直接爬取
        scheduler.add_job(
            run_crawl_job,
            id=f"crawl:{task.id}",
            args=[task.id, valid_direct_urls],
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
    direct_urls: list[str],
    target_date: date,
    date_to: date | None,
):
    """后台：域名发现 → URL 校验 → 合并精确 URL → 更新 task → 启动 crawl。"""
    logger.info("discovery start: task=%s entries=%s direct=%s", task_id, len(entry_urls), len(direct_urls))

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

    # 精确 URL 直接加入（跳过发现）
    for url in direct_urls:
        discovered.add(url)

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
    """APScheduler 入口：单任务整体执行，每完成一个 URL 推送进度事件。

    顶层 try/except/finally 确保任何异常都不会让任务卡在 running 状态。
    """
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
    completed = 0
    failed = 0
    final_status = "failed"
    fatal_error: str | None = None

    try:
        progress_bus.emit(ProgressEvent(
            task_id=task_id, status="running", total=total,
            message=f"开始抓取 {total} 个 URL",
        ))

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
            new_failed: list = []
            for url, res in zip(urls, results):
                if isinstance(res, (Exception, BaseException)):
                    new_failed.append({"url": url, "code": 5001, "reason": f"内部异常：{res!r}", "stage": "render"})
                elif isinstance(res, dict) and not res.get("ok") and not res.get("dedup") and not res.get("filtered"):
                    new_failed.append({"url": url, "code": res.get("code", 2001), "reason": res.get("reason", "未知错误"), "stage": res.get("stage", "")})
            t.completed_urls = completed
            t.failed_urls = failed
            t.failed_details = list(t.failed_details or []) + new_failed
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
            final_status = t.status
            await session.commit()

    except Exception as e:
        logger.exception("crawl job fatal error: task=%s", task_id)
        fatal_error = str(e)[:500]
        final_status = "failed"

    finally:
        # 无论如何都确保任务状态被更新，不会卡在 running
        if fatal_error:
            try:
                async with AsyncSessionLocal() as session:
                    t = await session.get(CrawlerTask, task_id)
                    if t and t.status == "running":
                        t.status = "failed"
                        t.completed_at = datetime.now(timezone.utc)
                        details = list(t.failed_details or [])
                        details.append({"url": "*", "code": 5001, "reason": f"任务异常终止：{fatal_error}", "stage": "job"})
                        t.failed_details = details
                        t.failed_urls = len(details)
                        await session.commit()
                        final_status = "failed"
            except Exception:
                logger.exception("crawl job: failed to update task status after fatal error")

        # 清理取消标记
        _cancelled_tasks.discard(task_id)

        try:
            progress_bus.emit(ProgressEvent(
                task_id=task_id, status=final_status,
                completed=completed, failed=failed, total=total,
                message=f"任务{final_status}",
            ))
        except Exception:
            pass

        logger.info("crawl job end: task=%s status=%s", task_id, final_status)


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

    # 清洗新闻噪音（图片署名、标题块等）
    draft.raw_content = _clean_news_noise(draft.raw_content)

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


# === AI 浏览（LLM 联网搜索降级） ===

_AI_BROWSE_PROMPT = """请访问以下 URL，提取页面中的文章内容。

URL: {url}

请输出严格 JSON（不要任何解释）：
{{
  "original_title": "文章标题",
  "source_unit": "来源机构（如网站名称、发布单位）",
  "publish_date": "YYYY-MM-DD（发布日期，不确定则为 null）",
  "raw_content": "文章正文（Markdown 格式，去除导航、广告、推荐栏、版权声明）"
}}

规则：
1. 只输出 JSON。
2. raw_content 必须是完整正文，去除所有非正文内容。
3. 如果该 URL 不是文章页面（如首页、列表页），将 original_title 设为页面标题，raw_content 设为可获取的主要内容。
4. 如果无法访问或内容为空，输出 {{"original_title": "", "raw_content": "", "error": "原因描述"}}。
"""


def _extract_json_simple(content: str) -> dict | None:
    """从 LLM 响应中提取 JSON 对象。"""
    import json
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


async def _store_ai_browsed_article(
    *, task_id: str, url: str, title: str, content: str,
    source: str | None, date_str: str | None, target_date: date,
) -> str | None:
    """存储 AI 浏览获取的文章，返回 article_id 或 None（去重/过短）。"""
    if not content or len(content.strip()) < 100:
        return None

    content = _clean_news_noise(content)

    publish_date = target_date
    if date_str:
        try:
            publish_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except Exception:
            pass

    fingerprint = hashlib.md5(f"{title.strip()}{content[:200].strip()}".encode()).hexdigest()
    try:
        if await redis_client.exists(f"af:{fingerprint}"):
            logger.info("ai_browse dedup(md5) hit: %s", url)
            return None
    except Exception:
        pass

    original_link = _normalize_url(url)
    article_id = None

    async with AsyncSessionLocal() as sess:
        existing = await sess.execute(select(Article).where(Article.original_link == original_link))
        row = existing.scalar_one_or_none()
        if row:
            return str(row.id)

        article = Article(
            task_id=task_id,
            original_title=(title or "")[:512],
            source_unit=source,
            original_link=original_link,
            publish_date=publish_date,
            raw_content=content,
            status="raw",
        )
        sess.add(article)
        try:
            await sess.commit()
            await sess.refresh(article)
            article_id = str(article.id)
        except IntegrityError:
            await sess.rollback()
            return None

    if article_id:
        try:
            await redis_client.setex(f"af:{fingerprint}", 604800, "1")
        except Exception:
            pass
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

    return article_id


async def ai_browse_urls(task_id: str, urls: list[str], session: AsyncSession) -> dict:
    """用 LLM 联网搜索浏览失败 URL，提取内容入库。"""
    from app.modules.ai.kimi_client import get_ai_config, get_llm_client, get_web_search_tools

    client, model = await get_llm_client()
    if not client:
        return {"success": 0, "failed": [{"url": u, "reason": "AI API Key 未配置"} for u in urls], "total": len(urls)}

    cfg = await get_ai_config()
    provider = cfg.get("provider", "kimi")
    tools = get_web_search_tools(provider)

    task = await session.get(CrawlerTask, task_id)
    if not task:
        return {"success": 0, "failed": [{"url": u, "reason": "任务不存在"} for u in urls], "total": len(urls)}

    success_urls: list[str] = []
    failed: list[dict] = []

    for url in urls:
        try:
            prompt = _AI_BROWSE_PROMPT.format(url=url)
            resp = await client.chat.completions.create(
                model=model,
                temperature=0.1,
                max_tokens=4096,
                tools=tools,
                messages=[
                    {"role": "system", "content": "你是一个网页内容提取助手。请使用内置的网页浏览功能访问用户提供的 URL，然后提取文章的标题、正文、来源和发布日期。"},
                    {"role": "user", "content": prompt},
                ],
            )
            raw = resp.choices[0].message.content or ""
            data = _extract_json_simple(raw)

            if not data or not data.get("raw_content"):
                reason = data.get("error", "LLM 未能提取内容") if data else "LLM 响应解析失败"
                failed.append({"url": url, "reason": reason})
                continue

            article_id = await _store_ai_browsed_article(
                task_id=task_id, url=url,
                title=data.get("original_title", ""),
                content=data.get("raw_content", ""),
                source=data.get("source_unit"),
                date_str=data.get("publish_date"),
                target_date=task.target_date,
            )
            if article_id:
                success_urls.append(url)
            else:
                failed.append({"url": url, "reason": "文章存储失败（可能已存在或内容过短）"})
        except Exception as e:
            logger.warning("ai_browse failed for %s: %r", url, e)
            failed.append({"url": url, "reason": f"LLM 调用失败: {e!r}"})

    # 更新任务的 failed_details
    if success_urls:
        success_set = set(success_urls)
        remaining = [d for d in (task.failed_details or []) if d.get("url") not in success_set]
        task.failed_details = remaining
        task.failed_urls = len(remaining)
        task.completed_urls = (task.completed_urls or 0) + len(success_urls)
        if not remaining and task.status in ("partial_failed", "failed"):
            task.status = "completed" if task.completed_urls >= (task.total_urls or 0) else "partial_failed"
        await session.commit()

    return {"success": len(success_urls), "failed": failed, "total": len(urls)}


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


async def list_tasks(
    session: AsyncSession,
    *,
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
    date_from=None,
    date_to=None,
    keyword: str | None = None,
) -> tuple[list[CrawlerTask], int]:
    """返回 (tasks, total_count)，支持筛选。"""
    from datetime import timedelta

    from sqlalchemy import and_, func

    conditions = []
    if status:
        conditions.append(CrawlerTask.status == status)
    if date_from:
        conditions.append(CrawlerTask.created_at >= date_from)
    if date_to:
        conditions.append(CrawlerTask.created_at < date_to + timedelta(days=1))
    if keyword:
        conditions.append(CrawlerTask.task_name.ilike(f"%{keyword}%"))

    where = and_(*conditions) if conditions else None

    total = (await session.execute(
        select(func.count(CrawlerTask.id)).where(where) if where else select(func.count(CrawlerTask.id))
    )).scalar_one()

    stmt = select(CrawlerTask).order_by(CrawlerTask.created_at.desc()).limit(limit).offset(offset)
    if where:
        stmt = stmt.where(where)
    res = await session.execute(stmt)
    return list(res.scalars().all()), total


async def get_task(session: AsyncSession, task_id: str) -> CrawlerTask | None:
    return await session.get(CrawlerTask, task_id)


# === 新闻噪音清洗 ===

# 图片署名：新华社记者 XX 摄 / 图/XX / 摄影：XX / XX供图 / 新华社照片
_PHOTO_CREDIT_RE = re.compile(
    r'^(?:'
    r'(?:新华社|中新社|人民日报|央视|光明日报|经济日报)?'
    r'(?:记者\s*)?.{1,6}\s*(?:摄|摄影|拍摄|供图|图|照片)'
    r'|图[/／].{1,10}'
    r'|摄影[：:].{1,10}'
    r'|(?:图片|影像)[：:].{1,10}'
    r'|编辑[：:].{1,10}'
    r'|来源[：:].{1,20}'
    r')\s*$',
    re.MULTILINE,
)

# 标题块：连续 2-5 行短文本（每行不超 30 字），紧跟在标题后、正文前
_HEADLINE_BLOCK_RE = re.compile(
    r'(?:^.{2,30}[^\n。！？\n]\n){2,5}(?=[^\n])',
    re.MULTILINE,
)

# Markdown 粗体标记（支持跨行）
_MD_BOLD_RE = re.compile(r'\*{1,2}(.+?)\*{1,2}', re.DOTALL)

# 连续空行压缩
_MULTI_BLANK_RE = re.compile(r'\n{3,}')


def _clean_news_noise(text: str) -> str:
    """清洗新闻正文中的常见噪音：图片署名、标题块、markdown 标记等。"""
    if not text:
        return text
    # 去除 markdown 粗体标记
    text = _MD_BOLD_RE.sub(r'\1', text)
    # 去除图片署名行
    text = _PHOTO_CREDIT_RE.sub('', text)
    # 压缩连续空行
    text = _MULTI_BLANK_RE.sub('\n\n', text)
    return text.strip()


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


async def scan_stale_running_tasks(timeout_sec: int = 600) -> int:
    """启动时扫描：将卡在 running/pending 超过阈值的任务标记为 failed。

    典型场景：后端容器重启导致 APScheduler 内存 job 丢失，任务卡在 running。
    """
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=timeout_sec)
    moved = 0
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(CrawlerTask).where(CrawlerTask.status.in_(["running", "pending"]))
        )
        rows = res.scalars().all()
        for t in rows:
            # 用 started_at 或 created_at 判断是否超时
            ref = t.started_at or t.created_at
            if ref and ref.tzinfo is None:
                ref = ref.replace(tzinfo=timezone.utc)
            if ref and ref < cutoff:
                old_status = t.status
                t.status = "failed"
                t.completed_at = now
                details = list(t.failed_details or [])
                details.append({
                    "url": "*",
                    "code": 5001,
                    "reason": f"系统重启后自动终止（原状态: {old_status}）",
                    "stage": "startup_scan",
                })
                t.failed_details = details
                t.failed_urls = len(details)
                moved += 1
        if moved:
            await session.commit()
            logger.info("startup scan: marked %s stale tasks as failed", moved)
    return moved
