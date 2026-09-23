"""站点发现服务：4 模块架构（LinkExtractor → ScoringFilter → URLFrontier → Coordinator）。

参考 Scrapy LinkExtractor、Apache Nutch ScoringFilter、Heritrix URL Frontier、Crawl4AI HeadPeekr。
"""
import asyncio
import json
import logging
import re
from datetime import date, datetime
from urllib.parse import parse_qs, urlparse

from sqlalchemy import select

import httpx
from bs4 import BeautifulSoup
from lxml import etree

from app.modules.crawler.renderer import renderer
from app.modules.discovery.frontier import URLFrontier
from app.modules.discovery.link_extractor import (
    extract_all_links,
    extract_url_date,
    is_url_date_in_range,
    find_next_page_url,
)
from app.modules.discovery.scoring import (
    ScoredLink,
    _extract_date_from_text,
    score_link_simple,
    score_links,
)
from app.core.database import AsyncSessionLocal
from app.models.article import Article

logger = logging.getLogger(__name__)

_DISCOVERY_CONCURRENCY = 5  # BFS 每层并发数

# ---------------------------------------------------------------------------
# Sitemap 发现
# ---------------------------------------------------------------------------
_SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
_SITEMAP_FETCH_TIMEOUT = 15.0
_SITEMAP_MAX_URLS = 2000
_SITEMAP_FETCH_CONCURRENCY = 5
_SITEMAP_MAX_RECURSION = 2
_SITEMAP_TOTAL_TIMEOUT = 30.0
_SITEMAP_LASTMOD_THRESHOLD_DAYS = 10
_SITEMAP_COMMON_PATHS = [
    "/sitemap.xml", "/sitemap_index.xml", "/sitemap-index.xml",
    "/sitemaps/sitemap.xml", "/sitemap/sitemap.xml",
]

# 网络捕获 API 发现
_API_SCORE_THRESHOLD = 10
_API_MAX_PAGES = 20
_API_FETCH_TIMEOUT = 15.0

_URL_FIELD_CANDIDATES = [
    "url", "URL", "link", "href", "articleUrl", "newsUrl",
    "detailUrl", "pageUrl", "sourceUrl", "redirectUrl",
]
_DATE_FIELD_CANDIDATES = [
    "date", "pubDate", "publishTime", "createTime", "time",
    "publishDate", "createdAt", "updateTime", "DOCRELPUBTIME",
    "DOCPUBTIME", "releaseDate", "postDate",
]
_TITLE_FIELD_CANDIDATES = [
    "title", "Title", "subject", "name", "headline",
    "articleTitle", "newsTitle", "heading",
]

# ---------------------------------------------------------------------------
# 日期感知前后截断：轻量 meta 标签日期提取（不依赖 Playwright）
# ---------------------------------------------------------------------------

_META_DATE_ATTRS = [
    {"property": "article:published_time"},
    {"name": "pubdate"},
    {"name": "publishdate"},
    {"name": "firstpublishedtime"},
    {"name": "citation_publication_date"},
    {"name": "dc.date"},
    {"name": "DC.date"},
    {"property": "og:pubdate"},
    {"name": "PubDate"},
    {"name": "date"},
]


def _quick_extract_date(html: str) -> date | None:
    """从 HTML meta 标签提取发布日期（仅检查头部，不做全文搜索）。"""
    soup = BeautifulSoup(html, "lxml")
    for attrs in _META_DATE_ATTRS:
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            val = tag["content"].strip()[:10]
            for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
                try:
                    return datetime.strptime(val, fmt).date()
                except ValueError:
                    continue
    return None


def _parse_date_string(s: str) -> date | None:
    """解析 ISO 8601 日期字符串，截取前 10 位。"""
    s = s.strip()[:10]
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _extract_jsonld_date(data) -> date | None:
    """递归提取 JSON-LD 中的 datePublished（优先）/ dateModified。"""
    if isinstance(data, list):
        for item in data:
            d = _extract_jsonld_date(item)
            if d:
                return d
        return None
    if isinstance(data, dict):
        for key in ("datePublished", "dateModified"):
            val = data.get(key)
            if val:
                d = _parse_date_string(str(val))
                if d:
                    return d
        for item in data.get("@graph", []):
            d = _extract_jsonld_date(item)
            if d:
                return d
    return None


def _extract_page_meta_date(soup) -> date | None:
    """从页面元数据提取发布日期：JSON-LD → meta 标签。"""
    # 1. JSON-LD datePublished
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            d = _extract_jsonld_date(data)
            if d:
                return d
        except (json.JSONDecodeError, TypeError):
            continue
    # 2. <meta> 标签
    for attrs in _META_DATE_ATTRS:
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            d = _parse_date_string(tag["content"])
            if d:
                return d
    return None


def _extract_article_date(soup) -> date | None:
    """从已渲染 HTML 提取文章发布日期（优先级：time > meta > 日期元素 > 正文容器）。"""
    # 1. <time datetime="..."> — W3C 标准，最可靠
    for time_tag in soup.find_all("time"):
        dt = time_tag.get("datetime", "")
        if dt:
            d = _parse_date_string(dt)
            if d:
                return d
    # 2. JSON-LD / meta 标签
    meta_date = _extract_page_meta_date(soup)
    if meta_date:
        return meta_date
    # 3. 带日期 class/id 的元素（如 class="date"、"pubdate"、"sj"）
    for el in soup.find_all(class_=re.compile(r"date|time|pubdate|publish|arti_|^sj$", re.I)):
        text = el.get_text(strip=True)[:80]
        d = _extract_date_from_text(text)
        if d:
            return d
    for el in soup.find_all(id=re.compile(r"date|time|pubdate|publish", re.I)):
        text = el.get_text(strip=True)[:80]
        d = _extract_date_from_text(text)
        if d:
            return d
    # 4. 正文容器前 500 字（避开页脚版权日期）
    #    广泛匹配中文大学 CMS 常见 class/id 模式
    content_area = (
        soup.find("article")
        or soup.find("div", class_=re.compile(
            r"article-content|article-body|post-body|news-content"
            r"|v_news_content|v_news_con|article_content"
            r"|article-con|news-con|detail-con|TRS_Editor", re.I))
        or soup.find("div", id=re.compile(
            r"vsb_content|article-content|article-body|content-main"
            r"|article_content|news_content", re.I))
    )
    if content_area:
        text = content_area.get_text(strip=True)[:500]
        d = _extract_date_from_text(text)
        if d:
            return d
    return None


# ---------------------------------------------------------------------------
# API 发现：Playwright 网络捕获 → 启发式评分 → httpx 消费
# ---------------------------------------------------------------------------


def _extract_items_from_api_response(data, data_field_hint: str | None = None) -> list[dict] | None:
    """从 API JSON 响应中提取文章列表（兼容多种包装形式）。"""
    if isinstance(data, list):
        return data if all(isinstance(i, dict) for i in data) else None
    if not isinstance(data, dict):
        return None
    if data_field_hint and data_field_hint in data:
        val = data[data_field_hint]
        if isinstance(val, list) and all(isinstance(i, dict) for i in val):
            return val
    for field in ("data", "list", "items", "results", "articleList",
                  "newsList", "records", "rows", "content", "documents"):
        val = data.get(field)
        if isinstance(val, list) and val and isinstance(val[0], dict):
            return val
    for key, value in data.items():
        if isinstance(value, list) and value and isinstance(value[0], dict):
            return value
    return None


def _detect_api_fields(sample: dict) -> dict:
    """从单条记录自动检测 URL/日期/标题字段名。"""
    url_field = next((c for c in _URL_FIELD_CANDIDATES if c in sample and isinstance(sample[c], str)), "")
    date_field = next((c for c in _DATE_FIELD_CANDIDATES if c in sample and isinstance(sample[c], (str, int, float)) and str(sample[c]).strip()), "")
    title_field = next((c for c in _TITLE_FIELD_CANDIDATES if c in sample and isinstance(sample[c], str)), "")
    return {"url_field": url_field, "date_field": date_field, "title_field": title_field}


