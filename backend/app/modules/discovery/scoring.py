"""ScoringFilter：域名无关的通用链接评分模型（0-100 分）。

3 个信号：
  1. 链接文本长度（0-40） — 文章标题长，导航链接短
  2. URL 路径深度（0-30） — 文章在较深路径
  3. 邻近时间痕迹（0-30） — 四色分流：绿色(命中)/黄色(近似)/黑色(过期)/蓝色(无日期)
"""

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from urllib.parse import urlparse

from app.modules.discovery.link_extractor import ExtractedLink, extract_url_date


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class ScoredLink:
    """评分后的链接。"""
    url: str
    score: int                      # 0-100
    signals: dict = field(default_factory=dict)  # 评分信号明细


# ---------------------------------------------------------------------------
# 信号 1：链接文本长度（0-40）
# ---------------------------------------------------------------------------

def _score_text_length(text: str) -> int:
    n = len(text.strip())
    if n == 0:
        return 0
    elif n <= 3:
        return 5        # 极短：导航（"首页"、"更多"）
    elif n <= 6:
        return 15       # 短：栏目名（"综合新闻"、"通知公告"）
    elif n <= 12:
        return 25       # 中等：可能是标题或栏目
    elif n <= 20:
        return 35       # 长：大概率是文章标题
    else:
        return 40       # 很长：几乎确定是文章标题


# ---------------------------------------------------------------------------
# 信号 2：URL 路径深度（0-30）
# ---------------------------------------------------------------------------

def _score_url_depth(url: str) -> int:
    path = urlparse(url).path
    depth = path.count("/")
    if depth <= 2:
        return 5        # 浅层：首页、一级栏目
    elif depth == 3:
        return 15       # 中层：列表页或文章
    elif depth == 4:
        return 25       # 深层：大概率是文章
    else:
        return 30       # 很深：几乎确定是文章


# ---------------------------------------------------------------------------
# 信号 3：邻近时间痕迹（0-30）— 四色分流
# ---------------------------------------------------------------------------

_DATE_PATTERNS_ABS = [
    re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日"),
    re.compile(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})"),
]

# 缺年份月日：5月8日、05-08、5/8（避免匹配 IP 地址、大数字、以及完整日期中的月日）
_DATE_PATTERN_NO_YEAR = re.compile(
    r"(?<![年0-9])(1[0-2]|0?[1-9])[-/月](0?[1-9]|[12]\d|3[01])[日]?(?![0-9])"
)

# 相对时间
_RELATIVE_PATTERNS = [
    (re.compile(r"(\d+)\s*分钟前"), lambda m: date.today()),
    (re.compile(r"(\d+)\s*小时前"), lambda m: date.today()),
    (re.compile(r"(\d+)\s*天前"), lambda m: date.today() - timedelta(days=int(m.group(1)))),
]


def _extract_date_from_text(text: str) -> date | None:
    """多级降级日期解析：相对时间 → 标准绝对（取最新） → 缺年份月日。"""
    today = date.today()

    # 优先级 1：相对时间
    if "昨天" in text:
        return today - timedelta(days=1)
    if "前天" in text:
        return today - timedelta(days=2)
    for pattern, calc in _RELATIVE_PATTERNS:
        m = pattern.search(text)
        if m:
            return calc(m)

    # 优先级 2：标准绝对日期（带 4 位年份）— 取所有匹配中最晚的
    best: date | None = None
    for p in _DATE_PATTERNS_ABS:
        for m in p.finditer(text):
            try:
                y, mo = int(m.group(1)), int(m.group(2))
                d = int(m.group(3)) if m.lastindex >= 3 else 1
                if 2000 <= y <= 2099 and 1 <= mo <= 12 and 1 <= d <= 31:
                    candidate = date(y, mo, d)
                    if best is None or candidate > best:
                        best = candidate
            except ValueError:
                continue
    if best:
        return best

    # 优先级 3：缺年份月日（补全当年）
    m = _DATE_PATTERN_NO_YEAR.search(text)
    if m:
        try:
            mo, d = int(m.group(1)), int(m.group(2))
            if 1 <= mo <= 12 and 1 <= d <= 31:
                return date(today.year, mo, d)
        except ValueError:
            pass

    return None


