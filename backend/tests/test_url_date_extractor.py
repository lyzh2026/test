"""extract_url_date / is_url_date_in_range 单元测试。"""
from datetime import date

import pytest

from app.modules.discovery.link_extractor import extract_url_date, is_url_date_in_range


class TestExtractUrlDate:
    """extract_url_date 各种 URL 模式测试。"""

    # === 精确日期 (/YYYY-MM-DD/) ===

    def test_day_slash_format(self):
        assert extract_url_date("https://example.com/news/2026/05/21/title.html") == date(2026, 5, 21)

    def test_day_dash_format(self):
        assert extract_url_date("https://example.com/2023-01-15/article") == date(2023, 1, 15)

    def test_day_single_digit(self):
        assert extract_url_date("https://example.com/2024/3/7/post") == date(2024, 3, 7)

    # === 年月 (/YYYY-MM/ or /YYYY/MM/) ===

    def test_month_slash_format(self):
        assert extract_url_date("https://example.com/2025/04/article") == date(2025, 4, 1)

    def test_month_dash_format(self):
        assert extract_url_date("https://example.com/news/2024-12/detail.html") == date(2024, 12, 1)

    # === 紧凑格式 (/YYYYMMDD_ or /YYYYMM/) ===

    def test_compact_date_with_suffix(self):
        assert extract_url_date("https://example.com/20260521_12345.html") == date(2026, 5, 1)

    def test_compact_month(self):
        assert extract_url_date("https://example.com/202605/article") == date(2026, 5, 1)

    # === 年份 (/YYYY/) ===

    def test_year_only(self):
        assert extract_url_date("https://example.com/2024/article") == date(2024, 1, 1)

    # === 无日期 URL ===

    def test_no_date_returns_none(self):
        assert extract_url_date("https://example.com/news/latest.html") is None

    def test_short_path_returns_none(self):
        assert extract_url_date("https://example.com/") is None

    def test_empty_path_returns_none(self):
        assert extract_url_date("https://example.com") is None

    # === 边界情况 ===

    def test_year_out_of_range_1999_returns_none(self):
        assert extract_url_date("https://example.com/1999/05/article") is None

    def test_year_out_of_range_2100_returns_none(self):
        assert extract_url_date("https://example.com/2100/01/article") is None

    def test_invalid_month_0_returns_none(self):
        assert extract_url_date("https://example.com/2026/00/article") is None

    def test_invalid_month_13_returns_none(self):
        assert extract_url_date("https://example.com/2026/13/article") is None

    def test_query_params_ignored(self):
        assert extract_url_date("https://example.com/2026/05/article?page=1") == date(2026, 5, 1)

    def test_fragment_ignored(self):
        assert extract_url_date("https://example.com/2026/05/article#section") == date(2026, 5, 1)

    # === 优先级：精确日期 > 年月 ===

    def test_full_path_prefers_day_over_month(self):
        url = "https://example.com/2026/05/21/14/30/article"
        assert extract_url_date(url) == date(2026, 5, 21)

    # === 真实 URL 样本 ===

    def test_gov_cn_style(self):
        url = "https://www.gov.cn/zhengce/zhengceku/202504/content_6951234.html"
        assert extract_url_date(url) == date(2025, 4, 1)

    def test_university_style_compact(self):
        # 紧凑日期后紧跟更多数字再接分隔符 → 不匹配（避免误提取）
        url = "https://www.tsinghua.edu.cn/info/1234/20260515234567.htm"
        assert extract_url_date(url) is None

    def test_university_style_underscore(self):
        # 紧凑日期后接下划线 → 正常提取
        url = "https://www.tsinghua.edu.cn/info/20260515_234567.htm"
        assert extract_url_date(url) == date(2026, 5, 1)

    def test_news_style(self):
        url = "https://news.example.com/2026/05/21/c_123456.htm"
        assert extract_url_date(url) == date(2026, 5, 21)


class TestIsUrlDateInRange:
    """is_url_date_in_range 粒度感知测试。"""

    TARGET = date(2026, 5, 7)
    DATE_TO = date(2026, 5, 9)

    # === 日级粒度 ===

    def test_day_in_range(self):
        url = "https://example.com/news/2026/05/08/article.htm"
        assert is_url_date_in_range(url, self.TARGET, self.DATE_TO) is True

    def test_day_before_range(self):
        url = "https://example.com/news/2026/05/05/article.htm"
        assert is_url_date_in_range(url, self.TARGET, self.DATE_TO) is False

    def test_day_after_range(self):
        url = "https://example.com/news/2026/05/15/article.htm"
        assert is_url_date_in_range(url, self.TARGET, self.DATE_TO) is False

    def test_day_wrong_year(self):
        url = "http://www.gov.cn/lianbo/2023-05/05/content_5754181.htm"
        assert is_url_date_in_range(url, self.TARGET, self.DATE_TO) is False

    # === 月级粒度（应保留整月） ===

    def test_month_overlaps_range(self):
        """月级日期 /202605/ 应保留（整月与 5/7-5/9 重叠）。"""
        url = "https://www.gov.cn/yaowen/liebiao/202605/content_7069661.htm"
        assert is_url_date_in_range(url, self.TARGET, self.DATE_TO) is True

    def test_month_before_range(self):
        """月级日期 /202604/ 在 5/7 之前，应过滤。"""
        url = "https://www.gov.cn/yaowen/liebiao/202604/content_7064519.htm"
        assert is_url_date_in_range(url, self.TARGET, self.DATE_TO) is False

    def test_month_after_range(self):
        """月级日期 /202606/ 在 5/9 之后，应过滤。"""
        url = "https://www.gov.cn/yaowen/liebiao/202606/content_1234567.htm"
        assert is_url_date_in_range(url, self.TARGET, self.DATE_TO) is False

    def test_month_wrong_year(self):
        """2023-05 月级，年份不对，应过滤。"""
        url = "https://www.gov.cn/yaowen/liebiao/202305/content_5754181.htm"
        assert is_url_date_in_range(url, self.TARGET, self.DATE_TO) is False

    # === 无日期 ===

    def test_no_date_returns_none(self):
        url = "https://www.gov.cn/index.htm"
        assert is_url_date_in_range(url, self.TARGET, self.DATE_TO) is None