def _score_api_response(resp: dict) -> int:
    """对捕获的 JSON 响应评分，越高越可能是文章列表 API。"""
    score = 0
    url = resp.get("url", "")
    body = resp.get("body", "")

    # 尝试解析 JSON
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        return 0

    items = _extract_items_from_api_response(data)
    if items is None:
        return 0

    # 直接列表 +10，字段包装列表 +8
    if isinstance(data, list):
        score += 10
    else:
        score += 8

    # 列表数量加分
    if len(items) >= 5:
        score += 3

    # URL 关键词加分
    lower_url = url.lower()
    for kw in ("list", "article", "news", "data", "feed", "json"):
        if kw in lower_url:
            score += 2

    # 字段检测加分
    fields = _detect_api_fields(items[0])
    if fields["url_field"]:
        score += 5
    if fields["date_field"]:
        score += 3
    if fields["title_field"]:
        score += 2
    if fields["url_field"] and fields["date_field"]:
        score += 2  # 同时有 URL + 日期加分

    return score


def _parse_api_date(val) -> date | None:
    """多格式日期解析。"""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        # 时间戳（毫秒或秒）
        ts = val / 1000 if val > 10**12 else val
        try:
            from datetime import datetime as dt_util
            return dt_util.fromtimestamp(ts).date()
        except (OSError, OverflowError, ValueError):
            return None
    s = str(val).strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S",
                "%Y%m%d", "%Y年%m月%d日"):
        try:
            return datetime.strptime(s[:19], fmt).date()
        except ValueError:
            continue
    # 正则兜底
    m = re.search(r"(20\d{2}[-/]\d{2}[-/]\d{2})", s)
    if m:
        for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
            try:
                return datetime.strptime(m.group(1), fmt).date()
            except ValueError:
                continue
    return None


def _detect_api_pagination(data, api_url: str) -> dict | None:
    """自动检测 API 分页模式。"""
    if not isinstance(data, dict):
        return None
    # 从响应体检测
    for page_field in ("totalPages", "totalPage", "totalCount", "total", "totalNum"):
        if page_field in data:
            page_size = None
            for size_field in ("pageSize", "page_size", "size", "limit", "pageSize"):
                val = data.get(size_field)
                if isinstance(val, (int, float)) and val > 0:
                    page_size = int(val)
                    break
            return {"type": "page", "page_size": page_size}
    if "hasMore" in data or "hasNext" in data:
        return {"type": "cursor", "cursor_field": "nextCursor" if "nextCursor" in data else None}

    # 从 URL 参数推断
    parsed = urlparse(api_url)
    qs = parse_qs(parsed.query)
    if "page" in qs or "pageNum" in qs or "p" in qs:
        return {"type": "page", "page_size": None}
    if "offset" in qs or "start" in qs:
        page_size = None
        if "limit" in qs:
            try:
                page_size = int(qs["limit"][0])
            except (ValueError, IndexError):
                pass
        return {"type": "offset", "page_size": page_size}
    return None


def _discover_api_from_network(network_responses: list[dict]) -> dict | None:
    """遍历捕获的 JSON 响应，评分选出最优 API 端点。"""
    best: dict | None = None
    best_score = 0

    for resp in network_responses:
        score = _score_api_response(resp)
        if score > best_score:
            body = resp.get("body", "")
            try:
                data = json.loads(body)
            except (json.JSONDecodeError, ValueError):
                continue
            items = _extract_items_from_api_response(data)
            if not items:
                continue
            fields = _detect_api_fields(items[0])
            pagination = _detect_api_pagination(data, resp["url"])
            best = {
                "api_url": resp["url"],
                "url_field": fields["url_field"],
                "date_field": fields["date_field"],
                "title_field": fields["title_field"],
                "original_body": body,
                "pagination": pagination,
                "score": score,
            }
            best_score = score

    if best and best_score >= _API_SCORE_THRESHOLD:
        return best
    return None


async def _fetch_all_from_api(
    api_info: dict,
    *,
    target_date: date | None,
    date_to: date | None,
    max_links: int = 50,
) -> list[dict]:
    """httpx 调用发现的 API，处理分页和日期过滤，返回 [{url, date}]。"""
    api_url = api_info["api_url"]
    url_field = api_info["url_field"]
    date_field = api_info["date_field"]
    pagination = api_info["pagination"]
    all_articles: list[dict] = []

    page = 1
    while len(all_articles) < max_links:
        url = api_url
        if pagination and pagination.get("type") == "page" and page > 1:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}page={page}"
        elif pagination and pagination.get("type") == "offset" and page > 1:
            ps = pagination.get("page_size") or 20
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}offset={(page - 1) * ps}"

        try:
            async with httpx.AsyncClient(timeout=_API_FETCH_TIMEOUT) as c:
                resp = await c.get(url, headers={"User-Agent": "Mozilla/5.0 Chrome/120"})
                if resp.status_code != 200:
                    if page > 1:
                        break  # 翻页返回非 200 说明已到底
                    return []
                data = resp.json()
        except Exception as e:
            logger.debug("api_fetch: request failed %s - %r", url, e)
            if page > 1:
                break
            return []

        items = _extract_items_from_api_response(data)
        if not items:
            break

        # 日期感知截断
        any_in_range = False
        all_too_old = True   # 全部比目标范围旧（翻过头了）
        all_too_new = True   # 全部比目标范围新（还没到）
        for item in items:
            if len(all_articles) >= max_links:
                break
            raw_url = item.get(url_field) or item.get("url") or item.get("URL") or ""
            if not raw_url:
                continue
            article_date = None
            if date_field:
                article_date = _parse_api_date(item.get(date_field))

            # 日期过滤
            if target_date and date_to and article_date:
                if target_date <= article_date <= date_to:
                    any_in_range = True
                    all_too_old = False
                    all_too_new = False
                elif article_date < target_date:
                    continue  # 太旧，跳过
                else:
                    all_too_new = False  # 太新但 all_too_old 也应为 False
                    continue

            all_articles.append({"url": raw_url, "date": article_date})

        # 全部比目标旧 → 已翻过头，停止
        if all_too_old and not any_in_range and items and date_field:
            logger.debug("api_fetch: all articles older than range at page %d, stopping", page)
            break
        # 全部比目标新 → 还没到，继续翻页（不 break）

        # 检测是否还有下一页
        if not pagination:
            break
        if pagination["type"] == "page":
            page += 1
        elif pagination["type"] == "offset":
            page += 1
        else:
            break  # cursor 分页暂不支持自动翻页

    logger.info("api_fetch: got %d articles from %s", len(all_articles), api_url)
    return all_articles


async def _sample_article_date(article_urls: list[str]) -> date | None:
    """对候选文章 URL 做轻量级日期采样（httpx 快速请求，无 JS）。"""
    for url in article_urls[:3]:
        try:
            rendered = await renderer.fast_fetch(url)
            if rendered and rendered.get("ok"):
                d = _quick_extract_date(rendered["html"])
                if d:
                    return d
        except Exception:
            continue
    return None


async def _render_listing_for_api(
    listing_url: str, target_date: date | None, date_to: date | None, max_links: int
) -> list[dict] | None:
    """渲染列表页并尝试 API 发现，成功返回文章列表，失败返回 None。"""
    try:
        _lr = await renderer.render(listing_url, capture_network=True, scroll_rounds_range=(1, 2))
        _lnr = _lr.get("network_responses", [])
        if not _lnr:
            return None
        _api2 = _discover_api_from_network(_lnr)
        if not _api2:
            return None
        logger.info("api_discovery: found API %s (score=%d) from listing page %s",
                    _api2["api_url"], _api2["score"], listing_url)
        _api2_articles = await _fetch_all_from_api(
            _api2, target_date=target_date, date_to=date_to, max_links=max_links,
        )
        if not _api2_articles:
            return None
        results = [
            {"url": a["url"], "score": score_link_simple(a["url"])}
            for a in _api2_articles
        ]
        results.sort(key=lambda x: x["score"], reverse=True)
        logger.info("api_discovery: got %d articles from listing page %s",
                    len(results), listing_url)
        return results
    except Exception as e:
        logger.debug("listing page api_discovery failed: %s - %r", listing_url, e)
        return None


# ---------------------------------------------------------------------------
# Sitemap 发现：robots.txt 解析 → sitemap.xml 递归 → 文章 URL 提取
# ---------------------------------------------------------------------------


async def _fetch_text(url: str) -> str | None:
    """httpx 获取纯文本响应（绕过 fast_fetch 的 HTML 专有检查）。"""
    try:
        async with httpx.AsyncClient(timeout=_SITEMAP_FETCH_TIMEOUT, follow_redirects=True) as c:
            resp = await c.get(url, headers={"User-Agent": "Mozilla/5.0 Chrome/120"})
            if resp.status_code == 200:
                return resp.text
    except Exception as e:
        logger.debug("sitemap fetch_text failed: %s - %r", url, e)
    return None


