# 周报分发系统 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现周报自动分发功能：每周一 8:30 发送上周文章全量分类周报，支持邮件 + 飞书 Webhook 双通道，并在管理后台配置。

**Architecture:** 复用现有 APScheduler 定时触发，新增 distribution 模块（service + adapters），report 生成后按通道适配器分发。数据模型 2 张表（config + log），前端嵌入 admin 模块。

**Tech Stack:** FastAPI + SQLAlchemy + APScheduler, smtplib (邮件), httpx (Webhook), React shadcn 风格 UI

---

### Task 1: 数据模型 + Alembic 迁移

**Files:**
- Create: `backend/app/models/distribution.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/0003_add_distribution_tables.py`
- Modify: `backend/alembic/env.py`

- [ ] **Step 1: 创建 DistributionConfig 和 DistributionLog 模型**

`backend/app/models/distribution.py`:

```python
"""distribution_config / distribution_log 表。"""
from datetime import datetime
import uuid

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DistributionConfig(Base):
    __tablename__ = "distribution_config"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel_type: Mapped[str] = mapped_column(String(20), nullable=False)  # email | webhook
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DistributionLog(Base):
    __tablename__ = "distribution_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    config_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    config_name: Mapped[str | None] = mapped_column(String(100))
    channel_type: Mapped[str | None] = mapped_column(String(20))
    report_week: Mapped[str] = mapped_column(String(10), nullable=False)
    date_range_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    date_range_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # success | failed
    article_count: Mapped[int] = mapped_column(Integer, default=0)
    category_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 2: 注册模型到 __init__**

Edit `backend/app/models/__init__.py`:

```python
from app.models.allowed_domain import AllowedDomain
from app.models.ai_analysis import AIAnalysis
from app.models.article import Article
from app.models.crawler_task import CrawlerTask
from app.models.distribution import DistributionConfig, DistributionLog