def _score_time_hint(
    link: ExtractedLink,
    target_date: date | None = None,
    date_to: date | None = None,
) -> int:
    """四色分流时间评分（0-30）。

    绿色（30）：日期在目标区间内
    黄色（10）：日期不在区间，差距 ≤ 15 天
    黑色（ 0）：日期不在区间，差距 > 15 天
    蓝色（15）：完全没找到日期（无罪推定）
    """
    # 收集所有日期信号，优先级：URL > 锚文本 > 周围文本
    found_date: date | None = None
    source = ""

    url_date = extract_url_date(link.url)
    if url_date:
        found_date = url_date
        source = "url"
    else:
        text_date = _extract_date_from_text(link.text)
        if text_date:
            found_date = text_date
            source = "text"
        else:
            ctx_date = _extract_date_from_text(link.surrounding_text)
            if ctx_date:
                found_date = ctx_date
                source = "context"

    # 无日期 → 蓝色：给基础分 15，允许入队
    if found_date is None:
        return 15

    # 有日期但无参照 → 20
    if target_date is None:
        return 20

    # 有日期 + 有参照 → 四色分流
    end_date = date_to or target_date
    if target_date <= found_date <= end_date:
        return 30  # 绿色：命中区间

    days_diff = min(
        abs((found_date - target_date).days),
        abs((found_date - end_date).days),
    )
    if days_diff <= 15:
        return 10  # 黄色：近似，不枪毙
    return 0       # 黑色：彻底淘汰


# ---------------------------------------------------------------------------
# 垃圾链接检测（自然淘汰，低分不出队）
# ---------------------------------------------------------------------------

_JUNK_PATTERNS = [
    re.compile(r"^#$"),
    re.compile(r"^javascript:", re.I),
    re.compile(r"^mailto:", re.I),
    re.compile(r"/tag[s]?/", re.I),
    re.compile(r"/search", re.I),
    re.compile(r"/login", re.I),
    re.compile(r"/register", re.I),
    re.compile(r"/rss", re.I),
    re.compile(r"/feed", re.I),
    re.compile(r"/comment", re.I),
    re.compile(r"\.(pdf|docx?|xlsx?|pptx?|zip|rar|7z|jpe?g|png|gif)$", re.I),
]


def _is_junk(url: str) -> bool:
    for p in _JUNK_PATTERNS:
        if p.search(url):
            return True
    return False


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def score_link_simple(url: str) -> int:
    """简单评分（仅基于 URL，无锚文本上下文）。用于 Sitemap/API 来源。"""
    if _is_junk(url):
        return 0
    depth_score = _score_url_depth(url)
    url_date = extract_url_date(url)
    time_score = 20 if url_date else 0
    return min(depth_score + time_score, 100)


def score_links(
    links: list[ExtractedLink],
    target_date: date | None = None,
    date_to: date | None = None,
) -> list[ScoredLink]:
    """批量评分，返回按 score 降序排列的 ScoredLink 列表。"""
    results: list[ScoredLink] = []
    for link in links:
        if _is_junk(link.url):
            continue
        text_score = _score_text_length(link.text)
        depth_score = _score_url_depth(link.url)
        time_score = _score_time_hint(link, target_date, date_to)
        total = min(text_score + depth_score + time_score, 100)
        results.append(ScoredLink(
            url=link.url,
            score=total,
            signals={
                "text_len_score": text_score,
                "depth_score": depth_score,
                "time_score": time_score,
            },
        ))
    results.sort(key=lambda x: x.score, reverse=True)
    return results
