"""ScoringFilter 单元测试：验证评分模型区分文章和导航页。"""
from datetime import date

from app.modules.discovery.scoring import ExtractedLink, score_links, score_link_simple


class TestScoringArticleVsNav:
    """文章页应得分高于导航/列表页。"""

    def test_long_text_article_scores_high(self):
        """长锚文本（文章标题）应得高分。"""
        links = [ExtractedLink(
            url="https://www.tsinghua.edu.cn/info/1002/122886.htm",
            text="清华大学举行2026年研究生毕业典礼暨学位授予仪式",
        )]
        scored = score_links(links)
        assert scored[0].score >= 60

    def test_short_text_nav_scores_low(self):
        """短锚文本（导航链接）应得低分。"""
        links = [ExtractedLink(
            url="https://www.tsinghua.edu.cn/jyjx.htm",
            text="教育教学",
        )]
        scored = score_links(links)
        assert scored[0].score <= 35

    def test_article_scores_higher_than_nav(self):
        """文章页得分应高于导航页。"""
        article = ExtractedLink(
            url="https://www.tsinghua.edu.cn/info/1002/122886.htm",
            text="清华大学举行2026年研究生毕业典礼暨学位授予仪式",
        )
        nav = ExtractedLink(
            url="https://www.tsinghua.edu.cn/jyjx.htm",
            text="教育教学",
        )
        scored = score_links([article, nav])
        scores = {s.url: s.score for s in scored}
        assert scores[article.url] > scores[nav.url]


class TestThreeTierDefense:
    """四色分流测试。"""

    TARGET = date(2026, 5, 4)
    DATE_TO = date(2026, 5, 7)

    def test_green_in_range(self):
        """绿色：日期在区间内 → 30 分。"""
        link = ExtractedLink(
            url="https://example.com/news/2026/05/05/article.htm",
            text="某篇文章",
        )
        scored = score_links([link], target_date=self.TARGET, date_to=self.DATE_TO)
        assert scored[0].signals["time_score"] == 30

    def test_yellow_close_date(self):
        """黄色：日期差距 ≤ 15 天 → 10 分。"""
        link = ExtractedLink(
            url="https://example.com/news/2026/04/25/article.htm",
            text="某篇文章",
        )
        scored = score_links([link], target_date=self.TARGET, date_to=self.DATE_TO)
        assert scored[0].signals["time_score"] == 10

    def test_black_old_date(self):
        """黑色：日期差距 > 15 天 → 0 分。"""
        link = ExtractedLink(
            url="https://example.com/news/2026/03/01/article.htm",
            text="某篇文章",
        )
        scored = score_links([link], target_date=self.TARGET, date_to=self.DATE_TO)
        assert scored[0].signals["time_score"] == 0

    def test_blue_no_date(self):
        """蓝色：无日期 → 15 分（无罪推定）。"""
        link = ExtractedLink(
            url="https://example.com/info/1002/122886.htm",
            text="某篇文章",
        )
        scored = score_links([link], target_date=self.TARGET, date_to=self.DATE_TO)
        assert scored[0].signals["time_score"] == 15

    def test_blue_not_zero(self):
        """蓝色不能是 0 分（会被当作黑色淘汰）。"""
        link = ExtractedLink(
            url="https://www.tsinghua.edu.cn/info/1177/125704.htm",
            text="清华大学某篇新闻文章标题",
        )
        scored = score_links([link], target_date=self.TARGET, date_to=self.DATE_TO)
        assert scored[0].signals["time_score"] > 0


class TestMultiStageDateParsing:
    """多级降级日期解析测试。"""

    def test_relative_hours_ago(self):
        """相对时间：3小时前 → 今天。"""
        from app.modules.discovery.scoring import _extract_date_from_text
        result = _extract_date_from_text("3小时前发布")
        assert result == date.today()

    def test_relative_yesterday(self):
        """相对时间：昨天。"""
        from datetime import timedelta
        from app.modules.discovery.scoring import _extract_date_from_text
        result = _extract_date_from_text("昨天发布")
        assert result == date.today() - timedelta(days=1)

    def test_relative_days_ago(self):
        """相对时间：5天前。"""
        from datetime import timedelta
        from app.modules.discovery.scoring import _extract_date_from_text
        result = _extract_date_from_text("5天前更新")
        assert result == date.today() - timedelta(days=5)

    def test_standard_absolute(self):
        """标准绝对日期。"""
        from app.modules.discovery.scoring import _extract_date_from_text
        result = _extract_date_from_text("2026年5月8日发布")
        assert result == date(2026, 5, 8)

    def test_missing_year(self):
        """缺年份月日：补全当年。"""
        from app.modules.discovery.scoring import _extract_date_from_text
        result = _extract_date_from_text("05-08发布")
        assert result == date(date.today().year, 5, 8)

    def test_context_date_in_surrounding(self):
        """周围文本中的日期应被提取。"""
        link = ExtractedLink(
            url="https://example.com/info/1002/122886.htm",
            text="某篇文章",
            surrounding_text="2026年5月5日 清华大学新闻",
        )
        scored = score_links([link], target_date=date(2026, 5, 4), date_to=date(2026, 5, 7))
        assert scored[0].signals["time_score"] == 30  # 绿色：周围文本日期在区间内


class TestScoreLinkSimple:
    """score_link_simple（仅基于 URL）测试。"""

    def test_article_url_scores_reasonably(self):
        score = score_link_simple("https://www.tsinghua.edu.cn/info/1002/122886.htm")
        assert score >= 15

    def test_junk_url_scores_zero(self):
        score = score_link_simple("https://example.com/login")
        assert score == 0

    def test_pdf_url_scores_zero(self):
        score = score_link_simple("https://example.com/doc.pdf")
        assert score == 0


class TestJunkFiltering:
    """垃圾链接应被过滤（不出现在结果中）。"""

    def test_javascript_link_filtered(self):
        links = [ExtractedLink(url="javascript:void(0)", text="点击")]
        scored = score_links(links)
        assert len(scored) == 0

    def test_pdf_link_filtered(self):
        links = [ExtractedLink(url="https://example.com/doc.pdf", text="下载")]
        scored = score_links(links)
        assert len(scored) == 0