__all__ = ["Article", "AIAnalysis", "CrawlerTask", "AllowedDomain", "DistributionConfig", "DistributionLog"]
```

- [ ] **Step 3: 更新 alembic env.py 导入新模型**

Edit `backend/alembic/env.py`, line 9 — add `distribution` to the import:

```python
from app.models import article, ai_analysis, crawler_task, allowed_domain, distribution  # noqa: F401
```

- [ ] **Step 4: 创建迁移脚本**

`backend/alembic/versions/0003_add_distribution_tables.py`:

```python
"""add distribution_config / distribution_log tables.

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # distribution_config
    op.create_table(
        "distribution_config",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("channel_type", sa.String(20), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("config", postgresql.JSONB, nullable=False),
        sa.Column("enabled", sa.Boolean, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # distribution_log
    op.create_table(
        "distribution_log",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("config_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("config_name", sa.String(100)),
        sa.Column("channel_type", sa.String(20)),
        sa.Column("report_week", sa.String(10), nullable=False),
        sa.Column("date_range_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("date_range_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("article_count", sa.Integer, server_default="0"),
        sa.Column("category_count", sa.Integer, server_default="0"),
        sa.Column("error_message", sa.Text),
        sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_distribution_log_week", "distribution_log", ["report_week"])
    op.create_index("idx_distribution_log_status", "distribution_log", ["status"])


def downgrade() -> None:
    op.drop_index("idx_distribution_log_status", table_name="distribution_log")
    op.drop_index("idx_distribution_log_week", table_name="distribution_log")
    op.drop_table("distribution_log")
    op.drop_table("distribution_config")
```

- [ ] **Step 5: 运行迁移验证**

```bash
cd backend && alembic upgrade head
```

Expected output: `INFO  [alembic.runtime.migration] Running upgrade 0002 -> 0003`

---

### Task 2: 周报数据结构 + 服务核心

**Files:**
- Create: `backend/app/modules/distribution/__init__.py`
- Create: `backend/app/modules/distribution/schemas.py`
- Create: `backend/app/modules/distribution/service.py`
- Create: `backend/tests/test_distribution_service.py`

- [ ] **Step 1: 创建模块包**

`backend/app/modules/distribution/__init__.py` — empty file.

- [ ] **Step 2: 定义 WeeklyReport Pydantic schemas**

`backend/app/modules/distribution/schemas.py`:

```python
"""周报数据结构和 API schemas。"""
from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class ArticleItem(BaseModel):
    title: str
    summary: str
    url: str
    publish_date: date
    source_unit: str


class CategoryGroup(BaseModel):
    name: str
    articles: list[ArticleItem]


class ReportStats(BaseModel):
    total_articles: int
    total_categories: int


class WeeklyReport(BaseModel):
    year_week: str
    date_range_start: date
    date_range_end: date
    categories: list[CategoryGroup]
    stats: ReportStats


# --- API Schemas ---

class ConfigCreate(BaseModel):
    channel_type: str  # email | webhook
    name: str
    config: dict
    enabled: bool = True


class ConfigUpdate(BaseModel):
    name: Optional[str] = None
    config: Optional[dict] = None
    enabled: Optional[bool] = None


class ConfigResponse(BaseModel):
    id: str
    channel_type: str
    name: str
    config: dict
    enabled: bool
    created_at: Optional[datetime]
    updated_at: Optional[datetime]


class LogResponse(BaseModel):
    id: str
    config_name: Optional[str]
    channel_type: Optional[str]
    report_week: str
    status: str
    article_count: int
    category_count: int
    error_message: Optional[str]
    sent_at: Optional[datetime]
```

- [ ] **Step 3: 实现 WeeklyDigestService**

`backend/app/modules/distribution/service.py`:

```python
"""周报生成与分发核心服务。"""
import logging
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.ai_analysis import AIAnalysis
from app.models.article import Article
from app.modules.distribution.schemas import ArticleItem, CategoryGroup, ReportStats, WeeklyReport

logger = logging.getLogger("shixun.distribution")


def _parse_year_week(year_week: str) -> tuple[date, date]:
    """将 '2026-W18' 转换为 (周一日期, 周日日期)。"""
    from datetime import datetime as dt

    year = int(year_week[:4])
    week = int(year_week[6:])
    # ISO week: 周一是第1天
    jan4 = date(year, 1, 4)
    start_of_week1 = jan4 - timedelta(days=jan4.isoweekday() - 1)
    monday = start_of_week1 + timedelta(weeks=week - 1)
    sunday = monday + timedelta(days=6)
    return monday, sunday


def _get_current_year_week() -> str:
    """获取上周的 year_week 字符串（因为周报发的是上周数据）。"""
    today = date.today()
    # 如果是周一，上周 = today - 7 天；否则 = today 的上周一
    iso = today.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


class WeeklyDigestService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def generate_weekly_report(self, year_week: str | None = None) -> WeeklyReport:
        """生成指定周的周报。"""
        if year_week is None:
            year_week = _get_current_year_week()

        monday, sunday = _parse_year_week(year_week)

        # 查询本周已处理的文章，含 AI 分析
        stmt = (
            select(Article)
            .options(joinedload(Article.ai_analysis))
            .where(
                Article.publish_date.between(monday, sunday),
                Article.status == "processed",
            )
            .order_by(Article.publish_date.desc())
        )
        result = await self.session.execute(stmt)
        articles = result.unique().scalars().all()

        # 按分类分组
        category_map: dict[str, list[ArticleItem]] = {}
        for article in articles:
            cats = []
            if article.ai_analysis and article.ai_analysis.categories:
                cats = article.ai_analysis.categories
            # 取第一个分类，无分类归入"其他"
            cat_name = cats[0] if cats else "其他"

            item = ArticleItem(
                title=article.original_title,
                summary=article.ai_analysis.summary if article.ai_analysis else "",
                url=article.original_link,
                publish_date=article.publish_date,
                source_unit=article.source_unit or "",
            )
            if cat_name not in category_map:
                category_map[cat_name] = []
            category_map[cat_name].append(item)

        # 按文章数降序排列，不足 2 篇的合并到"其他"
        sorted_cats = sorted(category_map.items(), key=lambda x: len(x[1]), reverse=True)
        merged: list[CategoryGroup] = []
        others: list[ArticleItem] = []
        for name, items in sorted_cats:
            if len(items) < 2:
                others.extend(items)
            else:
                merged.append(CategoryGroup(name=name, articles=items))

        if others:
            merged.append(CategoryGroup(name="其他", articles=others))

        return WeeklyReport(
            year_week=year_week,
            date_range_start=monday,
            date_range_end=sunday,
            categories=merged,
            stats=ReportStats(
                total_articles=len(articles),
                total_categories=len(merged),
            ),
        )
```

- [ ] **Step 4: 写服务单元测试**

`backend/tests/test_distribution_service.py`:

```python
"""测试 WeeklyDigestService。"""
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from app.models.article import Article
from app.models.ai_analysis import AIAnalysis
from app.modules.distribution.schemas import WeeklyReport
from app.modules.distribution.service import WeeklyDigestService, _parse_year_week


class TestParseYearWeek:
    def test_2026_w18(self):
        monday, sunday = _parse_year_week("2026-W18")
        assert monday == date(2026, 4, 27)
        assert sunday == date(2026, 5, 3)

    def test_2026_w01(self):
        monday, sunday = _parse_year_week("2026-W01")
        assert monday == date(2025, 12, 29)
        assert sunday == date(2026, 1, 4)


class TestGenerateWeeklyReport:
    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    def _make_article(self, title: str, cat: str, day_offset: int = 0):
        article = MagicMock(spec=Article)
        article.original_title = title
        article.original_link = f"https://example.com/{title}"
        article.publish_date = date(2026, 4, 27 + day_offset)
        article.source_unit = "测试来源"
        article.status = "processed"
        article.ai_analysis = MagicMock(spec=AIAnalysis)
        article.ai_analysis.summary = f"{title}的摘要"
        article.ai_analysis.categories = [cat]
        return article

    @pytest.mark.asyncio
    async def test_happy_path(self, mock_session):
        """正常生成周报：文章按分类分组，降序排列。"""
        articles = [
            self._make_article("文章A", "政策法规", 0),
            self._make_article("文章B", "科技创新", 1),
            self._make_article("文章C", "政策法规", 2),
        ]
        mock_result = MagicMock()
        mock_result.unique.return_value.scalars.return_value.all.return_value = articles
        mock_session.execute = AsyncMock(return_value=mock_result)

        svc = WeeklyDigestService(mock_session)
        report = await svc.generate_weekly_report("2026-W18")

        assert isinstance(report, WeeklyReport)
        assert report.year_week == "2026-W18"
        assert report.stats.total_articles == 3
        # 政策法规有2篇 -> 独立分类；科技创新仅1篇 -> 合并到"其他"
        cat_names = [c.name for c in report.categories]
        assert "政策法规" in cat_names
        assert "其他" in cat_names  # 科技创新被合并
        assert "科技创新" not in cat_names

    @pytest.mark.asyncio
    async def test_empty_week(self, mock_session):
        """无文章时正常返回空列表。"""
        mock_result = MagicMock()
        mock_result.unique.return_value.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        svc = WeeklyDigestService(mock_session)
        report = await svc.generate_weekly_report("2026-W18")

        assert report.stats.total_articles == 0
        assert report.categories == []

    @pytest.mark.asyncio
    async def test_no_ai_analysis(self, mock_session):
        """文章有 AI 分析结果时正确读取。"""
        article = self._make_article("无分析文章", "政策法规", 0)
        article.ai_analysis = None  # 无 AI 分析
        mock_result = MagicMock()
        mock_result.unique.return_value.scalars.return_value.all.return_value = [article]
        mock_session.execute = AsyncMock(return_value=mock_result)

        svc = WeeklyDigestService(mock_session)
        report = await svc.generate_weekly_report("2026-W18")

        assert report.stats.total_articles == 1
        assert report.categories[0].articles[0].summary == ""
```

- [ ] **Step 5: 运行测试**

```bash
cd backend && python -m pytest tests/test_distribution_service.py -v
```

Expected: 4 tests PASS

---

### Task 3: 通道适配器基类 + EmailAdapter

**Files:**
- Create: `backend/app/modules/distribution/adapters/__init__.py`
- Create: `backend/app/modules/distribution/adapters/base.py`
- Create: `backend/app/modules/distribution/adapters/email_adapter.py`
- Create: `backend/tests/test_email_adapter.py`

- [ ] **Step 1: 创建适配器包**

`backend/app/modules/distribution/adapters/__init__.py` — empty file.

- [ ] **Step 2: 定义抽象基类**

`backend/app/modules/distribution/adapters/base.py`:

```python
"""分发通道适配器基类。"""
from abc import ABC, abstractmethod

from app.modules.distribution.schemas import WeeklyReport


class DistributionAdapter(ABC):
    """适配器接口：每个通道实现 send 方法。"""

    @abstractmethod
    async def send(self, report: WeeklyReport, config: dict) -> bool:
        """发送周报，成功返回 True，失败抛异常。"""
        ...
```

- [ ] **Step 3: 实现 EmailAdapter**

`backend/app/modules/distribution/adapters/email_adapter.py`:

```python
"""邮件通道适配器。"""
import logging
import smtplib
from email.mime.text import MIMEText

from app.modules.distribution.adapters.base import DistributionAdapter
from app.modules.distribution.schemas import WeeklyReport

logger = logging.getLogger("shixun.distribution.email")


def _build_html(report: WeeklyReport) -> str:
    """渲染周报 HTML 邮件正文。"""
    rows = ""
    for cat in report.categories:
        articles_html = ""
        for a in cat.articles:
            articles_html += f"""\
