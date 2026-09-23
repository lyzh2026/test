"""链接提取：从 HTML 中提取所有 <a href> 链接及其上下文。不做任何过滤。

保留的工具函数：
  - extract_url_date / is_url_date_in_range — URL 日期提取
  - find_next_page_url — 翻页检测
  - dedup_links — 去重
  - STATIC_PAGE_KEYWORDS — 静态信息页关键词（供 readability_adapter 使用）
"""

import re
from dataclasses import dataclass
from datetime import date
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class ExtractedLink:
    """从 HTML 中提取的单个链接及其上下文。"""
    url: str
    text: str                       # 锚文本
    surrounding_text: str = ""      # 锚文本周围文本（~100 字）
    parent_class: str = ""          # 父容器 class
    parent_id: str = ""             # 父容器 id


# ---------------------------------------------------------------------------
# URL 日期提取（用于发现阶段预过滤）
# ---------------------------------------------------------------------------

# 优先级：精确日期 > 年月 > 年份，避免 /202605/ 被误匹配为 /2026/05/
_URL_DATE_PATTERNS = [
    (re.compile(r"/(\d{4})[/-](\d{1,2})[/-](\d{1,2})/"), "day"),    # /2023-05-06/ or /2023/05/06/
    (re.compile(r"/(\d{4})[/-](\d{1,2})/"), "month"),                # /2023-05/ or /2023/05/
    (re.compile(r"/(\d{4})(\d{2})\d{2}[\W_]"), "month_compact"),    # /20230506_ / /20230506. / /20230506/
    (re.compile(r"/(\d{4})(\d{2})/"), "month_compact"),              # /202305/
    (re.compile(r"/(\d{4})/"), "year"),                              # /2023/
]


def extract_url_date(url: str) -> date | None:
    """从 URL 路径中提取日期。返回 date 或 None（无法提取时）。"""
    path = urlparse(url).path
    for pattern, granularity in _URL_DATE_PATTERNS:
        m = pattern.search(path)
        if not m:
            continue
        try:
            y = int(m.group(1))
            if not (2000 <= y <= 2099):
                continue
            if granularity == "day":
                mo, d = int(m.group(2)), int(m.group(3))
                return date(y, mo, d)
            elif granularity in ("month", "month_compact"):
                mo = int(m.group(2))
                if 1 <= mo <= 12:
                    return date(y, mo, 1)
                return None  # 月份无效（如 /2026/13/），直接拒绝，不 fallback 到年份
            elif granularity == "year":
                return date(y, 1, 1)
        except (ValueError, IndexError):
            continue
    return None


def extract_url_date_with_granularity(url: str) -> tuple[date, str] | None:
    """从 URL 路径中提取日期及粒度。返回 (date, "day"|"month"|"year") 或 None。"""
    path = urlparse(url).path
    for pattern, granularity in _URL_DATE_PATTERNS:
        m = pattern.search(path)
        if not m:
            continue
        try:
            y = int(m.group(1))
            if not (2000 <= y <= 2099):
                continue
            if granularity == "day":
                mo, d = int(m.group(2)), int(m.group(3))
                return date(y, mo, d), "day"
            elif granularity in ("month", "month_compact"):
                mo = int(m.group(2))
                if 1 <= mo <= 12:
                    return date(y, mo, 1), "month"
                return None
            elif granularity == "year":
                return date(y, 1, 1), "year"
        except (ValueError, IndexError):
            continue
    return None


def is_url_date_in_range(url: str, target_date: date, date_to: date) -> bool | None:
    """检查 URL 日期是否在目标范围内。考虑粒度：月级日期用整月重叠判断。

    Returns:
        True: 确定在范围内
        False: 确定不在范围内
        None: 无法判断（URL 无日期）
    """
    result = extract_url_date_with_granularity(url)
    if result is None:
        return None
    d, granularity = result
    if granularity == "day":
        return target_date <= d <= date_to
    elif granularity == "month":
        # 月级：用整月范围判断重叠
        import calendar
        last_day = calendar.monthrange(d.year, d.month)[1]
        month_end = date(d.year, d.month, last_day)
        return month_end >= target_date and d <= date_to
    elif granularity == "year":
        year_end = date(d.year, 12, 31)
        return year_end >= target_date and d <= date_to
    return None


# ---------------------------------------------------------------------------
# 静态信息页关键词（供 readability_adapter 标题过滤使用）
# ---------------------------------------------------------------------------

STATIC_PAGE_KEYWORDS = {
    "学校沿革", "历史沿革", "沿革", "学校简介", "学校概况", "关于我们", "简介",
    "机构设置", "部门设置", "组织架构", "内设机构", "机构职能",
    "领导介绍", "领导班子", "现任领导", "历任领导", "领导信箱",
    "校园风光", "校园地图", "校园导览", "校区介绍",
    "招生就业", "招生信息", "招生简章", "本科招生", "研究生招生",
    "师资队伍", "师资力量", "名师风采", "教师风采", "杰出人才",
    "学科建设", "专业设置", "重点学科", "学科简介",
    "校史", "校训", "校歌", "校徽", "校庆",
    "联系我们", "联系方式", "交通指南", "来校路线",
    "信息公开指南", "信息公开目录",
    "规章制度", "政策法规",
    "校友会", "校友总会", "教育基金会",
    "图书馆", "档案馆", "网络中心",
    "校园文化", "学生工作", "学生社团",
    "合作交流", "国际交流", "国际合作",
    "党建工作", "思政工作", "纪检监察",
    "安全保卫", "后勤服务", "物业服务",
    # 大学导航页补充
    "本科教育", "本科专业", "研究生教育", "终身教育", "招生教育",
    "继续教育", "优质课程", "特色项目", "实践教学", "教学成果",
    "教学名师", "奖助体系", "国际化培养", "学位教育",
    "学术学位", "专业学位", "学术期刊", "技术转移", "论文著作",
    "获奖成果", "企业合作", "地方合作", "科研机构",
    "科研项目", "重大项目", "学术交流", "清华论坛", "媒体关注",
}


