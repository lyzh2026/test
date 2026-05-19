"""链接提取与过滤：借鉴 Crawl4AI 的 FilterChain + 评分思路。"""

import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

# 静态信息页锚文本/标题黑名单（命中任一即跳过）
_STATIC_PAGE_KEYWORDS = {
    "学校沿革", "历史沿革", "沿革", "学校简介", "学校概况", "关于我们", "简介",
    "机构设置", "部门设置", "组织架构", "内设机构", "机构职能",
    "领导介绍", "领导班子", "现任领导", "历任领导", "领导信箱",
    "校园风光", "校园地图", "校园导览", "校区介绍",
    "招生就业", "招生信息", "招生简章", "本科招生", "研究生招生",
    "师资队伍", "师资力量", "名师风采", "教师风采", "杰出人才",
    "学科建设", "专业设置", "重点学科", "学科简介",
    "校史", "校训", "校歌", "校徽", "校庆",
    "联系我们", "联系方式", "交通指南", "来校路线",
    "信息公开", "信息公开指南", "信息公开目录",
    "规章制度", "政策法规",
    "校友会", "校友总会", "教育基金会",
    "图书馆", "档案馆", "网络中心",
    "校园文化", "学生工作", "学生社团",
    "合作交流", "国际交流", "国际合作",
    "党建工作", "思政工作", "纪检监察",
    "安全保卫", "后勤服务", "物业服务",
}


def _is_static_page_link(link_text: str, url: str) -> bool:
    """锚文本或 URL 路径是否指向静态信息页（非文章）。"""
    text = link_text.strip()
    for kw in _STATIC_PAGE_KEYWORDS:
        if text == kw or text.endswith(kw):
            return True
    # URL 路径中包含关键词拼音/英文也拦截
    lower_url = url.lower()
    _URL_BLOCK = [
        "about", "contact", "overview", "history", "introduction",
        "organization", "leadership", "campus", "enrollment",
        "faculty", "discipline", "xxgk", "xxjj", "jgsz",
    ]
    for seg in _URL_BLOCK:
        if f"/{seg}" in lower_url or f"/{seg}/" in lower_url:
            return True
    return False

# 文章 URL 的启发式加分模式
ARTICLE_PATTERNS = [
    (r"/article[s]?/", 2),
    (r"/news/", 2),
    (r"/detail/", 2),
    (r"/post/", 2),
    (r"/zhengce/", 2),
    (r"/zhengceku/", 2),
    (r"/content_\d+", 2),
    (r"/content/", 2),
    (r"/info/", 2),                       # 高校站点通用
    (r"/n/", 2),                          # 部分站点短 URL
    (r"/c/", 2),
    (r"/\d{4}[/-]\d{2}[/-]\d{2}/", 3),   # 日期路径
    (r"/(\d{4})(\d{2})/", 2),             # 202504 格式
    (r"\.s?html?$", 1),                   # .htm/.html 静态页面
]

# 垃圾路径排除模式（直接丢弃）
JUNK_PATTERNS = [
    r"^#",
    r"^javascript:",
    r"^mailto:",
    r"/tag[s]?/",
    r"/search",
    r"/about",
    r"/contact",
    r"/user[s]?/",
    r"/login",
    r"/register",
    r"/rss",
    r"/feed",
    r"/comment",
    r"\.pdf$",
    r"\.docx?$",
    r"\.jpe?g$",
    r"\.png$",
    r"\.gif$",
    r"\.zip$",
    r"\.rar$",
]

# 列表页路径模式（发现阶段需要继续深入）
LISTING_PATTERNS = [
    r"/news/?$",
    r"/article[s]?/?$",
    r"/zhengce/?$",
    r"/zhengceku/?$",
    r"/list/?",
    r"/category/",
    r"/column/",
    r"/subject/",
    r"/page/\d+",
    r"index\.html?$",
]