<tr style="border-bottom:1px solid #eee;">
  <td style="padding:10px 8px;vertical-align:top;">
    <a href="{a.url}" style="color:#1a73e8;text-decoration:none;font-weight:500;">{a.title}</a>
    <div style="color:#666;font-size:12px;margin-top:2px;">{a.source_unit} · {a.publish_date}</div>
    <div style="color:#333;font-size:13px;margin-top:4px;line-height:1.5;">{a.summary}</div>
  </td>
</tr>"""
        rows += f"""\
<tr><td style="padding:12px 0 4px;"><h3 style="margin:0;color:#333;">📋 {cat.name}（{len(cat.articles)}篇）</h3></td></tr>
{articles_html}"""

    return f"""\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,sans-serif;padding:20px;background:#f5f5f5;">
<div style="max-width:640px;margin:0 auto;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.1);">
<div style="background:#1a73e8;padding:20px;color:#fff;">
  <h1 style="margin:0;font-size:20px;">拾讯周报 {report.year_week}</h1>
  <p style="margin:4px 0 0;font-size:13px;opacity:0.9;">{report.date_range_start} ~ {report.date_range_end}</p>
</div>
<div style="padding:16px 20px;background:#e8f0fe;font-size:13px;color:#555;">
  本周共采集 <strong>{report.stats.total_articles}</strong> 篇文章，覆盖 <strong>{report.stats.total_categories}</strong> 个分类
</div>
<div style="padding:0 20px 20px;">
  <table style="width:100%;border-collapse:collapse;">
    {rows}
  </table>
</div>
<div style="padding:12px 20px;font-size:11px;color:#999;border-top:1px solid #eee;text-align:center;">
  本邮件由拾讯系统自动发送
