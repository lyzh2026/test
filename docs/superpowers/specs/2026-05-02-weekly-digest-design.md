# 周报分发系统设计文档

> 日期：2026-05-02
> 状态：待实现

---

## 1. 需求概述

实现"拾讯"情报平台的"分发"闭环：定时生成周报并通过多渠道推送给团队成员。

### 核心需求

- **内容**：每周一自动发送上周全量文章，按分类分组罗列（标题 + AI 摘要 + 来源 + 日期）
- **通道**：邮件 + 飞书 Webhook
- **频率**：每周一早 8:30
- **用途**：内部团队使用

---

## 2. 数据模型

### 2.1 `distribution_config` — 分发通道配置

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID | PK, default uuid4 | |
| channel_type | VARCHAR(20) | NOT NULL | `email` / `webhook` |
| name | VARCHAR(100) | NOT NULL | 配置名称（如"研发团队邮件组"） |
| config | JSONB | NOT NULL | 通道参数 |
| enabled | BOOLEAN | DEFAULT true | 是否启用 |
| created_at | TIMESTAMPTZ | DEFAULT now() | |
| updated_at | TIMESTAMPTZ | DEFAULT now() | |

**config 结构**（按 channel_type）：

email:
```json
{
  "smtp_host": "smtp.qq.com",
  "smtp_port": 465,
  "smtp_user": "xxx@qq.com",
  "smtp_pass": "授权码",
  "from_addr": "拾讯周报 <xxx@qq.com>",
  "to_addrs": ["a@company.com", "b@company.com"],
  "use_tls": true
}
```

webhook:
```json
{
  "url": "https://open.feishu.cn/open-apis/bot/v2/hook/xxx",
  "platform": "feishu",
  "secret": ""
}
```

### 2.2 `distribution_log` — 发送日志

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID | PK, default uuid4 | |
| config_id | UUID | FK → distribution_config, ON DELETE SET NULL | |
| config_name | VARCHAR(100) | | 发送时的通道名称（快照） |
| channel_type | VARCHAR(20) | | 发送时的通道类型（快照） |
| report_week | VARCHAR(10) | NOT NULL | 如 "2026-W18" |
| date_range_start | DATE | NOT NULL | |
| date_range_end | DATE | NOT NULL | |
| status | VARCHAR(20) | NOT NULL | `success` / `failed` |
| article_count | INTEGER | DEFAULT 0 | 本次发送文章数 |
| category_count | INTEGER | DEFAULT 0 | 涉及分类数 |
| error_message | TEXT | | 失败原因 |
| sent_at | TIMESTAMPTZ | DEFAULT now() | |

---

## 3. 系统架构

```
APScheduler (每周一 8:30)
    │
    ▼
WeeklyDigestService.generate_weekly_report()
  ├─ 查询上周文章 (publish_date 范围 + status=processed)
  ├─ 按 ai_analysis.categories 分组
  ├─ 不足 2 篇的分类合并至"其他"
  └─ 返回 WeeklyReport 数据对象
    │
    ▼
 遍历所有启用的 distribution_config
    │
    ├─▶ EmailAdapter
    │    ├─ 渲染 HTML 模板
    │    ├─ smtplib 发送
    │    └─ 写入 distribution_log
    │
    └─▶ WebhookAdapter
         ├─ FeishuFormatter → Markdown 消息
         ├─ httpx POST
         └─ 写入 distribution_log
```

---

## 4. 核心模块

### 4.1 WeeklyReport 数据类

```python
@dataclass
class WeeklyReport:
    year_week: str                # "2026-W18"
    date_range: tuple[date, date]  # (start, end)
    categories: list[CategoryGroup]
    stats: ReportStats

@dataclass
class CategoryGroup:
    name: str
    articles: list[ArticleItem]

@dataclass
class ArticleItem:
    title: str
    summary: str          # 来自 ai_analysis
    url: str
    publish_date: date
    source_unit: str

@dataclass
class ReportStats:
    total_articles: int
    total_categories: int
```

### 4.2 WeeklyDigestService

`backend/app/modules/distribution/service.py`

核心方法：

- `generate_weekly_report(year_week: str) -> WeeklyReport`
  - 解析 year_week 为日期范围（周一 ~ 周日）
  - 查询 `articles WHERE publish_date BETWEEN ... AND status = 'processed'`
  - JOIN `ai_analysis` 获取 categories 和 summary
  - categories JSONB 数组展开，每篇文章归入第一个分类
  - 按分类聚合，数量降序排列
  - 分类下不足 2 篇 → 合并到"其他"
  - 返回 WeeklyReport