def extract_links(html: str, base_url: str) -> list[str]:
    """从 HTML 中提取所有绝对化后的链接。"""
    soup = BeautifulSoup(html, "lxml")
    results = []
    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        if not href:
            continue
        absolute = urljoin(base_url, href)
        # 去掉 # 后面的锚点
        absolute = absolute.split("#")[0]
        if absolute:
            results.append(absolute)
    return results


def extract_links_with_text(html: str, base_url: str) -> list[tuple[str, str]]:
    """从 HTML 中提取链接及其锚文本，过滤静态信息页。"""
    soup = BeautifulSoup(html, "lxml")
    results = []
    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        if not href:
            continue
        absolute = urljoin(base_url, href)
        absolute = absolute.split("#")[0]
        if not absolute:
            continue
        link_text = tag.get_text(strip=True)
        if _is_static_page_link(link_text, absolute):
            continue
        results.append((absolute, link_text))
    return results


def is_junk_link(url: str) -> bool:
    """是否是垃圾链接（导航、搜索、资源文件等）。"""
    for pattern in JUNK_PATTERNS:
        if re.search(pattern, url, re.I):
            return True
    return False


def is_article_link(url: str) -> bool:
    """URL 是否命中文章类路径模式。"""
    for pattern, _ in ARTICLE_PATTERNS:
        if re.search(pattern, url, re.I):
            return True
    return False


def is_listing_link(url: str) -> bool:
    """URL 是否命中列表页路径模式（可继续深入发现）。"""
    for pattern in LISTING_PATTERNS:
        if re.search(pattern, url, re.I):
            return True
    return False


def score_link(url: str) -> int:
    """链接评分：越高越可能是目标文章页。"""
    score = 0
    for pattern, pts in ARTICLE_PATTERNS:
        if re.search(pattern, url, re.I):
            score += pts

    # URL 深度适中加分（过深通常是垃圾页）
    parsed = urlparse(url)
    path_depth = parsed.path.count("/")
    if path_depth <= 4:
        score += 1
    if path_depth > 6:
        score -= 2

    # 查询参数过多扣分
    if parsed.query.count("&") > 2:
        score -= 1

    return score


def find_next_page_url(html: str, base_url: str) -> str | None:
    """在 HTML 中检测"下一页"链接，返回绝对 URL 或 None。

    优先级：<link rel="next"> > <a rel="next"> > <a class="next"> > 文本含"下一页""下一頁""›""»" > ?page=N 推断。
    """
    soup = BeautifulSoup(html, "lxml")

    # 1. <link rel="next">
    link_tag = soup.find("link", rel="next")
    if link_tag and link_tag.get("href"):
        return urljoin(base_url, link_tag["href"])

    # 2. <a rel="next">
    a_rel = soup.find("a", rel="next")
    if a_rel and a_rel.get("href"):
        return urljoin(base_url, a_rel["href"])

    # 3. class 包含 next / pagination-next
    for cls_name in ("next", "pagination-next", "page-next", "next-page"):
        a = soup.find("a", class_=cls_name)
        if a and a.get("href"):
            return urljoin(base_url, a["href"])

    # 4. 文本含"下一页""下一頁""›""»" 的 <a>（排除 aria-label=previous 等）
    for a_tag in soup.find_all("a", href=True):
        text = a_tag.get_text(strip=True)
        if any(sep in text for sep in ("下一页", "下一頁", "›", "»", "next", "»")):
            return urljoin(base_url, a_tag["href"])

    # 5. 列表页 ?page=N 参数推断（当前 URL + 1）
    parsed = urlparse(base_url)
    from urllib.parse import parse_qs, urlencode, urlunparse
    qs = parse_qs(parsed.query)
    if "page" in qs:
        try:
            cur = int(qs["page"][0])
            qs["page"] = [str(cur + 1)]
            new_q = urlencode(qs, doseq=True)
            return urlunparse(parsed._replace(query=new_q))
        except (ValueError, IndexError):
            pass

    return None


def dedup_links(links: list[str]) -> list[str]:
    """去重并保持顺序。"""
    seen: set[str] = set()
    results: list[str] = []
    for url in links:
        if url not in seen:
            seen.add(url)
            results.append(url)
    return results
