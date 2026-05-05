"""站点发现服务：BFS 遍历入口页，提取文章链接。"""
import logging
from collections import deque
from urllib.parse import urlparse

from app.modules.crawler.renderer import renderer
from app.modules.discovery.link_extractor import (
    dedup_links,
    extract_links,
    find_next_page_url,
    is_article_link,
    is_junk_link,
    is_listing_link,
    score_link,
)

logger = logging.getLogger(__name__)


async def discover_articles(
    *,
    entry_url: str,
    max_depth: int = 2,
    max_links: int = 50,
    enable_pagination: bool = True,
    max_pages: int = 5,
) -> list[dict]:
    """BFS 从入口页发现文章链接。

    支持自动翻页（enable_pagination），翻页不消耗 BFS depth 预算。
    返回 [{"url": str, "score": int}], 按评分降序排列。
    """
    entry_host = urlparse(entry_url).netloc
    seen: set[str] = set()
    queue: deque[tuple[str, int]] = deque([(entry_url, 0)])
    article_results: list[dict] = []
    paginated_urls: set[str] = set()  # 已翻页处理的 URL

    while queue and len(article_results) < max_links:
        url, depth = queue.popleft()
        if url in seen or depth > max_depth:
            continue
        seen.add(url)

        try:
            rendered = await renderer.render(url)
        except Exception as e:
            logger.warning("render failed for discovery: %s - %r", url, e)
            continue

        if not rendered.get("ok"):
            continue

        final_url = rendered.get("final_url") or url
        links = extract_links(rendered["html"], final_url)
        links = dedup_links(links)

        candidates: list[dict] = []
        for link in links:
            if is_junk_link(link) or link in seen:
                continue
            # 只保留同域链接
            if urlparse(link).netloc != entry_host:
                continue
            candidates.append({"url": link, "score": score_link(link)})

        # 按评分降序，优先处理高价值链接
        candidates.sort(key=lambda x: x["score"], reverse=True)

        for item in candidates:
            if len(article_results) >= max_links:
                break
            if item["url"] in seen:
                continue
            seen.add(item["url"])

            if is_article_link(item["url"]):
                article_results.append(item)
            elif is_listing_link(item["url"]) and depth < max_depth:
                queue.append((item["url"], depth + 1))

        # 自动翻页：检测"下一页"，推入同级队列（不消耗 depth）
        if enable_pagination and url not in paginated_urls:
            paginated_urls.add(url)
            for _ in range(max_pages):
                next_url = find_next_page_url(rendered["html"], final_url)
                if not next_url or next_url in seen or next_url in paginated_urls:
                    break
                paginated_urls.add(next_url)
                try:
                    rendered = await renderer.render(next_url)
                except Exception as e:
                    logger.warning("pagination render failed: %s - %r", next_url, e)
                    break
                if not rendered.get("ok"):
                    break
                final_url = rendered.get("final_url") or next_url
                links = extract_links(rendered["html"], final_url)
                links = dedup_links(links)
                for link in links:
                    if is_junk_link(link) or link in seen:
                        continue
                    if urlparse(link).netloc != entry_host:
                        continue
                    if len(article_results) >= max_links:
                        break
                    if link not in seen:
                        seen.add(link)
                        if is_article_link(link):
                            article_results.append({"url": link, "score": score_link(link)})

    # 最终按评分降序返回
    article_results.sort(key=lambda x: x["score"], reverse=True)
    return article_results