def _parse_robots_for_sitemap(text: str) -> list[str]:
    """从 robots.txt 内容中提取 Sitemap: 指令的 URL。"""
    results = []
    for line in text.splitlines():
        line = line.strip()
        if line.lower().startswith("sitemap:"):
            url = line.split(":", 1)[1].strip()
            if url:
                results.append(url)
    return results


async def _try_common_sitemap_paths(base_url: str) -> list[str]:
    """尝试常见 sitemap 路径，返回找到的 URL 列表。"""
    from urllib.parse import urljoin
    found = []
    for path in _SITEMAP_COMMON_PATHS:
        url = urljoin(base_url, path)
        text = await _fetch_text(url)
        if text and ("<urlset" in text[:500].lower() or "<sitemapindex" in text[:500].lower()):
            found.append(url)
    return found


async def _parse_sitemap(
    url: str,
    *,
    entry_host: str,
    depth: int = 0,
    sem: asyncio.Semaphore,
    deadline: float,
) -> tuple[list[dict], list[str]]:
    """递归解析 sitemap XML，返回 (article_urls, child_sitemap_urls)。

    article_urls: [{"url": str, "lastmod": date|None}]
    容错：每个 sitemap 独立 try/except，失败返回空。
    """
    if depth > _SITEMAP_MAX_RECURSION:
        return [], []
    if asyncio.get_event_loop().time() > deadline:
        logger.debug("sitemap: deadline exceeded at %s", url)
        return [], []

    async with sem:
        text = await _fetch_text(url)
    if not text:
        return [], []

    articles: list[dict] = []
    child_sitemaps: list[str] = []

    try:
        # 解析 XML，容错命名空间
        root = etree.fromstring(text.encode("utf-8"))
        # 尝试带命名空间的查询
        ns = {"s": _SITEMAP_NS}
        url_elements = root.findall(".//s:url", ns)
        sitemap_elements = root.findall(".//s:sitemap", ns)

        # 命名空间回退：如果带命名空间查询为空，尝试无命名空间
        if not url_elements and not sitemap_elements:
            url_elements = root.findall(".//url")
            sitemap_elements = root.findall(".//sitemap")

        # 提取子 sitemap
        for sm in sitemap_elements:
            loc = sm.find("s:loc", ns)
            if loc is None:
                loc = sm.find("loc")
            if loc is not None and loc.text:
                child_sitemaps.append(loc.text.strip())

        # 提取文章 URL
        for url_el in url_elements:
            if len(articles) >= _SITEMAP_MAX_URLS:
                break
            loc = url_el.find("s:loc", ns)
            if loc is None:
                loc = url_el.find("loc")
            if loc is None or not loc.text:
                continue
            loc_text = loc.text.strip()

            # 只保留同站 URL
            if urlparse(loc_text).netloc != entry_host:
                continue

            # 提取 lastmod
            lastmod_el = url_el.find("s:lastmod", ns)
            if lastmod_el is None:
                lastmod_el = url_el.find("lastmod")
            lastmod_date = None
            if lastmod_el is not None and lastmod_el.text:
                try:
                    lastmod_date = datetime.strptime(lastmod_el.text.strip()[:10], "%Y-%m-%d").date()
                except ValueError:
                    pass

            articles.append({"url": loc_text, "lastmod": lastmod_date})

    except Exception as e:
        logger.debug("sitemap parse failed: %s - %r", url, e)
        return [], []

    return articles, child_sitemaps


