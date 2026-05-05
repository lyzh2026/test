"""单文章翻页检测：检测文章内容页的"下一页"链接。"""

import re
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup


def find_article_next_page(html: str, base_url: str, visited: set[str]) -> str | None:
    """在文章内容页中检测"下一页"链接。

    匹配优先级：
      1. <link rel="next"> 或 <a rel="next">
      2. <a class="next" / class="pagination-next" / class="article-next">
      3. 文本含"下一页""下一頁""›""»" 的 <a>
      4. URL 中 ?page=N 或 _N.html 模式推断
    """
    soup = BeautifulSoup(html, "lxml")

    # 1. <link rel="next">
    link_tag = soup.find("link", rel="next")
    if link_tag and link_tag.get("href"):
        url = urljoin(base_url, link_tag["href"])
        if url not in visited:
            return url

    # 2. <a rel="next">
    a_rel = soup.find("a", rel="next")
    if a_rel and a_rel.get("href"):
        url = urljoin(base_url, a_rel["href"])
        if url not in visited:
            return url

    # 3. class 关键字
    for cls_name in ("next", "pagination-next", "article-next", "page-next"):
        a = soup.find("a", class_=cls_name)
        if a and a.get("href"):
            url = urljoin(base_url, a["href"])
            if url not in visited:
                return url

    # 4. 文本匹配
    for a_tag in soup.find_all("a", href=True):
        text = a_tag.get_text(strip=True)
        if any(sep in text for sep in ("下一页", "下一頁", "›", "»", "next", "»")):
            url = urljoin(base_url, a_tag["href"])
            if url not in visited:
                return url

    # 5. ?page=N 推断（仅当当前 URL 有 page 参数）
    parsed = urlparse(base_url)
    qs = parse_qs(parsed.query)
    if "page" in qs:
        try:
            cur = int(qs["page"][0])
            next_page = str(cur + 1)
            qs["page"] = [next_page]
            new_q = urlencode(qs, doseq=True)
            url = urlunparse(parsed._replace(query=new_q))
            if url not in visited:
                return url
        except (ValueError, IndexError):
            pass

    # 6. _N.html 模式（如 content_1.html → content_2.html）
    m = re.search(r"/(\d+)\.html$", parsed.path)
    if m:
        cur = int(m.group(1))
        next_path = parsed.path.replace(m.group(1), str(cur + 1), 1)
        url = urlunparse(parsed._replace(path=next_path))
        if url not in visited:
            return url

    return None