</div>
</div>
</body>
</html>"""


class EmailAdapter(DistributionAdapter):
    """SMTP 邮件适配器。"""

    async def send(self, report: WeeklyReport, config: dict) -> bool:
        to_addrs = config.get("to_addrs", [])
        if not to_addrs:
            raise ValueError("收件人列表为空")

        html = _build_html(report)
        msg = MIMEText(html, "html", "utf-8")
        msg["Subject"] = f"拾讯周报 {report.year_week}（{report.date_range_start} ~ {report.date_range_end}）"
        msg["From"] = config.get("from_addr", config.get("smtp_user", ""))
        msg["To"] = ", ".join(to_addrs)

        use_tls = config.get("use_tls", True)
        smtp_host = config["smtp_host"]
        smtp_port = config["smtp_port"]
        smtp_user = config["smtp_user"]
        smtp_pass = config["smtp_pass"]

        loop = asyncio.get_running_loop()

        def _send():
            if use_tls:
                with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
                    server.login(smtp_user, smtp_pass)
                    server.sendmail(smtp_user, to_addrs, msg.as_string())
            else:
                with smtplib.SMTP(smtp_host, smtp_port) as server:
                    server.starttls()
                    server.login(smtp_user, smtp_pass)
                    server.sendmail(smtp_user, to_addrs, msg.as_string())

        try:
            await loop.run_in_executor(None, _send)
            logger.info("邮件周报发送成功: %s -> %s", smtp_user, to_addrs)
            return True
        except Exception as e:
            logger.error("邮件发送失败: %s", e)
            raise

    # 添加这个 import（文件顶部也有）
```

Wait — fix the import. The file needs `import asyncio` at the top. Let me fix:

```python
"""邮件通道适配器。"""
import asyncio
import logging
import smtplib
from email.mime.text import MIMEText

from app.modules.distribution.adapters.base import DistributionAdapter
from app.modules.distribution.schemas import WeeklyReport

logger = logging.getLogger("shixun.distribution.email")


# ... (rest same as above)
```

- [ ] **Step 4: 写 EmailAdapter 单元测试**

`backend/tests/test_email_adapter.py`:

```python
"""测试 EmailAdapter。"""
from datetime import date
from unittest.mock import patch

import pytest

from app.modules.distribution.adapters.email_adapter import EmailAdapter, _build_html
from app.modules.distribution.schemas import ArticleItem, CategoryGroup, ReportStats, WeeklyReport


@pytest.fixture
def sample_report():
    return WeeklyReport(
        year_week="2026-W18",
        date_range_start=date(2026, 4, 27),
        date_range_end=date(2026, 5, 3),
        categories=[
            CategoryGroup(
                name="政策法规",
                articles=[
                    ArticleItem(title="政策A", summary="摘要A", url="https://a.com", publish_date=date(2026, 4, 28), source_unit="来源A"),
                    ArticleItem(title="政策B", summary="摘要B", url="https://b.com", publish_date=date(2026, 4, 29), source_unit="来源B"),
                ],
            ),
        ],
        stats=ReportStats(total_articles=2, total_categories=1),
    )


class TestBuildHtml:
    def test_contains_title(self, sample_report):
        html = _build_html(sample_report)
        assert "拾讯周报 2026-W18" in html
        assert "2026-04-27" in html
        assert "2026-05-03" in html
        assert "2" in html  # total_articles
        assert "政策法规" in html
        assert "政策A" in html
        assert "摘要A" in html

    def test_empty_report(self):
        report = WeeklyReport(
            year_week="2026-W18",
            date_range_start=date(2026, 4, 27),
            date_range_end=date(2026, 5, 3),
            categories=[],
            stats=ReportStats(total_articles=0, total_categories=0),
        )
        html = _build_html(report)
        assert "0" in html
        assert "拾讯周报" in html


class TestEmailAdapterSend:
    @pytest.mark.asyncio
    async def test_send_success(self, sample_report):
        adapter = EmailAdapter()
        config = {
            "smtp_host": "smtp.test.com",
            "smtp_port": 465,
            "smtp_user": "user@test.com",
            "smtp_pass": "pass",
            "from_addr": "from@test.com",
            "to_addrs": ["to@test.com"],
            "use_tls": True,
        }
        with patch("smtplib.SMTP_SSL") as mock_smtp:
            mock_instance = mock_smtp.return_value.__enter__.return_value
            result = await adapter.send(sample_report, config)
            assert result is True
            mock_instance.login.assert_called_once_with("user@test.com", "pass")
            mock_instance.sendmail.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_empty_recipients(self, sample_report):
        adapter = EmailAdapter()
        config = {"to_addrs": [], "smtp_host": "x", "smtp_port": 25, "smtp_user": "x", "smtp_pass": "x"}
        with pytest.raises(ValueError, match="收件人列表为空"):
            await adapter.send(sample_report, config)
```

- [ ] **Step 5: 运行测试**

```bash
cd backend && python -m pytest tests/test_email_adapter.py -v
```

Expected: 4 tests PASS

---

### Task 4: WebhookAdapter（飞书）

**Files:**
- Create: `backend/app/modules/distribution/adapters/webhook_adapter.py`
- Create: `backend/tests/test_webhook_adapter.py`

- [ ] **Step 1: 实现飞书 Webhook 适配器**

`backend/app/modules/distribution/adapters/webhook_adapter.py`:

```python
"""飞书 Webhook 通道适配器。"""
import logging

import httpx

from app.modules.distribution.adapters.base import DistributionAdapter
from app.modules.distribution.schemas import WeeklyReport

logger = logging.getLogger("shixun.distribution.webhook")

# 飞书消息卡片最大元素数（约 50KB 限制）
_MAX_ELEMENTS = 20


def _build_feishu_card(report: WeeklyReport) -> dict:
    """构建飞书消息卡片。"""
    header_text = f"拾讯周报 {report.year_week}（{report.date_range_start} ~ {report.date_range_end}）"

    elements = [
        {
            "tag": "markdown",
            "content": f"本周共采集 **{report.stats.total_articles}** 篇文章，覆盖 **{report.stats.total_categories}** 个分类",
        },
        {"tag": "hr"},
    ]

    for cat in report.categories:
        lines = [f"**📋 {cat.name}（{len(cat.articles)}篇）**"]
        for a in cat.articles[:10]:  # 每个分类最多 10 篇
            lines.append(f"[{a.title}]({a.url}) · {a.publish_date}")
            lines.append(f"> {a.summary}")
        elements.append({"tag": "markdown", "content": "\n".join(lines)})
        elements.append({"tag": "hr"})

    # 截断防止超限
    if len(elements) > _MAX_ELEMENTS:
        elements = elements[:_MAX_ELEMENTS]
        elements.append({"tag": "markdown", "content": f"… 共 {report.stats.total_articles} 篇，完整内容请查看邮件"})

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": header_text},
            },
            "elements": elements,
        },
    }


class WebhookAdapter(DistributionAdapter):
    """通用 Webhook 适配器，按 platform 选择消息格式。"""

    async def send(self, report: WeeklyReport, config: dict) -> bool:
        url = config.get("url", "")
        if not url:
            raise ValueError("Webhook URL 为空")

        platform = config.get("platform", "feishu")

        if platform == "feishu":
            payload = _build_feishu_card(report)
        else:
            raise ValueError(f"不支持的 Webhook 平台: {platform}")

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code >= 400:
                raise RuntimeError(f"Webhook 发送失败: HTTP {resp.status_code} {resp.text[:200]}")

        logger.info("Webhook 周报发送成功: %s", platform)
        return True
```

- [ ] **Step 2: 写 WebhookAdapter 单元测试**

`backend/tests/test_webhook_adapter.py`:

```python
"""测试 WebhookAdapter（飞书）。"""
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from app.modules.distribution.adapters.webhook_adapter import WebhookAdapter, _build_feishu_card
from app.modules.distribution.schemas import ArticleItem, CategoryGroup, ReportStats, WeeklyReport


@pytest.fixture
def sample_report():
    return WeeklyReport(
        year_week="2026-W18",
        date_range_start=date(2026, 4, 27),
        date_range_end=date(2026, 5, 3),
        categories=[
            CategoryGroup(
                name="政策法规",
                articles=[
                    ArticleItem(title="政策A", summary="摘要A", url="https://a.com", publish_date=date(2026, 4, 28), source_unit="来源A"),
                ],
            ),
        ],
        stats=ReportStats(total_articles=1, total_categories=1),
    )


class TestBuildFeishuCard:
    def test_card_structure(self, sample_report):
        card = _build_feishu_card(sample_report)
        assert card["msg_type"] == "interactive"
        assert "拾讯周报 2026-W18" in card["card"]["header"]["title"]["content"]
        assert len(card["card"]["elements"]) > 0

    def test_header_contains_date(self, sample_report):
        card = _build_feishu_card(sample_report)
        header = card["card"]["header"]["title"]["content"]
        assert "2026-04-27" in header
        assert "2026-05-03" in header


class TestWebhookAdapterSend:
    @pytest.mark.asyncio
    async def test_send_success(self, sample_report):
        adapter = WebhookAdapter()
        config = {"url": "https://open.feishu.cn/webhook/test", "platform": "feishu"}
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = mock_client.return_value.__aenter__.return_value
            resp = AsyncMock()
            resp.status_code = 200
            mock_instance.post = AsyncMock(return_value=resp)
            result = await adapter.send(sample_report, config)
            assert result is True

    @pytest.mark.asyncio
    async def test_send_http_error(self, sample_report):
        adapter = WebhookAdapter()
        config = {"url": "https://invalid.url", "platform": "feishu"}
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = mock_client.return_value.__aenter__.return_value
            resp = AsyncMock()
            resp.status_code = 403
            resp.text = "forbidden"
            mock_instance.post = AsyncMock(return_value=resp)
            with pytest.raises(RuntimeError, match="HTTP 403"):
                await adapter.send(sample_report, config)

    @pytest.mark.asyncio
    async def test_empty_url(self, sample_report):
        adapter = WebhookAdapter()
        with pytest.raises(ValueError, match="Webhook URL 为空"):
            await adapter.send(sample_report, {"url": "", "platform": "feishu"})
```

- [ ] **Step 3: 运行测试**

```bash
cd backend && python -m pytest tests/test_webhook_adapter.py -v
```

Expected: 5 tests PASS

---

### Task 5: API 路由

**Files:**
- Create: `backend/app/modules/distribution/routes.py`

- [ ] **Step 1: 实现 distribution API CRUD**

`backend/app/modules/distribution/routes.py`:

```python
"""分发配置和发送日志 API。"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.dependencies.auth import current_admin
from app.models.distribution import DistributionConfig, DistributionLog
from app.utils.response import error, success

logger = logging.getLogger("shixun.distribution")

router = APIRouter(prefix="/api/v1/distribution", tags=["distribution"])