async def _discover_from_sitemap(
    entry_url: str,
    *,
    entry_host: str,
    max_links: int,
    target_date: date | None = None,
    date_to: date | None = None,
) -> list[dict]:
    """Stage 0: 从 sitemap 发现文章链接。返回 [{"url": str, "score": int}]。"""
    deadline = asyncio.get_event_loop().time() + _SITEMAP_TOTAL_TIMEOUT
    sem = asyncio.Semaphore(_SITEMAP_FETCH_CONCURRENCY)

    # Step 1: 获取 sitemap URL 列表
    sitemap_urls: list[str] = []

    # 尝试 robots.txt
    robots_url = entry_url.rstrip("/") + "/robots.txt"
    robots_text = await _fetch_text(robots_url)
    if robots_text:
        sitemap_urls = _parse_robots_for_sitemap(robots_text)
        if sitemap_urls:
            logger.info("sitemap: found %d sitemap URLs from robots.txt", len(sitemap_urls))

    # 回退：常见路径
    if not sitemap_urls:
        sitemap_urls = await _try_common_sitemap_paths(entry_url)
        if sitemap_urls:
            logger.info("sitemap: found %d sitemap URLs from common paths", len(sitemap_urls))

    if not sitemap_urls:
        logger.info("sitemap: no sitemap found for %s", entry_url)
        return []

    # Step 2: 递归解析所有 sitemap
    all_articles: list[dict] = []
    to_process = list(sitemap_urls)

    for _ in range(_SITEMAP_MAX_RECURSION + 1):
        if not to_process or len(all_articles) >= _SITEMAP_MAX_URLS:
            break
        if asyncio.get_event_loop().time() > deadline:
            logger.debug("sitemap: total timeout reached")
            break

        tasks = [
            _parse_sitemap(u, entry_host=entry_host, sem=sem, deadline=deadline)
            for u in to_process
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        next_batch: list[str] = []
        for r in results:
            if isinstance(r, Exception):
                continue
            articles, children = r
            all_articles.extend(articles)
            next_batch.extend(children)

        to_process = next_batch

    if not all_articles:
        logger.info("sitemap: no article URLs extracted from sitemaps")
        return []

    # Step 3: lastmod 阈值过滤（超过 N 天的丢弃，不占配额）
    today = date.today()
    threshold = today - __import__("datetime").timedelta(days=_SITEMAP_LASTMOD_THRESHOLD_DAYS)
    filtered = [
        a for a in all_articles
        if a["lastmod"] is None or a["lastmod"] >= threshold
    ]
    skipped = len(all_articles) - len(filtered)
    if skipped:
        logger.info("sitemap: lastmod threshold (%d days) filtered out %d old URLs",
                     _SITEMAP_LASTMOD_THRESHOLD_DAYS, skipped)

    # Step 3.5: URL 日期预过滤（优先 URL 路径日期，lastmod 作补充）
    if target_date and date_to:
        date_filtered = []
        for a in filtered:
            # 优先从 URL 路径提取发布日期（比 lastmod 更可靠，支持月级粒度）
            in_range = is_url_date_in_range(a["url"], target_date, date_to)
            if in_range is None:
                # URL 无日期，用 lastmod 作参考
                if a["lastmod"] and not (target_date <= a["lastmod"] <= date_to):
                    continue
            elif not in_range:
                continue
            date_filtered.append(a)
        skipped_date = len(filtered) - len(date_filtered)
        if skipped_date:
            logger.info("sitemap: date filter (%s~%s) filtered out %d URLs",
                        target_date, date_to, skipped_date)
        filtered = date_filtered

    # Step 4: 去重 + 评分
    seen: set[str] = set()
    results_list: list[dict] = []
    for a in filtered:
        if a["url"] in seen:
            continue
        seen.add(a["url"])
        results_list.append({"url": a["url"], "score": score_link_simple(a["url"])})

    results_list.sort(key=lambda x: x["score"], reverse=True)
    logger.info("sitemap: returning %d articles (capped at %d)", min(len(results_list), max_links), max_links)
    return results_list[:max_links]


# ---------------------------------------------------------------------------
# head_peek：流式 HTTP 只下载 <head>，提取 meta 日期（~200-500ms/URL）
# ---------------------------------------------------------------------------

_HEAD_PEEK_TIMEOUT = 3.0
_HEAD_PEEK_MAX_BYTES = 20000


async def head_peek_date(url: str) -> date | None:
    """流式下载到 </head>，提取 meta 标签中的发布日期。"""
    try:
        async with httpx.AsyncClient(timeout=_HEAD_PEEK_TIMEOUT, follow_redirects=True) as client:
            async with client.stream("GET", url, headers={"User-Agent": "Mozilla/5.0 Chrome/120"}) as response:
                if response.status_code != 200:
                    return None
                head = b""
                async for chunk in response.aiter_bytes(chunk_size=512):
                    head += chunk
                    if b"</head>" in head or len(head) > _HEAD_PEEK_MAX_BYTES:
                        break
        html = head.decode("utf-8", errors="ignore")
        d = _quick_extract_date(html)
        if d:
            logger.debug("head_peek: %s → date=%s", url, d)
        return d
    except Exception as e:
        logger.debug("head_peek failed: %s - %r", url, e)
        return None


# ---------------------------------------------------------------------------
# 链接密度：文章页 vs 列表页
# ---------------------------------------------------------------------------

_LINK_DENSITY_THRESHOLD = 0.35  # 链接文本占比阈值

# 翻页熔断
_CIRCUIT_BREAKER_STRIKE_THRESHOLD = 5  # 连续 N 页高越界比例 → chain frozen
_CIRCUIT_BREAKER_PAGE_RATIO = 0.8     # 单页越界链接占比高于此 → strike
_CIRCUIT_BREAKER_MIN_SAMPLE = 5       # 单页至少有 N 个可判定日期的链接才计入

# ---------------------------------------------------------------------------
# Hub Base 分流：门户首页 → 子站入口提取
# ---------------------------------------------------------------------------


_HUB_NEWS_KEYWORDS = {
    "新闻", "通知", "公告", "学术", "讲座", "动态", "媒体", "资讯",
    "信息", "头条", "报道", "科研", "教学", "交流", "合作", "活动",
}


def _is_relevant_hub_base(text: str, url: str) -> bool:
    """判断子站入口链接是否可能包含新闻/文章内容。

    仅当锚文本或 URL 包含新闻相关关键词时返回 True，
    确保 Hub Base 提权只作用于可能有内容的子站。
    """
    for kw in _HUB_NEWS_KEYWORDS:
        if kw in text:
            return True
    url_lower = url.lower()
    for kw in ("/news", "/info", "/zx", "/xw"):
        if kw in url_lower:
            return True
    return False


def _get_root_domain(host: str) -> str:
    """提取根域名（去掉 www. 前缀）。"""
    return host[4:] if host.startswith("www.") else host


def _is_same_site(url: str, entry_host: str) -> bool:
    """检查 URL 是否属于同一站点（同 host、子域名、或同根域名）。"""
    host = urlparse(url).netloc
    if host == entry_host:
        return True
    entry_root = _get_root_domain(entry_host)
    host_root = _get_root_domain(host)
    if entry_root and host_root == entry_root:
        return True
    return host.endswith("." + entry_root) if entry_root else False


def _is_portal_page(links: list, soup) -> bool:
    """检测入口页是否是门户导航页（区别于 CMS 列表页）。

    门户特征：高链接密度 + 大量 2-8 字"导航式"锚文本。
    """
    body = soup.find("body")
    if not body:
        return False
    density = _compute_link_density(body)
    total_with_text = sum(1 for l in links if len(l.text.strip()) >= 2)
    if total_with_text < 10:
        return False
    short_count = sum(1 for l in links if 2 <= len(l.text.strip()) <= 8)
    short_ratio = short_count / total_with_text
    return density > 0.25 and short_ratio > 0.4


def _extract_hub_bases(links: list, entry_host: str) -> list:
    """从门户首页提取子站入口链接（Hub Base），给予高优先级（score=85）。

    筛选条件：
    1. 锚文本 2-8 字（"清华新闻"、"通知公告"）
    2. 指向同站子路径或受信子域名
    3. 跳过文章详情页（/info/1234/5678.htm）和下载文件；允许列表页（news.htm、index.htm）
    """
    hub_bases = []
    for link in links:
        text = link.text.strip()
        url = link.url
        if len(text) < 2 or len(text) > 8:
            continue
        if not url.startswith(("http://", "https://")):
            continue
        if not _is_same_site(url, entry_host):
            continue
        parsed = urlparse(url)
        path = parsed.path
        # 跳过文章详情页（如 /info/1234/5678.htm）和下载类文件
        if re.search(r"/\d+/\d+\.(htm|html|shtml)$", path):
            continue
        if path.endswith((".pdf", ".doc", ".docx", ".zip", ".rar")):
            continue
        if not _is_relevant_hub_base(text, url):
            continue
        hub_bases.append(ScoredLink(
            url=url,
            score=85,
            signals={"hub_base": True, "text": text,
                     "depth_score": 25, "time_score": 20, "text_len_score": 20},
        ))
    return hub_bases


# ---------------------------------------------------------------------------
# URL 模式翻页推断（中国 CMS 通用：index_2.htm / list_2.html）
# ---------------------------------------------------------------------------


def _infer_pagination_url(url: str, page_num: int) -> str | None:
    """根据 CMS URL 模式推断第 page_num 页的 URL。

    支持模式：
    1. /xxx/index_1.htm → /xxx/index_2.htm
    2. /xxx/index.htm → /xxx/index_2.htm
    3. /xxx/list_1.html → /xxx/list_2.html
    4. /xxx/ → /xxx/index_2.htm
    5. /xxx/1.html → /xxx/2.html
    """
    if page_num <= 1:
        return None

    parsed = urlparse(url)
    path = parsed.path

    # 1. /xxx/index_N.{htm,html}
    m = re.search(r"/index_(\d+)\.(htm|html)$", path)
    if m:
        ext = m.group(2)
        new_path = re.sub(r"/index_\d+\.(htm|html)$", f"/index_{page_num}.{ext}", path)
        return url.replace(path, new_path)

    # 2. /xxx/index.{htm,html}
    m = re.search(r"/index\.(htm|html)$", path)
    if m:
        ext = m.group(1)
        new_path = path.replace(f"index.{ext}", f"index_{page_num}.{ext}")
        return url.replace(path, new_path)

    # 3. /xxx/list_N.{htm,html}
    m = re.search(r"/list_(\d+)\.(htm|html)$", path)
    if m:
        ext = m.group(2)
        new_path = re.sub(r"/list_\d+\.(htm|html)$", f"/list_{page_num}.{ext}", path)
        return url.replace(path, new_path)

    # 4. /xxx/ 目录 → /xxx/index_N.htm
    if path.endswith("/") and path.count("/") >= 2:
        return url.rstrip("/") + f"/index_{page_num}.htm"

    # 5. /xxx/N.{htm,html} 数字结尾
    m = re.search(r"/(\d+)\.(htm|html)$", path)
    if m:
        ext = m.group(2)
        new_path = re.sub(r"/\d+\.(htm|html)$", f"/{page_num}.{ext}", path)
        return url.replace(path, new_path)

    return None


def _compute_link_density(body_tag) -> float:
    """计算 <body> 中链接文本占总文本的比例。

    文章页：大量正文、少量链接 → 密度低（< 0.2）
    列表页：链接密集、正文少 → 密度高（> 0.5）
    """
    if body_tag is None:
        return 1.0  # 无 body → 不是文章
    all_text = body_tag.get_text(strip=True)
    if len(all_text) < 50:
        return 1.0  # 文本太少 → 不是文章
    link_text = "".join(a.get_text(strip=True) for a in body_tag.find_all("a"))
    return len(link_text) / len(all_text)


# ---------------------------------------------------------------------------
# 文章 vs 列表页判断（基于评分信号）
# ---------------------------------------------------------------------------

def _looks_like_article(sl: ScoredLink) -> bool:
    """基于评分信号判断是否更像文章而非列表页。

    长锚文本（≥12字）+ 有时间痕迹 → 文章（走 head_peek 快速验证）。
    短锚文本 + 日期 → 黄金枢纽（优质列表页），不走这条路。
    """
    if sl.signals.get("text_len_score", 0) >= 25 and sl.signals.get("time_score", 0) >= 10:
        return True
    return False


# ---------------------------------------------------------------------------
# DYNAMIC_QUEUE：无日期信号的文章 → Playwright + 全文正则兜底
# ---------------------------------------------------------------------------

async def _process_dynamic_queue(
    pending: list[dict],
    *,
    target_date: date | None,
    date_to: date | None,
    max_links: int = 50,
) -> list[dict]:
    """对无日期信号的文章页做 Playwright 重渲染 + 全文日期正则，三路分流。"""
    results: list[dict] = []
    for item in pending:
        if len(results) >= max_links:
            break
        url = item["url"]
        try:
            # Playwright 渲染（静态页 fast_fetch 已经失败才会进 DYNAMIC_QUEUE）
            rendered = await renderer.render(url, scroll_rounds_range=(1, 2))
            if not rendered or not rendered.get("ok"):
                logger.debug("dynamic_queue: render failed, discard: %s", url)
                continue

            html = rendered["html"]
            soup = BeautifulSoup(html, "lxml")

            # 1. 结构化日期提取（第二次尝试，html 可能比 fast_fetch 完整）
            article_date = _extract_article_date(soup)

            # 2. 结构化无果 → 全文正则（body text 搜 ISO/中文/英文日期）
            if not article_date:
                body = soup.find("body")
                body_text = body.get_text(strip=True) if body else ""
                article_date = _extract_date_from_body_text(body_text)

            # 3. 三路分流
            if article_date and target_date and date_to:
                if target_date <= article_date <= date_to:
                    logger.info("dynamic_queue: recovered in-range article: %s (date=%s)", url, article_date)
                    results.append({"url": url, "score": item["score"]})
                else:
                    logger.info("dynamic_queue: out of range: %s (date=%s, range=%s~%s)",
                                url, article_date, target_date, date_to)
                    # 越界 → 丢弃
            else:
                logger.info("dynamic_queue: no date found, discard: %s", url)
                # 无法找到日期 → 丢弃（避免死链入库）
        except Exception as e:
            logger.debug("dynamic_queue: processing failed: %s - %r", url, e)
    return results


# ---------------------------------------------------------------------------
# DB 去重：批量检查 URL 是否已在 Article 库中
# ---------------------------------------------------------------------------

async def _batch_filter_existing_urls(urls: list[str]) -> set[str]:
    """批量查询 Article 表，返回已存在的 URL 集合。"""
    if not urls:
        return set()
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Article.original_link).where(Article.original_link.in_(urls))
            )
            return set(row[0] for row in result.all())
    except Exception as e:
        logger.warning("db dedup check failed: %r", e)
        return set()