# ---------------------------------------------------------------------------
# 核心提取函数
# ---------------------------------------------------------------------------

# 行级容器标签（向上追溯时命中即停止）
_ROW_TAGS = {"li", "tr", "td", "p", "article", "section", "h3", "h4"}


def _find_row_container(tag, max_depth: int = 3):
    """向上追溯 DOM 树找行级容器，最多 max_depth 层。

    优先命中 <li>/<tr>/<td>/<p> 等行级标签；
    <div> 需要文本较短（< 200 字）才当作行级容器。
    """
    cur = tag.parent
    for _ in range(max_depth):
        if cur is None:
            break
        if cur.name in _ROW_TAGS:
            return cur
        if cur.name == "div":
            text = cur.get_text(strip=True)
            if len(text) < 200:
                return cur
        cur = cur.parent
    return tag.parent  # fallback


def extract_all_links(html: str, base_url: str) -> list[ExtractedLink]:
    """从 HTML 中提取所有链接 + 行级上下文，不做任何过滤。"""
    soup = BeautifulSoup(html, "lxml")
    results: list[ExtractedLink] = []
    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        if not href:
            continue
        absolute = urljoin(base_url, href)
        absolute = absolute.split("#")[0]
        if not absolute:
            continue

        text = tag.get_text(strip=True)

        # 行级容器包裹：向上追溯找行级标签，打包整行文本
        row = _find_row_container(tag)
        surrounding = ""
        parent_class = ""
        parent_id = ""
        if row:
            surrounding = row.get_text(separator=" ", strip=True)[:200]
            parent_class = " ".join(row.get("class", [])) if row.get("class") else ""
            parent_id = row.get("id", "") or ""

        results.append(ExtractedLink(
            url=absolute,
            text=text,
            surrounding_text=surrounding,
            parent_class=parent_class,
            parent_id=parent_id,
        ))
    return results


# ---------------------------------------------------------------------------
# 翻页检测
# ---------------------------------------------------------------------------

def _valid_next_url(url: str) -> str | None:
    """验证下一页 URL 是否可用（过滤 javascript: 等伪链接）。"""
    if not url:
        return None
    if url.startswith(("http://", "https://")):
        return url
    return None


def find_next_page_url(html: str, base_url: str) -> str | None:
    """在 HTML 中检测"下一页"链接，返回绝对 URL 或 None。

    优先级：<link rel="next"> > <a rel="next"> > <a class="next"> > 文本含"下一页""下一頁""›""»" > ?page=N 推断。
    """
    soup = BeautifulSoup(html, "lxml")

    # 1. <link rel="next">
    link_tag = soup.find("link", rel="next")
    if link_tag and link_tag.get("href"):
        result = _valid_next_url(urljoin(base_url, link_tag["href"]))
        if result:
            return result

    # 2. <a rel="next">
    a_rel = soup.find("a", rel="next")
    if a_rel and a_rel.get("href"):
        result = _valid_next_url(urljoin(base_url, a_rel["href"]))
        if result:
            return result

    # 3. class 包含 next / pagination-next
    for cls_name in ("next", "pagination-next", "page-next", "next-page"):
        a = soup.find("a", class_=cls_name)
        if a and a.get("href"):
            result = _valid_next_url(urljoin(base_url, a["href"]))
            if result:
                return result

    # 4. 文本含"下一页""下一頁""›""»" 的 <a>
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"].strip()
        if href.startswith("javascript:"):
            continue
        text = a_tag.get_text(strip=True)
        if any(sep in text for sep in ("下一页", "下一頁", "›", "»", "next", "»")):
            result = _valid_next_url(urljoin(base_url, href))
            if result:
                return result

    # 5. 列表页 ?page=N 参数推断（当前 URL + 1）
    parsed = urlparse(base_url)
    from urllib.parse import parse_qs, urlencode, urlunparse
    qs = parse_qs(parsed.query)
    if "page" in qs:
        try:
            cur = int(qs["page"][0])
            qs["page"] = [str(cur + 1)]
            new_q = urlencode(qs, doseq=True)
            result = urlunparse(parsed._replace(query=new_q))
            if result:
                return result
        except (ValueError, IndexError):
            pass

    return None


# ---------------------------------------------------------------------------
# 去重
# ---------------------------------------------------------------------------

def dedup_links(links: list[str]) -> list[str]:
    """去重并保持顺序。"""
    seen: set[str] = set()
    results: list[str] = []
    for url in links:
        if url not in seen:
            seen.add(url)
            results.append(url)
    return results