def _serialize_config(item: DistributionConfig) -> dict:
    return {
        "id": str(item.id),
        "channel_type": item.channel_type,
        "name": item.name,
        "config": item.config,
        "enabled": item.enabled,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def _serialize_log(item: DistributionLog) -> dict:
    return {
        "id": str(item.id),
        "config_name": item.config_name,
        "channel_type": item.channel_type,
        "report_week": item.report_week,
        "status": item.status,
        "article_count": item.article_count,
        "category_count": item.category_count,
        "error_message": item.error_message,
        "sent_at": item.sent_at.isoformat() if item.sent_at else None,
    }


# === 通道配置 CRUD ===

@router.get("/configs")
async def list_configs(
    request: Request,
    _: object = Depends(current_admin),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(DistributionConfig).order_by(DistributionConfig.created_at.desc())
    )
    items = result.scalars().all()
    return success({"items": [_serialize_config(item) for item in items]}, request=request)


@router.post("/configs")
async def create_config(
    payload: dict,
    request: Request,
    _: object = Depends(current_admin),
    session: AsyncSession = Depends(get_session),
):
    channel_type = payload.get("channel_type", "").strip()
    name = payload.get("name", "").strip()
    config = payload.get("config", {})
    enabled = payload.get("enabled", True)

    if not channel_type:
        return error(1001, "channel_type 不能为空", http_status=400, request=request)
    if channel_type not in ("email", "webhook"):
        return error(1001, "channel_type 必须为 email 或 webhook", http_status=400, request=request)
    if not name:
        return error(1001, "name 不能为空", http_status=400, request=request)
    if not config:
        return error(1001, "config 不能为空", http_status=400, request=request)

    item = DistributionConfig(
        channel_type=channel_type,
        name=name,
        config=config,
        enabled=enabled,
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return success(_serialize_config(item), request=request)


@router.put("/configs/{item_id}")
async def update_config(
    item_id: str,
    payload: dict,
    request: Request,
    _: object = Depends(current_admin),
    session: AsyncSession = Depends(get_session),
):
    item = await session.get(DistributionConfig, item_id)
    if not item:
        return error(1002, "配置不存在", http_status=404, request=request)

    if "name" in payload and payload["name"]:
        item.name = payload["name"].strip()
    if "config" in payload and payload["config"]:
        item.config = payload["config"]
    if "enabled" in payload:
        item.enabled = bool(payload["enabled"])
    if "channel_type" in payload:
        item.channel_type = payload["channel_type"]
    item.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(item)
    return success(_serialize_config(item), request=request)


@router.delete("/configs/{item_id}")
async def delete_config(
    item_id: str,
    request: Request,
    _: object = Depends(current_admin),
    session: AsyncSession = Depends(get_session),
):
    item = await session.get(DistributionConfig, item_id)
    if not item:
        return error(1002, "配置不存在", http_status=404, request=request)
    await session.delete(item)
    await session.commit()
    return success({"id": item_id}, request=request)


@router.patch("/configs/{item_id}/toggle")
async def toggle_config(
    item_id: str,
    request: Request,
    _: object = Depends(current_admin),
    session: AsyncSession = Depends(get_session),
):
    item = await session.get(DistributionConfig, item_id)
    if not item:
        return error(1002, "配置不存在", http_status=404, request=request)
    item.enabled = not item.enabled
    item.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(item)
    return success(_serialize_config(item), request=request)


# === 发送日志 ===

@router.get("/logs")
async def list_logs(
    request: Request,
    week: str = "",
    _: object = Depends(current_admin),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(DistributionLog).order_by(DistributionLog.sent_at.desc())
    if week:
        stmt = stmt.where(DistributionLog.report_week == week)
    result = await session.execute(stmt)
    items = result.scalars().all()
    return success({"items": [_serialize_log(item) for item in items]}, request=request)
```

---

### Task 6: 注册路由 + 调度任务

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/app/core/scheduler.py`

- [ ] **Step 1: 在 main.py 注册 distribution 路由和调度任务**

Edit `backend/app/main.py`:

Add import after line 26 (other router imports):
```python
from app.modules.distribution.routes import router as distribution_router
```

Add import for the weekly digest job function:
```python
from app.modules.distribution.service import send_weekly_digest
```

Wait — I need to think about the scheduler integration more carefully. The `send_weekly_digest` function needs to be an async function that creates its own DB session. Let me design this properly.

Actually, let me add a dedicated dispatch function in `service.py` first. I need to add a `dispatch_weekly_report` function to the service file that:
1. Creates a DB session
2. Generates the report
3. Iterates over enabled configs
4. For each config, picks the right adapter and sends
5. Logs the result

Let me add this to service.py:

```python
async def dispatch_weekly_report():
    """由 APScheduler 调用的入口：生成并分发周报。"""
    from app.core.database import AsyncSessionLocal
    
    async with AsyncSessionLocal() as session:
        svc = WeeklyDigestService(session)
        year_week = _get_current_year_week()
        
        try:
            report = await svc.generate_weekly_report(year_week)
        except Exception as e:
            logger.error("周报生成失败: %s", e)
            return
        
        # 查询启用的通道
        from app.models.distribution import DistributionConfig
        result = await session.execute(
            select(DistributionConfig).where(DistributionConfig.enabled == True)
        )
        configs = result.scalars().all()
        
        from app.models.distribution import DistributionLog
        
        for cfg in configs:
            adapter = _get_adapter(cfg.channel_type)
            if adapter is None:
                continue
            
            log_entry = DistributionLog(
                config_id=cfg.id,
                config_name=cfg.name,
                channel_type=cfg.channel_type,
                report_week=year_week,
                date_range_start=report.date_range_start,
                date_range_end=report.date_range_end,
                status="failed",
                article_count=report.stats.total_articles,
                category_count=report.stats.total_categories,
            )
            
            try:
                await adapter.send(report, cfg.config)
                log_entry.status = "success"
                logger.info("周报分发成功: %s (%s)", cfg.name, cfg.channel_type)
            except Exception as e:
                log_entry.error_message = str(e)[:500]
                logger.error("周报分发失败: %s (%s): %s", cfg.name, cfg.channel_type, e)
            
            session.add(log_entry)
        
        await session.commit()


def _get_adapter(channel_type: str) -> DistributionAdapter | None:
    """根据通道类型获取适配器实例。"""
    from app.modules.distribution.adapters.email_adapter import EmailAdapter
    from app.modules.distribution.adapters.webhook_adapter import WebhookAdapter
    
    if channel_type == "email":
        return EmailAdapter()
    elif channel_type == "webhook":
        return WebhookAdapter()
    return None
```

And I need to add the import for `select` and `DistributionAdapter` in service.py.

OK let me restructure the plan tasks. Let me add the dispatch function to the service file in the plan, and then register it in main.py.

Actually, let me step back and think about the cleanest approach. Currently `main.py` registers scheduler jobs in the lifespan function. Let me follow the same pattern.

For the scheduler, I'll add the weekly job directly in main.py's lifespan, following the existing pattern for `scan_analyzing_timeouts`.

Let me finalize the code for both modifications.

- [ ] **Step 1: Add dispatch functions to service.py**

Append to `backend/app/modules/distribution/service.py` (after the WeeklyDigestService class):

```python
import logging
from datetime import date, timedelta

from sqlalchemy import select  # already imported if at top, otherwise add
from sqlalchemy.ext.asyncio import AsyncSession  # already imported

from app.modules.distribution.adapters.base import DistributionAdapter

logger = logging.getLogger("shixun.distribution")


def _get_adapter(channel_type: str) -> DistributionAdapter | None:
    from app.modules.distribution.adapters.email_adapter import EmailAdapter
    from app.modules.distribution.adapters.webhook_adapter import WebhookAdapter

    if channel_type == "email":
        return EmailAdapter()
    elif channel_type == "webhook":
        return WebhookAdapter()
    return None


async def dispatch_weekly_report():
    """APScheduler 入口：生成并分发周报。"""
    from app.core.database import AsyncSessionLocal
    from app.models.distribution import DistributionConfig, DistributionLog

    async with AsyncSessionLocal() as session:
        svc = WeeklyDigestService(session)
        year_week = _get_current_year_week()

        try:
            report = await svc.generate_weekly_report(year_week)
        except Exception as e:
            logger.error("周报生成失败: %s", e)
            return

        result = await session.execute(
            select(DistributionConfig).where(DistributionConfig.enabled == True)
        )
        configs = result.scalars().all()

        if not configs:
            logger.info("无启用的分发通道，周报跳过")
            return

        for cfg in configs:
            adapter = _get_adapter(cfg.channel_type)
            if adapter is None:
                logger.warning("未知通道类型: %s", cfg.channel_type)
                continue

            log_entry = DistributionLog(
                config_id=cfg.id,
                config_name=cfg.name,
                channel_type=cfg.channel_type,
                report_week=year_week,
                date_range_start=report.date_range_start,
                date_range_end=report.date_range_end,
                status="failed",
                article_count=report.stats.total_articles,
                category_count=report.stats.total_categories,
            )

            try:
                await adapter.send(report, cfg.config)
                log_entry.status = "success"
                logger.info("周报分发成功: %s (%s)", cfg.name, cfg.channel_type)
            except Exception as e:
                log_entry.error_message = str(e)[:500]
                logger.error("周报分发失败: %s (%s): %s", cfg.name, cfg.channel_type, e)

            session.add(log_entry)

        await session.commit()
```

- [ ] **Step 2: 在 main.py 注册路由和调度任务**

Edit `backend/app/main.py`:

After line 26 (`from app.modules.discovery.routes import router as discovery_router`), add:
```python
from app.modules.distribution.routes import router as distribution_router
```

After line 27 (last existing import), add:
```python
from app.modules.distribution.service import dispatch_weekly_report
```

In the lifespan function, after the `scan_analyzing_timeouts` job (after line 69), add:
```python
    from apscheduler.triggers.cron import CronTrigger
    scheduler.add_job(
        dispatch_weekly_report,
        id="weekly_digest",
        trigger=CronTrigger(day_of_week="mon", hour=8, minute=30),
        replace_existing=True,
    )
```

After the last `app.include_router(articles_router)` (line 141), add:
```python
app.include_router(distribution_router)
```

- [ ] **Step 3: 验证启动不报错**

```bash
cd backend && python -c "from app.modules.distribution.service import dispatch_weekly_report; print('OK')"
```

Expected: `OK`

---

### Task 7: 前端 - 通道配置页

**Files:**
- Create: `frontend/app/admin/distribution/page.tsx`
- Modify: `frontend/lib/api.ts`

- [ ] **Step 1: 实现配置管理页面**

`frontend/app/admin/distribution/page.tsx`:

```tsx
'use client';

import { useEffect, useState, useCallback } from 'react';
import { Header } from '@/components/layout/Header';
import { api, ApiError } from '@/lib/api';

type DistConfig = {
  id: string;
  channel_type: string;
  name: string;
  config: Record<string, unknown>;
  enabled: boolean;
  created_at: string | null;
  updated_at: string | null;
};

const CHANNEL_LABELS: Record<string, string> = {
  email: '邮件',
  webhook: 'Webhook（飞书）',
};

export default function DistributionPage() {
  const [items, setItems] = useState<DistConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [formOpen, setFormOpen] = useState(false);
  const [editId, setEditId] = useState<string | null>(null);
  const [formType, setFormType] = useState('email');
  const [formName, setFormName] = useState('');
  const [formEnabled, setFormEnabled] = useState(true);

  // email fields
  const [smtpHost, setSmtpHost] = useState('');
  const [smtpPort, setSmtpPort] = useState('465');
  const [smtpUser, setSmtpUser] = useState('');
  const [smtpPass, setSmtpPass] = useState('');
  const [fromAddr, setFromAddr] = useState('');
  const [toAddrs, setToAddrs] = useState('');

  // webhook fields
  const [webhookUrl, setWebhookUrl] = useState('');

  const fetchList = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.get<{ items: DistConfig[] }>('/api/v1/distribution/configs');
      setItems(data.items);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchList(); }, [fetchList]);

  function openNew() {
    setEditId(null);
    setFormType('email');
    setFormName('');
    setFormEnabled(true);
    setSmtpHost('');
    setSmtpPort('465');
    setSmtpUser('');
    setSmtpPass('');
    setFromAddr('');
    setToAddrs('');
    setWebhookUrl('');
    setFormOpen(true);
  }

  function openEdit(item: DistConfig) {
    setEditId(item.id);
    setFormType(item.channel_type);
    setFormName(item.name);
    setFormEnabled(item.enabled);
    const c = item.config;
    setSmtpHost(String(c.smtp_host || ''));
    setSmtpPort(String(c.smtp_port || '465'));
    setSmtpUser(String(c.smtp_user || ''));
    setSmtpPass('');
    setFromAddr(String(c.from_addr || ''));
    setToAddrs(Array.isArray(c.to_addrs) ? c.to_addrs.join(', ') : '');
    setWebhookUrl(String(c.url || ''));
    setFormOpen(true);
  }

  function buildConfig(): Record<string, unknown> {
    if (formType === 'email') {
      return {
        smtp_host: smtpHost,
        smtp_port: parseInt(smtpPort, 10) || 465,
        smtp_user: smtpUser,
        smtp_pass: smtpPass,
        from_addr: fromAddr || smtpUser,
        to_addrs: toAddrs.split(',').map(s => s.trim()).filter(Boolean),
        use_tls: true,
      };
    }
    return { url: webhookUrl, platform: 'feishu' };
  }

  async function handleSave() {
    if (!formName.trim()) return;
    if (formType === 'webhook' && !webhookUrl.trim()) return;
    if (formType === 'email' && !smtpHost.trim()) return;
    try {
      const payload = {
        channel_type: formType,
        name: formName.trim(),
        config: buildConfig(),
        enabled: formEnabled,
      };
      if (editId) {
        await api.put(`/api/v1/distribution/configs/${editId}`, payload);
      } else {
        await api.post('/api/v1/distribution/configs', payload);
      }
      setFormOpen(false);
      fetchList();
    } catch (e: unknown) {
      alert(e instanceof ApiError ? e.message : '保存失败');
    }
  }

  async function handleToggle(id: string) {
    try {
      await api.patch(`/api/v1/distribution/configs/${id}/toggle`);
      fetchList();
    } catch (e: unknown) {
      alert(e instanceof ApiError ? e.message : '操作失败');
    }
  }

  async function handleDelete(id: string) {
    if (!confirm('确认删除此分发配置？')) return;
    try {
      await api.delete(`/api/v1/distribution/configs/${id}`);
      fetchList();
    } catch (e: unknown) {
      alert(e instanceof ApiError ? e.message : '删除失败');
    }
  }

  return (
    <>
      <Header />
      <main className="mx-auto max-w-6xl px-6 py-8">
        <div className="mb-6 flex items-center justify-between">
          <h1 className="text-xl font-semibold text-gray-800">分发配置</h1>
          <button
            onClick={openNew}
            className="rounded bg-brand-600 px-4 py-1.5 text-sm text-white hover:bg-brand-700"
          >
            新增通道
          </button>
        </div>

        {loading ? (
          <p className="text-sm text-gray-500">加载中…</p>
        ) : items.length === 0 ? (
          <p className="text-sm text-gray-500">暂未配置分发通道</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white shadow-sm">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-left text-xs text-gray-500">
                <tr className="border-b border-gray-200">
                  <th className="px-4 py-3">通道名称</th>
                  <th className="px-4 py-3">类型</th>
                  <th className="px-4 py-3">状态</th>
                  <th className="px-4 py-3">创建时间</th>
                  <th className="px-4 py-3">操作</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id} className="border-b border-gray-100 hover:bg-gray-50">
                    <td className="px-4 py-3 text-sm text-gray-800">{item.name}</td>
                    <td className="px-4 py-3 text-xs text-gray-600">
                      {CHANNEL_LABELS[item.channel_type] || item.channel_type}
                    </td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => handleToggle(item.id)}
                        className={`rounded px-2 py-0.5 text-xs ${
                          item.enabled
                            ? 'bg-emerald-100 text-emerald-700'
                            : 'bg-gray-100 text-gray-500'
                        }`}
                      >
                        {item.enabled ? '启用' : '禁用'}
                      </button>
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-500">
                      {item.created_at ? new Date(item.created_at).toLocaleString('zh-CN') : '-'}
                    </td>
                    <td className="px-4 py-3">
                      <button onClick={() => openEdit(item)} className="mr-2 text-xs text-brand-600 hover:underline">编辑</button>
                      <button onClick={() => handleDelete(item.id)} className="text-xs text-red-600 hover:underline">删除</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {formOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
            <div className="w-full max-w-lg rounded-lg bg-white p-6 shadow-xl">
              <h2 className="mb-4 text-base font-semibold text-gray-800">
                {editId ? '编辑' : '新增'}分发通道
              </h2>
              <div className="space-y-4">
                <div>
                  <label className="block text-xs text-gray-500">通道类型</label>
                  <select
                    value={formType}
                    onChange={e => setFormType(e.target.value)}
                    className="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm"
                    disabled={!!editId}
                  >
                    <option value="email">邮件</option>
                    <option value="webhook">Webhook（飞书）</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-gray-500">通道名称</label>
                  <input
                    value={formName}
                    onChange={e => setFormName(e.target.value)}
                    className="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm"
                    placeholder="如：研发团队邮件组"
                  />
                </div>

                {formType === 'email' && (
                  <>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="block text-xs text-gray-500">SMTP 地址</label>
                        <input value={smtpHost} onChange={e => setSmtpHost(e.target.value)} className="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm" placeholder="smtp.qq.com" />
                      </div>
                      <div>
                        <label className="block text-xs text-gray-500">端口</label>
                        <input value={smtpPort} onChange={e => setSmtpPort(e.target.value)} className="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm" placeholder="465" />
                      </div>
                    </div>
                    <div>
                      <label className="block text-xs text-gray-500">SMTP 用户名</label>
                      <input value={smtpUser} onChange={e => setSmtpUser(e.target.value)} className="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm" placeholder="xxx@qq.com" />
                    </div>
                    <div>
                      <label className="block text-xs text-gray-500">SMTP 密码/授权码</label>
                      <input type="password" value={smtpPass} onChange={e => setSmtpPass(e.target.value)} className="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm" placeholder={editId ? '留空则不修改' : ''} />
                    </div>
                    <div>
                      <label className="block text-xs text-gray-500">发件人地址</label>
                      <input value={fromAddr} onChange={e => setFromAddr(e.target.value)} className="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm" placeholder="可选，默认同用户名" />
                    </div>
                    <div>
                      <label className="block text-xs text-gray-500">收件人（多个用逗号分隔）</label>
                      <input value={toAddrs} onChange={e => setToAddrs(e.target.value)} className="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm" placeholder="a@company.com, b@company.com" />
                    </div>
                  </>
                )}

                {formType === 'webhook' && (
                  <div>
                    <label className="block text-xs text-gray-500">Webhook URL</label>
                    <input value={webhookUrl} onChange={e => setWebhookUrl(e.target.value)} className="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm" placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/..." />
                  </div>
                )}

                <div className="flex items-center gap-2">
                  <input type="checkbox" id="enabled" checked={formEnabled} onChange={e => setFormEnabled(e.target.checked)} className="rounded" />
                  <label htmlFor="enabled" className="text-sm text-gray-700">启用</label>
                </div>
              </div>
              <div className="mt-6 flex justify-end gap-3">
                <button onClick={() => setFormOpen(false)} className="rounded border border-gray-300 px-4 py-1.5 text-sm text-gray-600 hover:bg-gray-50">取消</button>
                <button onClick={handleSave} className="rounded bg-brand-600 px-4 py-1.5 text-sm text-white hover:bg-brand-700">保存</button>
              </div>
            </div>
          </div>
        )}
      </main>
    </>
  );
}
```

- [ ] **Step 2: 在 api.ts 添加 patch 方法**

Edit `frontend/lib/api.ts` — add `patch` to the `api` object (after `put`):

```typescript
  patch: <T>(p: string, payload?: unknown) =>
    apiRequest<T>(p, { method: 'PATCH', body: payload ? JSON.stringify(payload) : undefined }),
```

The final `api` object should look like:

```typescript
export const api = {
  get: <T>(p: string) => apiRequest<T>(p, { method: 'GET' }),
  post: <T>(p: string, payload?: unknown) =>
    apiRequest<T>(p, { method: 'POST', body: payload ? JSON.stringify(payload) : undefined }),
  put: <T>(p: string, payload?: unknown) =>
    apiRequest<T>(p, { method: 'PUT', body: payload ? JSON.stringify(payload) : undefined }),
  patch: <T>(p: string, payload?: unknown) =>
    apiRequest<T>(p, { method: 'PATCH', body: payload ? JSON.stringify(payload) : undefined }),
  delete: <T>(p: string) => apiRequest<T>(p, { method: 'DELETE' }),
};
```

- [ ] **Step 3: Verify build**

```bash
cd frontend && npx tsc --noEmit --pretty 2>&1 | head -30
```

Expected: No type errors (or only pre-existing ones)

---

### Task 8: 前端 - 发送日志页 + 导航更新

**Files:**
- Create: `frontend/app/admin/distribution/logs/page.tsx`
- Modify: `frontend/components/layout/Header.tsx`

- [ ] **Step 1: 实现发送日志页面**

`frontend/app/admin/distribution/logs/page.tsx`:

```tsx
'use client';

import { useEffect, useState, useCallback } from 'react';
import { Header } from '@/components/layout/Header';
import { api } from '@/lib/api';

type DistLog = {
  id: string;
  config_name: string | null;
  channel_type: string | null;
  report_week: string;
  status: string;
  article_count: number;
  category_count: number;
  error_message: string | null;
  sent_at: string | null;
};

const CHANNEL_LABELS: Record<string, string> = {
  email: '邮件',
  webhook: '飞书',
};

const STATUS_LABELS: Record<string, { label: string; cls: string }> = {
  success: { label: '成功', cls: 'bg-emerald-100 text-emerald-700' },
  failed: { label: '失败', cls: 'bg-red-100 text-red-700' },
};

export default function DistributionLogsPage() {
  const [logs, setLogs] = useState<DistLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [weekFilter, setWeekFilter] = useState('');
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    try {
      const params = weekFilter ? `?week=${weekFilter}` : '';
      const data = await api.get<{ items: DistLog[] }>(`/api/v1/distribution/logs${params}`);
      setLogs(data.items);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [weekFilter]);

  useEffect(() => { fetchLogs(); }, [fetchLogs]);

  return (
    <>
      <Header />
      <main className="mx-auto max-w-6xl px-6 py-8">
        <div className="mb-6 flex items-center justify-between">
          <h1 className="text-xl font-semibold text-gray-800">发送日志</h1>
          <div className="flex items-center gap-2">
            <input
              value={weekFilter}
              onChange={e => setWeekFilter(e.target.value)}
              className="rounded border border-gray-300 px-3 py-1.5 text-sm"
              placeholder="筛选周次，如 2026-W18"
            />
            {weekFilter && (
              <button
                onClick={() => setWeekFilter('')}
                className="rounded border border-gray-300 px-3 py-1.5 text-xs text-gray-500 hover:bg-gray-50"
              >
                清除
              </button>
            )}
          </div>
        </div>

        {loading ? (
          <p className="text-sm text-gray-500">加载中…</p>
        ) : logs.length === 0 ? (
          <p className="text-sm text-gray-500">暂无发送记录</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white shadow-sm">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-left text-xs text-gray-500">
                <tr className="border-b border-gray-200">
                  <th className="px-4 py-3">周次</th>
                  <th className="px-4 py-3">通道</th>
                  <th className="px-4 py-3">类型</th>
                  <th className="px-4 py-3">状态</th>
                  <th className="px-4 py-3">文章数</th>
                  <th className="px-4 py-3">发送时间</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {logs.map((log) => (
                  <tr key={log.id} className="border-b border-gray-100 hover:bg-gray-50">
                    <td className="px-4 py-3 text-xs font-mono text-gray-800">{log.report_week}</td>
                    <td className="px-4 py-3 text-sm text-gray-800">{log.config_name || '-'}</td>
                    <td className="px-4 py-3 text-xs text-gray-600">
                      {CHANNEL_LABELS[log.channel_type || ''] || log.channel_type || '-'}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`rounded px-2 py-0.5 text-xs ${STATUS_LABELS[log.status]?.cls || 'bg-gray-100 text-gray-500'}`}>
                        {STATUS_LABELS[log.status]?.label || log.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-600">{log.article_count}</td>
                    <td className="px-4 py-3 text-xs text-gray-500">
                      {log.sent_at ? new Date(log.sent_at).toLocaleString('zh-CN') : '-'}
                    </td>
                    <td className="px-4 py-3">
                      {log.status === 'failed' && log.error_message && (
                        <button
                          onClick={() => setExpandedId(expandedId === log.id ? null : log.id)}
                          className="text-xs text-brand-600 hover:underline"
                        >
                          {expandedId === log.id ? '收起' : '详情'}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {expandedId && (
              <div className="border-t border-gray-200 bg-red-50 px-4 py-3 text-xs text-red-700">
                {logs.find(l => l.id === expandedId)?.error_message}
              </div>
            )}
          </div>
        )}
      </main>
    </>
  );
}
```

- [ ] **Step 2: 更新导航栏**

Edit `frontend/components/layout/Header.tsx` — update NAV array:

```typescript
const NAV = [
  { href: '/dashboard', label: '看板' },
  { href: '/tasks', label: '任务' },
  { href: '/tasks/new', label: '新建任务' },
  { href: '/tasks/discover', label: '站点发现' },
  { href: '/articles', label: '文章' },
  { href: '/admin/allowlist', label: '白名单' },
  { href: '/admin/distribution', label: '分发配置' },
];
```

- [ ] **Step 3: Verify build**

```bash
cd frontend && npx tsc --noEmit --pretty 2>&1 | head -30
```

Expected: No type errors

---

### Task 9: 手动触发端点 + 集成验证

**Files:**
- Modify: `backend/app/modules/distribution/routes.py`

- [ ] **Step 1: 添加手动触发端点**

Append to `backend/app/modules/distribution/routes.py`:

```python
@router.post("/trigger")
async def trigger_dispatch(
    request: Request,
    _: object = Depends(current_admin),
    session: AsyncSession = Depends(get_session),
):
    """手动触发周报分发（调试用）。"""
    from app.modules.distribution.service import dispatch_weekly_report

    try:
        await dispatch_weekly_report()
        return success({"message": "周报分发已触发"}, request=request)
    except Exception as e:
        logger.error("手动触发周报分发失败: %s", e)
        return error(2001, f"触发失败: {str(e)}", http_status=500, request=request)
```

- [ ] **Step 2: 完整 verify 所有测试通过**

```bash
cd backend && python -m pytest tests/ -v
```

Expected: All tests pass (existing + new distribution tests)

---

### 执行顺序总结

```
Task 1: Models + Migration      (数据层)
Task 2: Service + Schemas       (核心逻辑)
Task 3: EmailAdapter            (邮件通道)
Task 4: WebhookAdapter          (飞书通道)
Task 5: API Routes              (REST API)
Task 6: Scheduler + Main        (注册路由和定时任务)
Task 7: Frontend Config Page    (配置管理 UI)
Task 8: Frontend Logs Page      (发送日志 UI + 导航)
Task 9: Trigger Endpoint + Verify (手动触发 + 集成验证)
```

每个任务可独立实现和测试，任务间依赖明确（Task 1 是所有后续的基础，Task 5 依赖 Task 1-4，Task 6 依赖 Task 5）。