# ---------------------------------------------------------------------------
# 翻页熔断：链标识 + 计数器
# ---------------------------------------------------------------------------

def _get_chain_key(url: str) -> str:
    """从 URL 路径提取翻页链标识（前 3 段，如 /news/2024/ → /news/2024/）。"""
    path = urlparse(url).path.rstrip("/")
    parts = [p for p in path.split("/") if p]
    key = "/" + "/".join(parts[:3])
    if not key.endswith("/"):
        key += "/"
    return key


# ---------------------------------------------------------------------------
# 全文日期正则兜底：对 Playwright 渲染后的 body 文本搜日期模式
# ---------------------------------------------------------------------------

_BODY_DATE_RE_ISO = re.compile(r'(20\d{2})[-/](\d{1,2})[-/](\d{1,2})')
_BODY_DATE_RE_CN = re.compile(r'(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日')
_BODY_DATE_RE_EN = re.compile(
    r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{1,2}),?\s+(20\d{2})', re.I
)
_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _extract_date_from_body_text(text: str) -> date | None:
    """从正文全文中正则搜索日期模式（ISO / 中文 / 英文）。"""
    m = _BODY_DATE_RE_ISO.search(text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    m = _BODY_DATE_RE_CN.search(text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    m = _BODY_DATE_RE_EN.search(text)
    if m:
        try:
            return date(int(m.group(3)), _MONTHS[m.group(1).lower()[:3]], int(m.group(2)))
        except (ValueError, KeyError):
            pass
    return None




# ---------------------------------------------------------------------------
# Coordinator：多源数据汇入 Frontier → head_peek → 完整爬取
# ---------------------------------------------------------------------------

async def discover_articles(
    *,
    entry_url: str,
    max_depth: int = 3,
    max_links: int = 50,
    enable_pagination: bool = True,
    max_pages: int = 10,
    target_date: date | None = None,
    date_to: date | None = None,
    enable_sitemap: bool = True,
) -> list[dict]:
    """Coordinator：多源数据汇入 Frontier → head_peek → 完整爬取。

    Phase 1: Sitemap + API + 入口页 HTML → 评分 → 入 Frontier
    Phase 2: Frontier 驱动循环：出队 → 判断文章/列表 → head_peek 预检 → 爬取/下钻

    返回 [{"url": str, "score": int}], 按评分降序排列。
    """
    entry_host = urlparse(entry_url).netloc
    frontier = URLFrontier(default_quota=20, max_size=max_links * 5)
    article_results: list[dict] = []
    visited_pages: set[str] = set()
    depth_map: dict[str, int] = {entry_url: 0}
    paginated_urls: set[str] = set()

    # ====== Phase 1: 多源数据汇入 Frontier ======

    # 1a. Sitemap → 直接入 Frontier
    if enable_sitemap:
        try:
            sitemap_results = await _discover_from_sitemap(
                entry_url,
                entry_host=entry_host,
                max_links=max_links,
                target_date=target_date,
                date_to=date_to,
            )
            for sr in sitemap_results:
                sl = ScoredLink(url=sr["url"], score=sr["score"])
                frontier.push(sl)
            if sitemap_results:
                logger.info("sitemap: got %d URLs into frontier", len(sitemap_results))
        except Exception as e:
            logger.warning("sitemap discovery failed for %s: %r", entry_url, e)

    # 1b. API 发现（Playwright 网络捕获）→ 入 Frontier
    rendered_entry: dict = {}
    try:
        rendered_entry = await renderer.render(
            entry_url,
            capture_network=True,
            scroll_rounds_range=(2, 3),
            scroll=True,
        )
        network_responses = rendered_entry.get("network_responses", [])
        api_found = False
        if network_responses:
            api_info = _discover_api_from_network(network_responses)
            if api_info:
                api_found = True
                logger.info("api_discovery: found API endpoint %s (score=%d)",
                            api_info["api_url"], api_info["score"])
                api_articles = await _fetch_all_from_api(
                    api_info,
                    target_date=target_date,
                    date_to=date_to,
                    max_links=max_links,
                )
                for a in api_articles:
                    sl = ScoredLink(url=a["url"], score=score_link_simple(a["url"]))
                    frontier.push(sl)
                if api_articles:
                    logger.info("api_discovery: got %d articles into frontier", len(api_articles))

        # 列表页候选 → 尝试 API 发现
        if not api_found:
            entry_html = rendered_entry.get("html", "") if rendered_entry.get("ok") else ""
            if not entry_html:
                ff_entry = await renderer.fast_fetch(entry_url)
                if ff_entry and ff_entry.get("ok"):
                    entry_html = ff_entry["html"]
            if entry_html:
                links = extract_all_links(entry_html, entry_url)
                scored = score_links(links, target_date=target_date, date_to=date_to)
                # 高分链接中找列表页候选（非文章、高深度分）
                listing_candidates = [
                    sl for sl in scored
                    if not _looks_like_article(sl)
                    and _is_same_site(sl.url, entry_host)
                ][:8]
                for lc in listing_candidates:
                    api_result = await _render_listing_for_api(lc.url, target_date, date_to, max_links)
                    if api_result:
                        for a in api_result:
                            sl = ScoredLink(url=a["url"], score=a["score"])
                            frontier.push(sl)
                        logger.info("api_discovery: got %d articles from listing %s",
                                    len(api_result), lc.url)
    except Exception as e:
        logger.warning("api_discovery failed for %s: %r", entry_url, e)

    # 1f. Hub Base 分流：门户首页 → 提取子站入口（高优先级入队）
    hub_bases: list[ScoredLink] = []
    if rendered_entry.get("ok"):
        _hub_html = rendered_entry["html"]
        _hub_soup = BeautifulSoup(_hub_html, "lxml")
        _hub_links = extract_all_links(_hub_html, rendered_entry.get("final_url") or entry_url)
        if _is_portal_page(_hub_links, _hub_soup):
            _hub_bases = _extract_hub_bases(_hub_links, entry_host)
            hub_bases = list(_hub_bases)
            for _hb in _hub_bases:
                depth_map[_hb.url] = 0
                frontier.push(_hb, skip_quota=True)
            if _hub_bases:
                logger.info("hub_base: extracted %d sub-site entries from portal page (score=85)", len(_hub_bases))

    # 1c. 入口页 HTML → 提取链接 → 评分 → 入 Frontier
    try:
        ff_result = await renderer.fast_fetch(entry_url)
        if ff_result and ff_result.get("ok"):
            links = extract_all_links(ff_result["html"], ff_result.get("final_url") or entry_url)
            scored = score_links(links, target_date=target_date, date_to=date_to)
            for sl in scored:
                if _is_same_site(sl.url, entry_host):
                    depth_map[sl.url] = 0
                    frontier.push(sl)
    except Exception as e:
        logger.warning("entry page fetch failed: %s - %r", entry_url, e)

    # 1d. 导航链路兜底：fast_fetch 链接太少 → 用 Playwright 渲染结果补
    if frontier.size < 20 and rendered_entry.get("ok"):
        links = extract_all_links(rendered_entry["html"], rendered_entry.get("final_url") or entry_url)
        scored = score_links(links, target_date=target_date, date_to=date_to)
        before = frontier.size
        for sl in scored:
            if _is_same_site(sl.url, entry_host):
                depth_map[sl.url] = 0
                frontier.push(sl)
        if frontier.size > before:
            logger.info("playwright nav fallback: extracted %d more links (frontier: %d→%d)",
                        frontier.size - before, before, frontier.size)

    # 1e. 入口页翻页兜底（不等 Frontier 出队）
    if enable_pagination and entry_url not in paginated_urls:
        _ep_render = rendered_entry if rendered_entry.get("ok") else ff_result
        if _ep_render and _ep_render.get("ok"):
            _ep_html = _ep_render["html"]
            _ep_soup = BeautifulSoup(_ep_html, "lxml")
            _ep_body = _ep_soup.find("body")
            _ep_density = _compute_link_density(_ep_body) if _ep_body else 0
            if _ep_body and _ep_density >= _LINK_DENSITY_THRESHOLD:
                paginated_urls.add(entry_url)
                _ep_cur_url = _ep_render.get("final_url") or entry_url
                _ep_cur_html = _ep_html
                _ep_found = False

                for _ in range(max_pages):
                    _ep_next = find_next_page_url(_ep_cur_html, _ep_cur_url)
                    if not _ep_next or _ep_next in paginated_urls:
                        break
                    _ep_found = True
                    paginated_urls.add(_ep_next)
                    _ep_r = await renderer.fast_fetch(_ep_next)
                    if not _ep_r or not _ep_r.get("ok"):
                        break
                    _ep_cur_url = _ep_r.get("final_url") or _ep_next
                    _ep_cur_html = _ep_r["html"]
                    for _ep_sl in score_links(extract_all_links(_ep_cur_html, _ep_cur_url),
                                              target_date=target_date, date_to=date_to):
                        if _is_same_site(_ep_sl.url, entry_host):
                            depth_map[_ep_sl.url] = 0
                            frontier.push(_ep_sl)

                if not _ep_found and _ep_soup.find("a", class_=re.compile(r"next", re.I)):
                    logger.info("entry page click_pagination: %s", entry_url)
                    _ep_pages = await renderer.click_paginate(_ep_cur_url, max_pages=max_pages)
                    for _ep_pd in _ep_pages:
                        for _ep_sl in score_links(
                            extract_all_links(_ep_pd["html"], _ep_pd.get("final_url", _ep_cur_url)),
                            target_date=target_date, date_to=date_to,
                        ):
                            if _is_same_site(_ep_sl.url, entry_host):
                                depth_map[_ep_sl.url] = 0
                                frontier.push(_ep_sl)

    # ====== Phase 2: Hub Base 优先处理 → 发现列表页 ======
    listing_pages: set[str] = set()  # Phase 3 待处理的列表页
    MAX_PAGES_RENDERED = 400
    pages_rendered = 0
    chain_strikes: dict[str, int] = {}        # 翻页熔断计数器
    pending_dynamic: list[dict] = []          # DYNAMIC_QUEUE：无日期信号的文章

    if hub_bases:
        hub_batch_size = _DISCOVERY_CONCURRENCY
        for i in range(0, len(hub_bases), hub_batch_size):
            hb_batch = hub_bases[i:i + hub_batch_size]
            # 并发渲染 hub_base 页面（含 Playwright 回退）
            async def _render_hub(url: str):
                if renderer.needs_playwright(url):
                    return await renderer.render(url, scroll_rounds_range=(1, 2))
                r = await renderer.fast_fetch(url)
                if not r:
                    await renderer.record_ff_failure(url)
                    return await renderer.render(url, scroll_rounds_range=(1, 2))
                renderer.record_ff_success(url)
                return r
            render_tasks = [_render_hub(hb.url) for hb in hb_batch]
            rendered_list = await asyncio.gather(*render_tasks, return_exceptions=True)

            for hb, rendered in zip(hb_batch, rendered_list):
                if isinstance(rendered, Exception) or not rendered or not rendered.get("ok"):
                    continue
                visited_pages.add(hb.url)
                pages_rendered += 1

                final_url = rendered.get("final_url") or hb.url
                links = extract_all_links(rendered["html"], final_url)
                scored = score_links(links, target_date=target_date, date_to=date_to)

                for sl in scored:
                    if not _is_same_site(sl.url, entry_host):
                        continue
                    # 日期分类
                    time_score = sl.signals.get("time_score", 15)
                    if time_score == 0:
                        # 黑色：日期超出15天 → 丢弃
                        continue
                    elif time_score == 15:
                        # 蓝色：无日期 → 默认当列表页
                        listing_pages.add(sl.url)
                    else:
                        # 绿色(30)/黄色(10)：日期在15天内 → 文章候选 → Frontier
                        frontier.push(sl)

            if pages_rendered >= MAX_PAGES_RENDERED:
                logger.warning("discovery: max pages rendered (%d) during hub_base phase, stopping", MAX_PAGES_RENDERED)
                break
            if len(article_results) >= max_links:
                break

        logger.info("hub_base phase: %d pages rendered, %d listing pages found, %d articles in frontier",
                    pages_rendered, len(listing_pages), frontier.size)

    # ====== Phase 2.5: 列表页独立处理 ======
    if listing_pages:
        _listing_batch = list(listing_pages)

        for lp in _listing_batch:
            if lp in visited_pages:
                continue
            try:
                if renderer.needs_playwright(lp):
                    rendered = await renderer.render(lp, scroll_rounds_range=(1, 2))
                else:
                    rendered = await renderer.fast_fetch(lp)
                    if not rendered:
                        await renderer.record_ff_failure(lp)
                        rendered = await renderer.render(lp, scroll_rounds_range=(1, 2))
                    else:
                        renderer.record_ff_success(lp)
            except Exception:
                continue
            if not rendered or not rendered.get("ok"):
                continue
            visited_pages.add(lp)
            pages_rendered += 1

            final_url = rendered.get("final_url") or lp
            html = rendered["html"]
            soup = BeautifulSoup(html, "lxml")
            body = soup.find("body")

            # 链接密度检查：确认是列表页还是误判的文章页
            density = _compute_link_density(body)
            if density <= _LINK_DENSITY_THRESHOLD:
                # 误判：实际是文章页 → 推入 Frontier，Phase 3 统一处理
                visited_pages.discard(lp)  # 允许 Phase 3 重新处理
                frontier.push(ScoredLink(url=lp, score=50, signals={}))
                logger.info("listing_page fallback: %s is article (density=%.2f), pushed to frontier", lp, density)
                continue

            # 确认是列表页：提取文章链接，推入 Frontier（Phase 4 做精确日期验证）
            links = extract_all_links(html, final_url)
            scored = score_links(links, target_date=target_date, date_to=date_to)
            _articles_pushed = 0
            for sl in scored:
                if not _is_same_site(sl.url, entry_host):
                    continue
                time_score = sl.signals.get("time_score", 15)
                if time_score == 0:
                    continue  # 日期超出15天，丢弃
                # time_score 30(范围内)/10(15天内)/15(无日期) → 都推入 Frontier
                frontier.push(sl)
                _articles_pushed += 1

            # 翻页（无电路熔断，仅用 max_pages 限制）
            _cur_html, _cur_url = html, final_url
            for _ in range(max_pages):
                next_url = find_next_page_url(_cur_html, _cur_url)
                if not next_url or next_url in paginated_urls:
                    break
                paginated_urls.add(next_url)
                try:
                    if renderer.needs_playwright(next_url):
                        next_rendered = await renderer.render(next_url, scroll_rounds_range=(2, 3))
                    else:
                        next_rendered = await renderer.fast_fetch(next_url)
                        if not next_rendered:
                            await renderer.record_ff_failure(next_url)
                            next_rendered = await renderer.render(next_url, scroll_rounds_range=(2, 3))
                        else:
                            renderer.record_ff_success(next_url)
                except Exception:
                    break
                if not next_rendered or not next_rendered.get("ok"):
                    break
                _cur_url = next_rendered.get("final_url") or next_url
                _cur_html = next_rendered["html"]
                pages_rendered += 1

                page_links = extract_all_links(_cur_html, _cur_url)
                page_scored = score_links(page_links, target_date=target_date, date_to=date_to)

                _page_pushed = 0
                for sl in page_scored:
                    if not _is_same_site(sl.url, entry_host):
                        continue
                    time_score = sl.signals.get("time_score", 15)
                    if time_score == 0:
                        continue  # 日期超出15天，丢弃
                    frontier.push(sl)
                    _page_pushed += 1

            if pages_rendered >= MAX_PAGES_RENDERED:
                break

        logger.info("listing_pages phase: %d pages rendered, frontier size=%d", pages_rendered, frontier.size)

    # ====== Phase 3: Frontier 驱动的爬取循环 ======
    pages_rendered = 0  # 重置计数器，Phase 3 有独立预算
    MAX_PAGES_RENDERED = 800  # Phase 3 需要更多预算处理 Frontier 中的 URL

    while not frontier.is_empty() and len(article_results) < max_links:
        # 批取出队，并发处理
        batch: list[ScoredLink] = []
        while not frontier.is_empty() and len(batch) < _DISCOVERY_CONCURRENCY:
            sl = frontier.pop()
            if sl and sl.url not in visited_pages:
                batch.append(sl)
                visited_pages.add(sl.url)

        if not batch:
            break

        tasks = [
            _process_frontier_url(
                sl,
                entry_host=entry_host,
                depth_map=depth_map,
                target_date=target_date,
                date_to=date_to,
                frontier=frontier,
                article_results=article_results,
                paginated_urls=paginated_urls,
                max_depth=max_depth,
                max_pages=max_pages,
                enable_pagination=enable_pagination,
                max_links=max_links,
                chain_strikes=chain_strikes,
                pending_dynamic=pending_dynamic,
            )
            for sl in batch
        ]
        results = await asyncio.gather(*tasks)
        pages_rendered += len(batch)

        # 硬上限：已渲染页面数
        if pages_rendered >= MAX_PAGES_RENDERED:
            logger.warning("discovery: max pages rendered (%d), stopping", MAX_PAGES_RENDERED)
            break

    # ====== DYNAMIC_QUEUE 处理：为无日期信号的文章做最终兜底 ======
    # 仅在设置了日期范围时运行（无日期范围时无日期文章已直接放行，此处不会积压）
    if pending_dynamic and target_date and date_to:
        logger.info("dynamic_queue: processing %d pending articles with Playwright + full-text date search", len(pending_dynamic))
        dynamic_results = await _process_dynamic_queue(
            pending_dynamic, target_date=target_date, date_to=date_to, max_links=max_links - len(article_results),
        )
        if dynamic_results:
            before = len(article_results)
            article_results.extend(dynamic_results)
            logger.info("dynamic_queue: recovered %d articles from %d pending (before=%d, after=%d)",
                        len(dynamic_results), len(pending_dynamic), before, len(article_results))

    # ====== DB 去重：过滤已在 Article 库中的 URL ======
    if article_results:
        urls_to_check = [a["url"] for a in article_results]
        existing_urls = await _batch_filter_existing_urls(urls_to_check)
        if existing_urls:
            before = len(article_results)
            article_results = [a for a in article_results if a["url"] not in existing_urls]
            logger.info("db dedup: filtered %d already-existing URLs (before=%d, after=%d)",
                        len(existing_urls), before, len(article_results))

    # 最终按评分降序截取
    article_results.sort(key=lambda x: x["score"], reverse=True)
    if len(article_results) > max_links:
        logger.info("discovery: collected %d, truncated to top %d by score",
                     len(article_results), max_links)
    return article_results[:max_links]


async def _process_frontier_url(
    sl: ScoredLink,
    *,
    entry_host: str,
    depth_map: dict[str, int],
    target_date: date | None,
    date_to: date | None,
    frontier: URLFrontier,
    article_results: list[dict],
    paginated_urls: set[str],
    max_depth: int,
    max_pages: int,
    enable_pagination: bool,
    max_links: int,
    chain_strikes: dict[str, int] | None = None,
    pending_dynamic: list[dict] | None = None,
):
    """处理单个 Frontier URL：渲染 → 链接密度判定文章/列表 → head_peek 验证/下钻。"""
    url = sl.url
    depth = depth_map.get(url, 0)

    # 0. URL 日期预检（快速拒绝明显过期的 URL）
    url_date = extract_url_date(url)
    if url_date and target_date and date_to:
        if not (target_date <= url_date <= date_to):
            logger.debug("url_date out of range: %s (date=%s)", url, url_date)
            return None

    # 1. 渲染页面
    if depth >= max_depth:
        return None

    try:
        if renderer.needs_playwright(url):
            rendered = await renderer.render(url, scroll_rounds_range=(1, 2))
        else:
            rendered = await renderer.fast_fetch(url)
            if not rendered:
                await renderer.record_ff_failure(url)
                rendered = await renderer.render(url, scroll_rounds_range=(1, 2))
            else:
                renderer.record_ff_success(url)  # sync, not async
    except Exception as e:
        logger.warning("render failed for frontier URL: %s - %r", url, e)
        return None
    if not rendered or not rendered.get("ok"):
        return None

    final_url = rendered.get("final_url") or url

    # 2. 文章日期确认（time > JSON-LD/meta > 正文容器前500字）
    html = rendered["html"]
    soup = BeautifulSoup(html, "lxml")
    body = soup.find("body")

    article_date = _extract_article_date(soup)
    if article_date and target_date and date_to:
        if not (target_date <= article_date <= date_to):
            logger.info("article_date filtered: %s (date=%s, range=%s~%s)", url, article_date, target_date, date_to)
            return {"filtered": True, "date": article_date}

    # 3. 无日期 → 降级 head_peek
    if not article_date and target_date and date_to and not url_date:
        peek_date = await head_peek_date(url)
        if peek_date and not (target_date <= peek_date <= date_to):
            logger.info("head_peek filtered: %s (peek=%s, range=%s~%s)", url, peek_date, target_date, date_to)
            return {"filtered": True, "date": peek_date}

    # 链路发现：已由 Phase 2/2.5 处理列表页发现，Phase 3 不再提取导航链接

    # 4. 链接密度判定：文章页 vs 列表页
    link_density = _compute_link_density(body)

    if link_density < _LINK_DENSITY_THRESHOLD:
        if article_date:
            # 有明确日期 → 直接入结果
            logger.info("article discovered: %s (score=%d, density=%.2f, date=%s)", url, sl.score, link_density, article_date)
            article_results.append({"url": url, "score": sl.score})
            return {"filtered": False, "date": article_date}
        elif pending_dynamic is not None and target_date and date_to:
            # 无日期但有日期范围 → 放入 DYNAMIC_QUEUE 等 Playwright + 全文正则兜底
            pending_dynamic.append({"url": url, "score": sl.score})
            logger.info("article pending (no date, queued for DYNAMIC): %s (score=%d)", url, sl.score)
            return None
        else:
            # 无日期 && (无日期范围 or 无 DYNAMIC_QUEUE) → 无罪推定放行
            logger.info("article discovered (no date, %s): %s (score=%d, density=%.2f)",
                        "fallthrough" if pending_dynamic is None else "no date range",
                        url, sl.score, link_density)
            article_results.append({"url": url, "score": sl.score})
            return {"filtered": False, "date": None}

    # 5. 列表页（链接密度高）→ 提取子链接 → 评分 → 入队

    # API 发现（BFS 内网络捕获）
    network_responses = rendered.get("network_responses", [])
    if network_responses:
        api_info = _discover_api_from_network(network_responses)
        if api_info:
            api_articles = await _fetch_all_from_api(
                api_info,
                target_date=target_date,
                date_to=date_to,
                max_links=max_links,
            )
            for a in api_articles:
                new_sl = ScoredLink(url=a["url"], score=score_link_simple(a["url"]))
                frontier.push(new_sl)
            if api_articles:
                logger.info("bfs_api: got %d articles from %s", len(api_articles), api_info["api_url"])
                return None

    # 列表页子链接提取：已由 Phase 2/2.5 处理，Phase 3 不再提取

    # 6. 自动翻页：已由 Phase 2/2.5 处理，Phase 3 禁用翻页
    if False and enable_pagination and url not in paginated_urls:
        paginated_urls.add(url)
        cur_html, cur_final = rendered["html"], final_url

        # 6a. 常规 URL 翻页（find_next_page_url 依赖 href 属性）
        _found_next = False
        for _ in range(max_pages):
            next_url = find_next_page_url(cur_html, cur_final)
            if not next_url or next_url in paginated_urls:
                break
            _found_next = True
            paginated_urls.add(next_url)
            try:
                if renderer.needs_playwright(next_url):
                    next_rendered = await renderer.render(next_url, scroll_rounds_range=(2, 3))
                else:
                    next_rendered = await renderer.fast_fetch(next_url)
                    if not next_rendered:
                        await renderer.record_ff_failure(next_url)
                        next_rendered = await renderer.render(next_url, scroll_rounds_range=(2, 3))
                    else:
                        renderer.record_ff_success(next_url)
            except Exception as e:
                logger.warning("pagination render failed: %s - %r", next_url, e)
                break
            if not next_rendered or not next_rendered.get("ok"):
                break
            cur_final = next_rendered.get("final_url") or next_url
            cur_html = next_rendered["html"]
            page_links = extract_all_links(cur_html, cur_final)
            page_scored = score_links(page_links, target_date=target_date, date_to=date_to)

            # ====== 翻页熔断：检测当前页链接日期分布 ======
            if chain_strikes is not None and target_date and date_to:
                chain_key = _get_chain_key(cur_final)
                dated_in = sum(1 for sl in page_scored if is_url_date_in_range(sl.url, target_date, date_to) is True)
                dated_out = sum(1 for sl in page_scored if is_url_date_in_range(sl.url, target_date, date_to) is False)
                dated_total = dated_in + dated_out
                if dated_total >= _CIRCUIT_BREAKER_MIN_SAMPLE and dated_out / dated_total >= _CIRCUIT_BREAKER_PAGE_RATIO:
                    chain_strikes[chain_key] = chain_strikes.get(chain_key, 0) + 1
                    if chain_strikes[chain_key] >= _CIRCUIT_BREAKER_STRIKE_THRESHOLD:
                        logger.info("circuit_breaker: chain %s frozen after %d strikes (out=%d/%d=%.0f%%)",
                                    chain_key, chain_strikes[chain_key], dated_out, dated_total, dated_out / dated_total * 100)
                        break  # 冻结翻页链，不再找下一页
                elif dated_total >= _CIRCUIT_BREAKER_MIN_SAMPLE:
                    # 正常页面 → 重置计数器（表示链还未过期）
                    chain_strikes[chain_key] = 0

                # 内容日期熔断：URL 无日期时，用评分信号中的 time_score 判断
                if dated_total == 0:
                    scored_green = sum(1 for sl in page_scored if sl.signals.get("time_score", 15) == 30)
                    scored_black = sum(1 for sl in page_scored if sl.signals.get("time_score", 15) == 0)
                    scored_dated = scored_green + scored_black
                    if scored_dated >= _CIRCUIT_BREAKER_MIN_SAMPLE and scored_green == 0:
                        logger.info("circuit_breaker: content-date chain %s — %d links all out of range (black=%d), stopping pagination",
                                    chain_key, scored_dated, scored_black)
                        break

            for new_sl in page_scored:
                if not _is_same_site(new_sl.url, entry_host):
                    continue
                _ts = new_sl.signals.get("time_score", 15)
                if _ts in (30, 10):
                    depth_map[new_sl.url] = depth + 1
                    frontier.push(new_sl)

        # 6b. Playwright 点击翻页兜底（常规翻页找不到有效 URL → JS 翻页）
        if not _found_next:
            _has_click_next = bool(
                soup.find("a", class_=re.compile(r"next|pagination.next", re.I))
                or soup.find("a", string=re.compile(r"下一页|下一頁"))
                or soup.find("a", rel="next")
            )
            if _has_click_next:
                _click_pages = await renderer.click_paginate(cur_final, max_pages=max_pages)
                if _click_pages:
                    logger.info("click_pagination: %s → %d pages via active click", url, len(_click_pages))
                    for _pd in _click_pages:
                        _html = _pd["html"]
                        _final = _pd.get("final_url", cur_final)
                        _links = extract_all_links(_html, _final)
                        _scored = score_links(_links, target_date=target_date, date_to=date_to)

                        # 翻页熔断
                        if chain_strikes is not None and target_date and date_to:
                            _ck = _get_chain_key(_final)
                            _din = sum(1 for sl in _scored if is_url_date_in_range(sl.url, target_date, date_to) is True)
                            _dout = sum(1 for sl in _scored if is_url_date_in_range(sl.url, target_date, date_to) is False)
                            _dtotal = _din + _dout
                            if _dtotal >= _CIRCUIT_BREAKER_MIN_SAMPLE and _dout / _dtotal >= _CIRCUIT_BREAKER_PAGE_RATIO:
                                chain_strikes[_ck] = chain_strikes.get(_ck, 0) + 1
                                if chain_strikes[_ck] >= _CIRCUIT_BREAKER_STRIKE_THRESHOLD:
                                    logger.info("circuit_breaker: click chain %s frozen", _ck)
                                    break
                            elif _dtotal >= _CIRCUIT_BREAKER_MIN_SAMPLE:
                                chain_strikes[_ck] = 0

                            # 内容日期熔断
                            if _dtotal == 0:
                                _sg = sum(1 for sl in _scored if sl.signals.get("time_score", 15) == 30)
                                _sb = sum(1 for sl in _scored if sl.signals.get("time_score", 15) == 0)
                                _sd = _sg + _sb
                                if _sd >= _CIRCUIT_BREAKER_MIN_SAMPLE and _sg == 0:
                                    logger.info("circuit_breaker: click content-date chain %s — %d links all out of range", _ck, _sd)
                                    break

                        for _sl in _scored:
                            if not _is_same_site(_sl.url, entry_host):
                                continue
                            _ts = _sl.signals.get("time_score", 15)
                            if _ts in (30, 10):
                                depth_map[_sl.url] = depth + 1
                                frontier.push(_sl)

            # 6c. URL 模式翻页兜底（常规翻页和点击翻页均无果 → 推断 CMS 翻页模式）
            _pattern_page = 2
            while _pattern_page <= max_pages:
                _pattern_url = _infer_pagination_url(cur_final, _pattern_page)
                if not _pattern_url or _pattern_url in paginated_urls:
                    break
                paginated_urls.add(_pattern_url)
                try:
                    _pattern_r = await renderer.fast_fetch(_pattern_url)
                    if not _pattern_r or not _pattern_r.get("ok"):
                        _pattern_r = await renderer.render(_pattern_url, scroll_rounds_range=(1, 2))
                except Exception:
                    break
                if not _pattern_r or not _pattern_r.get("ok"):
                    break
                _pattern_final = _pattern_r.get("final_url") or _pattern_url
                _pattern_html = _pattern_r["html"]
                _pattern_links = extract_all_links(_pattern_html, _pattern_final)
                _pattern_scored = score_links(_pattern_links, target_date=target_date, date_to=date_to)

                # 翻页熔断
                if chain_strikes is not None and target_date and date_to:
                    _pck = _get_chain_key(_pattern_final)
                    _pdin = sum(1 for sl in _pattern_scored if is_url_date_in_range(sl.url, target_date, date_to) is True)
                    _pdout = sum(1 for sl in _pattern_scored if is_url_date_in_range(sl.url, target_date, date_to) is False)
                    _pdtotal = _pdin + _pdout
                    if _pdtotal >= _CIRCUIT_BREAKER_MIN_SAMPLE and _pdout / _pdtotal >= _CIRCUIT_BREAKER_PAGE_RATIO:
                        chain_strikes[_pck] = chain_strikes.get(_pck, 0) + 1
                        if chain_strikes[_pck] >= _CIRCUIT_BREAKER_STRIKE_THRESHOLD:
                            logger.info("circuit_breaker: pattern chain %s frozen", _pck)
                            break
                    elif _pdtotal >= _CIRCUIT_BREAKER_MIN_SAMPLE:
                        chain_strikes[_pck] = 0

                    # 内容日期熔断
                    if _pdtotal == 0:
                        _psg = sum(1 for sl in _pattern_scored if sl.signals.get("time_score", 15) == 30)
                        _psb = sum(1 for sl in _pattern_scored if sl.signals.get("time_score", 15) == 0)
                        _psd = _psg + _psb
                        if _psd >= _CIRCUIT_BREAKER_MIN_SAMPLE and _psg == 0:
                            logger.info("circuit_breaker: pattern content-date chain %s — %d links all out of range", _pck, _psd)
                            break

                for _psl in _pattern_scored:
                    if not _is_same_site(_psl.url, entry_host):
                        continue
                    _ts = _psl.signals.get("time_score", 15)
                    if _ts in (30, 10):
                        depth_map[_psl.url] = depth + 1
                        frontier.push(_psl)
                _pattern_page += 1

    return None