- `send_weekly_report(year_week: str) -> list[DeliveryResult]`
  - 调用 generate_weekly_report()
  - 遍历所有启用的 distribution_config
  - 调用对应 adapter 发送
  - 记录 distribution_log

### 4.3 EmailAdapter

`backend/app/modules/distribution/adapters/email_adapter.py`

- `send(report: WeeklyReport, config: DistributionConfig) -> bool`
- HTML 模板引擎：string.Template（零依赖）
- 模板结构：
  - 头部：拾讯周报 + 日期范围
  - 统计行：本周共 X 篇，覆盖 X 个分类
  - 按分类分段，每段一个小表格：标题(超链接) | 来源 | 日期 | 摘要
  - 尾部：自动发送标识
- SMTP 连接：smtplib，支持 SSL/TLS
- 失败时抛异常，由上层记录日志

### 4.4 WebhookAdapter

`backend/app/modules/distribution/adapters/webhook_adapter.py`

- `send(report: WeeklyReport, config: DistributionConfig) -> bool`
- 根据 `config.platform` 选择合适的 formatter
- 飞书消息结构（Markdown）：

```json
{
  "msg_type": "interactive",
  "card": {
    "header": {"title": {"tag": "plain_text", "content": "拾讯周报 2026-W18"}},
    "elements": [
      {"tag": "markdown", "content": "本周共采集 **42** 篇文章，覆盖 **7** 个分类\n---"},
      {"tag": "markdown", "content": "**📋 政策法规**（12篇）\n1. [标题](url) · 2026-04-28 · 来源单位\n   > AI 摘要...\n2. ..."},
      ...
    ]
  }
}
```

- 飞书消息大小限制约 30KB，若超出则拆分发送或仅发送标题 + 链接

### 4.5 调度注册

`backend/app/core/scheduler.py` 中注册：

```python
scheduler.add_job(
    send_weekly_report,
    trigger=CronTrigger(day_of_week='mon', hour=8, minute=30),
    id='weekly_digest',
    replace_existing=True,
)
```

支持手动触发：`POST /api/v1/distribution/trigger`（管理员，调试用）

---

## 5. 管理界面

### 5.1 通道配置页

路由：`/admin/distribution`

功能：
- 列出所有通道配置（类型、名称、启用状态、最后发送时间）
- 添加/编辑通道（表单随 channel_type 动态切换字段）
- 启用/禁用开关
- 删除通道

### 5.2 发送日志页

路由：`/admin/distribution/logs`

功能：
- 按周筛选：默认当前周，支持选择周
- 列表：发送时间、通道名称、类型、状态（成功/失败）、文章数
- 失败条目可点击展开错误详情

### 5.3 导航更新

在 Header 组件 admin 下拉菜单中增加"分发配置"入口。

---

## 6. API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/distribution/configs` | 列出所有通道配置 |
| POST | `/api/v1/distribution/configs` | 新增通道配置 |
| PUT | `/api/v1/distribution/configs/{id}` | 编辑通道配置 |
| DELETE | `/api/v1/distribution/configs/{id}` | 删除通道配置 |
| PATCH | `/api/v1/distribution/configs/{id}/toggle` | 启用/禁用 |
| GET | `/api/v1/distribution/logs` | 发送日志列表（支持 week 参数筛选） |
| POST | `/api/v1/distribution/trigger` | 手动触发周报（调试用） |

---

## 7. 错误处理

- 邮件发送失败（SMTP 连接超时、认证失败）→ 记录 failed 日志，不影响其他通道
- Webhook 发送失败（网络超时、非 2xx 响应）→ 记录 failed 日志
- 报告生成失败（数据库查询异常）→ 不发送，记录错误日志，等待下周重试
- 单通道失败不阻塞其他通道
- 不实现自动重试（周报是定时任务，失败了下周会重新生成）

---

## 8. 配置项

在 `.env` 中新增（可选默认值，可在管理页面覆盖）：

```ini
# SMTP 默认配置
SMTP_HOST=smtp.qq.com
SMTP_PORT=465
SMTP_USER=
SMTP_PASS=
SMTP_FROM=拾讯周报 <noreply@shixun.local>

# 默认收件人（逗号分隔）
DEFAULT_TO_ADDRS=
```

---

## 9. 排除项（YAGNI）

- ❌ RSS Feed（用户已确认去掉）
- ❌ 个人微信推送（无官方 API）
- ❌ 报告内容自定义模板（现有模板满足需求）
- ❌ 发送失败自动重试（周报不可弥补）
- ❌ 多语言支持
- ❌ 报告归档和下载
