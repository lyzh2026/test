# 产品核心架构需求文档 (PRD) - shixun.com

| 项目信息 | 内容 |
| :--- | :--- |
| **项目名称** | 拾讯 (shixun.com) |
| **产品身份** | 资深全栈产品架构师 |
| **核心目标** | 构建从"数据抓取 → AI 深度加工 → 多渠道精准分发"的自动化闭环系统 |
| **版本** | v1.0 MVP |
| **日期** | 2026-04-24 |

---

## 1. 系统架构综述

### 1.1 架构理念

系统采用**模块化单体架构（Modular Monolith）**，按"数据采集"、"AI 加工"与"业务分发"三大领域划分为独立模块。对外暴露标准化 RESTful API，模块间以 HTTP 接口形态进行进程内调用（通过FastAPI 内部路由互调，不走外部网络），保持清晰的接口与数据边界，为未来独立拆分预留路径。

MVP 阶段所有模块聚合运行于同一 Docker Compose 网络内，通过内部 HTTP 调用协作，降低运维复杂度。模块间的解耦设计预留了未来独立拆分为微服务的扩展路径，无需重构核心逻辑即可演进。

### 1.2 技术栈总览

| 层级 | 技术选型 | 版本/说明 |
| :--- | :--- | :--- |
| **前端** | Next.js | 14+ (App Router, Server Components) |
| **前端 UI** | Tailwind CSS + shadcn/ui | 原子化 CSS + 无障碍组件库 |
| **后端框架** | FastAPI | Python 3.11+，原生异步支持 |
| **数据库** | PostgreSQL | 15+，支持 JSONB 与全文检索 |
| **ORM / 迁移** | SQLAlchemy 2.0 + Alembic | 类型安全的数据模型与版本控制 |
| **数据校验** | Pydantic v2 | 请求/响应模型统一校验 |
| **爬虫引擎** | Playwright + DynamicRenderer | 基于 Playwright 的渲染编排层，覆盖 SPA、懒加载、无限滚动（详见 2.1.9） |
| **内容提取** | 多策略 SpiderAdapter | XPath + Readability-lxml + LLM 抽取自动降级（详见 2.1.10） |
| **域名 / 适配器治理** | 动态配置（PostgreSQL） | `allowed_domains`（白名单）、`spider_adapter_configs`（适配器注册表）；环境变量 `ALLOWED_DOMAINS` 仅作首次启动 seed |
| **AI 模型** | 国产大模型 API | 通义千问 / 文心一言 / DeepSeek（AI 中枢与 LLMExtractionAdapter 复用同一供应商配置） |
| **任务调度** | APScheduler | 承担 Crawler 任务队列、AI 异步任务触发、定时扫描（超时检测/死信/归档）三重职责，JobStore 持久化至 PostgreSQL 避免重启丢失。MVP 不引入独立消息队列以降低运维复杂度 |
| **文件存储** | 本地文件系统 | MVP 本地存储 |
| **容器化** | Docker + Docker Compose | 一键部署，环境隔离 |

### 1.3 MVP 范围边界

**v1.0 MVP 核心目标**：实现"数据抓取 → AI 分析 → 前端实时展示"的最小闭环，验证业务模式可行性。

**MVP 包含**：
- 自动化数据采集（Crawler Service）
- AI 智能分析（AI Intelligence Engine）
- 结构化入库与前端实时数据展示（Storage & Frontend Data Service）
- 管理后台前端（Next.js）

**MVP 明确不包含**：
- 微信公众号自动分发
- 商业级文档导出
- 邮件订阅推送
- 多租户用户体系
- 对象存储（OSS）

上述功能作为 v2.0 扩展方向，在本文档中仅作极简说明，不定义详细接口与数据结构。

### 1.4 系统拓扑图

```
┌─────────────────────────────────────────────────────────────────────┐
│                              用户层                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │
│  │  管理后台    │  │  微信公众号  │  │   邮件收件箱 │  │             │ │
│  │ (Next.js)   │  │  (预留接口)  │  │  (预留接口)  │  │             │ │
│  └──────┬──────┘  └─────────────┘  └─────────────┘  └─────────────┘ │
└─────────┼───────────────────────────────────────────────────────────┘
          │ HTTPS / RESTful API
┌─────────▼───────────────────────────────────────────────────────────┐
│                    应用层 (FastAPI 单体应用)                          │
│                                                                     │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │   │
│   │  │ Crawler  │ │ AI Engine│ │ Reporting│ │  Export  │       │   │
│   │  │  Module  │ │  Module  │ │  Module  │ │  Module  │       │   │
│   │  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘       │   │
│   │  ┌────┴─────┐ ┌────┴─────┐ ┌────┴─────┐ ┌────┴─────┐     │   │
│   │  │ WeChat   │ │   Sub    │ │   Auth   │ │   File   │     │   │
│   │  │ Module   │ │ Module   │ │ Module   │ │ Module   │     │   │
│   │  │ (预留)    │ │ (预留)    │ │ (预留)    │ │ (本地/OSS)│     │   │
│   │  └──────────┘ └──────────┘ └──────────┘ └──────────┘     │   │
│   └─────────────────────────────────────────────────────────────┘   │
│                        内部 HTTP 调用 (进程内)                        │
└─────────────────────────────────────────────────────────────────────┘
          │
┌─────────▼───────────────────────────────────────────────────────────┐
│                           数据层                                     │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐     │
│  │   PostgreSQL    │  │   本地文件系统   │  │   (预留 MQ)     │     │
│  │  (文章/任务/用户) │  │ (封面图/静态文件)│  │  RabbitMQ/Kafka │     │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘     │
└─────────────────────────────────────────────────────────────────────┘
```

---

### 1.5 架构决策记录（ADR）

以下决策必须在 MVP 开发启动前确定，否则将阻塞后续设计。

| 编号 | 决策项 | 状态 | 推荐方案 | 阻塞影响 |
| :--- | :--- | :--- | :--- | :--- |
| **ADR-01** | 目标网站接入策略 | ✅ 已决策 | **动态白名单 + 协议层防护**：URL 必须命中 `allowed_domains` 启用记录方可爬取；表项支持 exact / suffix / regex 三种匹配模式，启用/禁用 + 软删除全周期管理；环境变量 `ALLOWED_DOMAINS` 在首次启动时灌入数据库作为初始 seed，运行时以数据库为准；SubdomainDiscover 发现的子域名自动入白（`auto_added=true`），运营事后可批量撤回 | 影响 Crawler 的 URL 校验逻辑、白名单管理后台与 SSRF 防护 |
| **ADR-02** | 用户系统优先级 | ✅ 已决策 | **单管理员模式**（MVP 不实现注册登录，仅内置 admin 账号，Session + API Key 鉴权） | 影响 Auth 模块是否建表、API 是否鉴权 |
| **ADR-03** | 分类标签体系 | ✅ 已决策 | **11 标签固定 + "未分类"兜底**，MVP 不支持动态增删 | 影响 AI Prompt 设计与人工复核队列规模 |
| **ADR-04** | 适配器与降级链 | ✅ 已决策 | **多策略 SpiderAdapter 体系**：XPath → Readability → LLM 抽取（MVP 必备）→ AI 浏览器代理（v1.1+ 预留），按域名注册表选择首选策略，失败逐级降级 | 影响爬虫核心流程与异构站点覆盖率 |

> **决策原则**：MVP 阶段优先选择"实现成本最低、未来改动最小"的方案，不为扩展性牺牲交付速度。

---

## 2. 核心功能模块详细需求

### 2.1 自动化数据采集模块 (Crawler Service)

#### 2.1.1 功能定位

负责接收用户提交的目标网址列表与日期范围，模拟浏览器行为抓取文章全文，提取标准化元数据，并将原始内容推送至 AI 加工模块。

#### 2.1.2 输入规范

- **接口**：`POST /api/v1/crawler/task`
- **请求体 (JSON)**：

```json
{
  "task_name": "可选任务名称",
  "target_date": "2026-04-23",
  "url_list": [
    "https://example.gov.cn/policy/123.html",
    "https://example.com/news/456.html"
  ],
  "callback_url": "可选的异步回调地址",
  "priority": 1
}
```

- **约束**：
  - `url_list` 单次提交上限 **100 条**（防止滥用）。
  - `url_list` 中每个 URL 必须满足以下条件，任意一项不通过即返回相应校验错误：
    - 协议必须为 `http` / `https`，禁止 `file://`、`ftp://` 等其他协议（违反返回 `1003`）。
    - 解析后的目标 IP 不得指向 Loopback / 保留段 / 内网网段（10.0.0.0/8、172.16.0.0/12、192.168.0.0/16、127.0.0.0/8、169.254.0.0/16、::1、fc00::/7 等），用于 SSRF 防护（违反返回 `1005`）。
    - URL 域名必须命中 `allowed_domains` 表中**已启用且未软删除**的白名单记录。匹配支持 exact / suffix / regex 三类模式（详见 2.1.7 与 4.2 表设计），不命中即拒绝（返回 `1004`）。
  - `target_date` 支持 ISO 8601 格式 (`YYYY-MM-DD`)。
  - 系统同时支持爬取历史日期文章（需判断目标站点的文章列表分页逻辑）。
  - **白名单维护**：管理员可在后台对 `allowed_domains` 进行 CRUD（启用 / 禁用 / 软删除）；环境变量 `ALLOWED_DOMAINS` 仅在首次启动时灌入数据库作为初始 seed，运行时以数据库为准。SubdomainDiscover 发现的子域名按 ADR-01 自动入白（`auto_added=true`），运营事后可在管理后台批量撤回。多 worker 缓存同步详见 5.4 配置缓存同步。

#### 2.1.3 核心逻辑

| 步骤 | 动作 | 说明 |
| :--- | :--- | :--- |
| 1 | 任务注册 | 将任务写入 `crawler_tasks` 表，状态置为 `pending` |
| 2 | 队列调度 | APScheduler 的 JobStore 持久化任务队列，按 `priority` 升序 + `created_at` FIFO 顺序调度 Crawler 任务。任务被实际拾取执行时，将 `status` 更新为 `running` 并记录 `started_at`。每批次限流执行，避免目标站点过载 |
| 3 | 适配器选择 | 根据 URL 域名查询 `spider_adapter_configs` 注册表，确定首选 SpiderAdapter（默认 `ReadabilityAdapter`），若注册表存在站点定制规则则优先选用 `XPathAdapter`。详见 2.1.10 |
| 4 | 动态渲染 | 调用 DynamicRenderer 启动 Headless Chromium，按适配器声明的渲染策略执行：智能等待、自动滚动（懒加载/无限滚动）、网络空闲检测、必要的元素交互（点击"加载更多"等）。详见 2.1.9 |
| 5 | 内容提取 | 由所选 SpiderAdapter 执行结构化提取（标题、正文、发布单位、发布时间）。**降级链**：`XPath → Readability → LLMExtractionAdapter → AIBrowserAgent`（v1.1+ 预留）；前一级失败或 `validate()` 不通过则自动尝试下一级，每级失败原因写入失败日志 |
| 6 | 字段清洗 | 标准化发布时间、清洗发布单位名称、过滤广告与导航栏 |
| 7 | 结果入库 | 在同一个数据库事务中完成：`articles` 写入并状态置为 `raw`，同时累加 `crawler_tasks.completed_urls`；若该条 URL 全降级链耗尽，累加 `failed_urls` 并写入 `failed_details`。事务必须成功提交后方可进入下一步 |
| 8 | 触发 AI | Crawler 通过内部 HTTP 调用 `POST /api/v1/ai/analyze` 投递单篇分析任务。请求体携带 `article_id`、`raw_title`、`raw_content`。Crawler **不更新** `articles` 状态，等待返回 `202 Accepted` 后立即继续处理下一篇 |
| 9 | 任务完结 | 根据 `completed_urls` / `failed_urls` 终态决定 `crawler_tasks.status`：① 全部成功 → `completed`；② 部分成功 → `partial_failed`；③ 全部失败 → `failed`；同时记录 `completed_at` |

**`crawler_tasks.status` 状态机**：

```
pending ──[step 2 拾取执行]──> running ──[step 9 终结]──> completed | partial_failed | failed
   │                              │
   │                              └──[超时检测：running 超过 60min 未推进]──> failed（自动判失，写入 failed_details）
   │
   └──[启动时孤儿任务清理]──> failed（DB 事务残留检测）
```
- `running` 超时检测由定时任务执行（见 5.5），防止 Crawler 进程崩溃导致任务永久挂起
- 终态后不可回退；如需重跑需调用 `POST /api/v1/crawler/retry` 创建子任务

#### 2.1.4 字段定义（爬取输出）

| 字段名 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| `original_title` | String | 是 | 文章原始标题 |
| `source_unit` | String | 否 | 发布单位（如"工信部"、"新华社"）；LLM 兜底抽取允许为空（前端展示为"未知来源"） |
| `original_link` | URL | 是 | 原始文章链接 |
| `publish_date` | Date | 是 | 文章发布日期（ISO 8601） |
| `raw_content` | Text | 是 | 正文原始 HTML / Markdown |
| `crawl_time` | DateTime | 是 | 系统爬取时间 |
| `task_id` | UUID | 是 | 关联的爬取任务 ID |

#### 2.1.5 反爬策略（MVP）

**风险与策略分级**：

| 级别 | 适用场景 | 应对手段 | MVP 状态 |
| :--- | :--- | :--- | :--- |
| **L1** 基础反爬 | 无 WAF / 静态 HTML 政府门户 | UA 轮换、请求间隔抖动、行为模拟、请求头伪装 | ✅ 实现 |
| **L2** 商业反爬 | 普通电商/媒体站，存在 JS 指纹与基础风控 | SpiderAdapter 多策略体系（XPath/Readability/LLM 抽取自动降级），可选接入 Camoufox / Patchright 等二进制级补丁工具 | ✅ 实现（详见 2.1.10） |
| **L3** 动态渲染 | SPA / 懒加载 / 无限滚动 | DynamicRenderer 智能等待 + 自动滚动 + 元素交互 | ✅ 实现（详见 2.1.9） |
| **L4** 严苛反爬 | 高强度风控 / 行为指纹 / 验证码挑战 | AI 浏览器代理（Browser Use / Computer Use 风格）模拟人工操作 | ⏸ v1.1+ 预留接口（详见 2.1.8） |

**基础策略**：

- **User-Agent 轮换**：内置 20+ 主流浏览器 UA，每次请求随机选取。
- **请求间隔抖动**：基础间隔 2s ~ 5s 随机延迟，避免固定频率触发风控。
- **行为模拟**：Playwright 操作需加入随机鼠标移动、滚动延迟、页面停留时间（3s ~ 8s 随机）。
- **请求头伪装**：携带 Accept-Language、Referer、Cookie（如目标站点需要）。
- **IP 限速保护**：单域名并发限制为 2，防止被封禁。

**失败判定与降级**：

- 403/429 状态码触发重试。
- 403 连续 3 次后自动降级为更低频策略（基础间隔延长至 5s ~ 10s），而非固定间隔重试。
- 单次 URL 最多重试 3 次；若仍失败则触发 SpiderAdapter 降级链（XPath → Readability → LLM 抽取 → AIBrowserAgent 预留），所有策略均失败后记录失败原因，文章状态置为 `failed_permanent`，不影响同批次其他 URL。

#### 2.1.6 预留接口

**爬取任务**：
```
POST /api/v1/crawler/task       # 提交爬取任务
GET  /api/v1/crawler/tasks      # 查询任务列表（分页）
GET  /api/v1/crawler/tasks/{id} # 查询单个任务详情与进度
POST /api/v1/crawler/retry      # 对失败项发起重试
```

**站点发现与子域名发现**（详见 2.1.7）：
```
POST /api/v1/discover/site            # 提交起始 URL，发现站内候选文章 URL
POST /api/v1/discover/subdomains      # 提交根域名，发现候选子域名
GET  /api/v1/discover/results/{id}    # 查询发现结果（含候选列表与状态）
POST /api/v1/discover/submit          # 将勾选的候选 URL 批量提交至爬取队列
```

**白名单管理**（鉴权后管理后台调用）：
```
GET    /api/v1/admin/allowlist             # 查询白名单列表（支持按 match_mode / enabled / auto_added 过滤）
POST   /api/v1/admin/allowlist             # 新增白名单条目（exact / suffix / regex）
PUT    /api/v1/admin/allowlist/{id}        # 修改白名单条目（启用 / 禁用 / 改备注）
DELETE /api/v1/admin/allowlist/{id}        # 软删除白名单条目（可恢复）
POST   /api/v1/admin/allowlist/revoke-auto # 一键撤回 auto_added=true 的条目（批量禁用 + 软删除）
```

**适配器配置**（鉴权后管理后台调用，详见 2.1.10）：
```
GET    /api/v1/admin/spider-adapters         # 查询站点适配器配置列表
POST   /api/v1/admin/spider-adapters         # 新增站点适配器配置
PUT    /api/v1/admin/spider-adapters/{id}    # 修改站点适配器配置
DELETE /api/v1/admin/spider-adapters/{id}    # 删除站点适配器配置
```

**配置缓存刷新**（鉴权后管理后台调用，详见 5.4 配置缓存同步）：
```
POST /api/v1/admin/cache/refresh             # 立即刷新本 worker 的 allowed_domains / spider_adapter_configs 缓存（不等 TTL）
```

#### 2.1.7 站点发现与子域名管理

**功能定位**：
为用户提供"提交一个入口即可批量发现可爬 URL"的能力，避免依赖纯人工汇总 URL 列表。发现模块产出**候选 URL / 候选子域名清单**，用户勾选后批量提交至标准爬取队列；发现过程不直接执行内容抓取与入库，仅做轻量请求与解析。

**两个子能力**：

| 子能力 | 输入 | 实现路径 | 输出 |
| :--- | :--- | :--- | :--- |
| **SiteCrawler**（站内爬虫） | 起始 URL（如目标站点首页或栏目页） | ① sitemap.xml 解析 ② RSS/Atom feed 解析 ③ 起始页 BFS（最大深度 2，单任务发现 URL 上限 500，遵循 nofollow / robots.txt） | 候选文章 URL 列表，写入 `discovered_urls` 表，状态 `pending_review` |
| **SubdomainDiscover**（子域名发现） | 根域名（如 `example.com`） | ① crt.sh 证书透明度日志查询 ② 已知站点链接图聚合（合并 SiteCrawler 抓到的同根 URL） | 候选子域名列表，写入 `subdomain_candidates` 表；每条候选**自动**写入 `allowed_domains`（`match_mode=exact` + `auto_added=true`），运营可随时在管理后台撤回 |

**关键约束**：
- SiteCrawler 必须遵循目标站点 robots.txt，命中 `Disallow` 的 URL 不出现在候选清单中；用户可在管理后台开启"忽略 robots.txt"开关（默认关闭，开启需二次确认并记录操作审计日志）。
- **域名边界过滤**（前置过滤，避免后续提交时大量被白名单拒绝）：BFS 遍历过程中只收集"满足以下任一条件"的 URL：① 与起始 URL 同根域（eTLD+1 相同，如 `gov.cn` 下任意子域）；② 已在 `allowed_domains` 表中命中已启用记录。其余跨域链接直接丢弃，并在 `discover_tasks` 任务结果中累计 `filtered_out_count` 字段，便于运营回看。
- 单任务全程使用 SpiderAdapter 中相同的 UA 与请求间隔策略，避免发现阶段触发对方风控。
- SubdomainDiscover 在写入 `allowed_domains` 时强制使用 `match_mode=exact` 与 `auto_added=true`，禁止扩大为 suffix / regex；运营可调用 `POST /api/v1/admin/allowlist/revoke-auto` 一键批量撤回（批量禁用 + 软删除），保持合规可追溯。
- 发现结果保留 30 天，过期未提交则自动归档（`discover_tasks.status = archived`，关联的 `discovered_urls` / `subdomain_candidates` 同步标记）。

**调用流程**：
1. 用户在前端提交起始 URL 或根域名
2. 系统创建发现任务，APScheduler 调度执行
3. 任务完成后，前端通过 `GET /api/v1/discover/results/{id}` 获取候选清单
4. 用户勾选后调用 `POST /api/v1/discover/submit` 批量进入标准爬取队列（自动经过 2.1.2 协议 / IP / 白名单校验；SubdomainDiscover 路径下，子域名通常已在白名单中，无需额外维护）

#### 2.1.8 AI 浏览器代理兜底（v1.1+ 预留）

**功能定位**：
针对 SpiderAdapter 全链路降级（XPath → Readability → LLM 抽取）仍失败的"严苛反爬"站点，提供基于 AI 浏览器代理的最终兜底。**MVP 阶段仅定义接口契约与配额机制，不接入具体实现**，以避免成本失控并保持交付节奏。

**接口契约**（抽象类 `AIBrowserAgent`，与其它 SpiderAdapter 同构）：
- `match(url) -> bool`：仅当任务声明 `enable_ai_fallback=true` 且降级链已耗尽时返回 `true`
- `render(page, hint) -> RenderedPage`：调用 AI 代理执行打开 URL、识别正文、提取目标字段
- `extract(rendered) -> ArticleDraft`：返回结构化文章草稿
- `validate(draft) -> bool`：与其它适配器复用同一套校验逻辑

**触发条件**：
- 任务请求体显式指定 `enable_ai_fallback=true`（默认 `false`，避免误触成本）
- 该 URL 在标准降级链上的所有适配器均失败
- 全局/任务/用户三级配额均未触顶

**配额机制**（环境变量驱动）：
- `AI_BROWSER_DAILY_QUOTA`（全局每日上限，默认 50 次）
- `AI_BROWSER_TASK_QUOTA`（单任务上限，默认 10 次）
- 超限时直接返回失败，文章置为 `failed_permanent`，不阻塞同批次其它 URL

**实现技术（候选）**：
- Browser Use 开源框架（https://github.com/browser-use/browser-use）
- Anthropic Claude Computer Use API
- 阿里千问 / 月之暗面等具备 Computer Use 能力的国产模型

**MVP 边界**：
- 仅在 `app/modules/crawler/adapters/ai_browser/` 目录下创建抽象类与配额计数器骨架；具体集成代码、Prompt 模板、UI 配置面板延后至 v1.1+。
- API 层 `enable_ai_fallback=true` 的任务在 MVP 阶段直接返回 `5002 兜底能力暂未开放`，便于前端提前对接 UI 流程。

#### 2.1.9 动态渲染处理（DynamicRenderer）

**功能定位**：
在 Playwright 之上提供"把页面渲染到可提取状态"的统一编排层，覆盖 SPA、懒加载、无限滚动、模态遮罩等动态场景。SpiderAdapter 通过声明式配置调用 DynamicRenderer，二者职责完全解耦——DynamicRenderer 不关心如何抽取，SpiderAdapter 不关心如何渲染。

**四类原子能力**：

| 能力 | 说明 | 关键参数 |
| :--- | :--- | :--- |
| **智能等待** | 等待 CSS 选择器出现，或文档主体长度达到阈值；两种策略可组合，先到者优先 | `wait_for_selector`、`min_content_length`、`timeout_ms`（默认 15000） |
| **自动滚动** | 分段滚动到底部，触发懒加载与无限滚动；每段间隔 500–1500ms 抖动 | `scroll_to_bottom`、`scroll_step_px`（默认 800）、`max_scroll_rounds`（默认 20） |
| **网络空闲检测** | 等待 `networkidle` 事件 + 显式超时双约束；防止异步埋点请求拖死爬虫 | `wait_for_network_idle`、`network_idle_timeout_ms`（默认 5000） |
| **元素交互** | 点击"加载更多"、关闭弹窗遮罩、勾选时间筛选；每步可附带等待断言 | `actions: [{type, selector, wait_after}]` |

**配置驱动**：
- 每个 SpiderAdapter 在其配置中声明所需渲染策略（`spider_adapter_configs.render_config` JSONB 字段）
- 全局默认策略：`wait_for_selector="body"` + `min_content_length=500` + `wait_for_network_idle=true`
- 局部覆盖：站点定制配置覆盖全局默认

**性能与稳定性**：
- 单页面总渲染时长不超过 30s（硬上限），超时返回 `RENDER_TIMEOUT` 错误，进入降级

- **实例池作用域（A）**：
  - MVP 默认单 worker 部署（uvicorn），实例池为应用进程内**全局单例**，由 FastAPI `lifespan` 钩子负责创建/销毁
  - 生产部署使用 gunicorn 多 worker 时，每 worker **独立持有**自己的实例池，**单 worker 上限调整为 3 个 Chromium 进程**（避免总数 `worker × 5` 失控；典型 4 worker 部署下 Chromium 总数 = 12，单台 8 GB 机器仍有余量）
  - Playwright Browser 不支持跨进程共享，**v2.0 大规模场景**可演进为外置 Browserless / Playwright Server，本 PRD 不在 MVP 范围

- **重启触发与策略（B）**：
  - **触发方式**：每次页面渲染结束后由 DynamicRenderer 主动检查 `process.memory_info().rss`，**不使用独立定时器**（避免线程切换开销与内存毛刺误判）
  - **双阈值优雅降级**：
    - 软阈值 **1.0 GB**：进程标记为 `draining`，从实例池摘除，不再分配新任务；等当前在执行的任务自然结束后销毁该进程，并重建一个新实例补位
    - 硬阈值 **1.5 GB**（兜底，防 OOM）：立即 `kill -9` 该进程，进程内未完成任务标记 `RENDER_TIMEOUT` 错误并写入 `crawler_tasks.failed_details`，由 SpiderAdapter 降级链兜底
  - **重建期就绪保证**：若实例池可用进程数 < 1，新任务在请求队列中等待最多 10s（与 APScheduler `misfire_grace_time` 解耦的本地等待）；超时返回 `RENDER_TIMEOUT`，进入降级

- **实例生命周期（C）**：
  - 启动：FastAPI `lifespan startup` 预热 **1 个**实例（避免首请求冷启动 ≥ 3s 渲染延迟）
  - 运行：按需扩容至上限（每个新任务命中"无空闲实例 + 未达上限"时创建）；空闲超过 5 分钟的实例由后台清理任务回收（释放内存）
  - 关闭：`lifespan shutdown` 优雅销毁所有实例（先 `draining` 再 `close`），避免 Chromium 僵尸进程

- 渲染失败时附加截屏与 DOM 快照（保存在 `static/render_failures/{task_id}/{url_hash}.{png,html}`），辅助排查

#### 2.1.10 SpiderAdapter 多策略体系

**功能定位**：
将"内容提取"从单一 `Readability-lxml` 升级为可插拔、按域名注册、自动降级的多策略体系，覆盖政府门户、行业媒体、SPA、自媒体、结构异常站等异构场景。

**接口契约**（抽象基类 `SpiderAdapter`）：
- `match(url) -> bool`：判断本适配器是否适用
- `render(page) -> RenderedPage`：调用 DynamicRenderer 准备页面（也可直接返回静态 HTML）
- `extract(rendered) -> ArticleDraft`：抽取结构化字段（标题/正文/发布单位/发布时间）
- `validate(draft) -> bool`：质量校验（必填字段非空、正文 stripped 长度 ≥ 100、发布时间可解析）

**内置适配器**（按降级优先级从高到低）：

| 适配器 | 适用场景 | 实现方式 | 成本 | MVP 状态 |
| :--- | :--- | :--- | :--- | :--- |
| `XPathAdapter` | 已配置 XPath/CSS 规则的特定站点 | 按 `spider_adapter_configs.selectors` 精确取值 | 极低 | ✅ 实现 |
| `ReadabilityAdapter` | 默认通用方案，文章型页面 | `readability-lxml` 自动判别正文区域 | 低 | ✅ 实现（保留现有方案） |
| `LLMExtractionAdapter` | Readability 失败 / 结构异常 / 列表页与正文混排 | 截取主体 HTML（去脚本/样式/导航），调用 AI 中枢的国产大模型按统一 Prompt 输出 JSON 字段；模型供应商复用 2.2.6 配置（DeepSeek 优先，通义千问/文心一言备用），不引入新模型 | 中 | ✅ 实现 |
| `AIBrowserAgent` | 严苛反爬 / 行为指纹 / 验证码挑战 | 详见 2.1.8 | 高 | ⏸ v1.1+ 预留 |

**适配器选择与降级**：
- 启动时加载 `spider_adapter_configs` 表至**进程本地内存**（每个 gunicorn worker 独立持有一份缓存，详见 5.4 配置缓存同步）
- 处理 URL 时遍历"域名 → 适配器名 + 配置"映射，命中即用 `XPathAdapter`，未命中走默认链
- 默认降级链：`ReadabilityAdapter → LLMExtractionAdapter →（如启用）AIBrowserAgent`
- 每级失败原因（`STRUCTURE_NOT_MATCH` / `CONTENT_TOO_SHORT` / `LLM_PARSE_ERROR` 等）写入失败日志，便于运营回看

**LLMExtractionAdapter Prompt 输出格式**（统一约定）：
```json
{
  "original_title": "string",
  "source_unit": "string | null",
  "publish_date": "YYYY-MM-DD | null",
  "raw_content": "string (Markdown)",
  "confidence": 0.0
}
```
- `confidence < 0.5` 视为提取失败，触发下一级降级
- 模型参数：`temperature=0.1`、`max_tokens=4096`，与 AI 中枢的分类摘要任务隔离，便于成本归因
- **null 字段处理**：`source_unit` / `publish_date` 允许为 null（兜底场景下 LLM 无法识别），但 `original_title` 与 `raw_content` 必须非空，否则视为提取失败并触发下一级降级

**配置面板**（管理后台）：
- 列表页：展示已配置站点适配器、命中域名、最近成功率
- 编辑页：可视化配置 XPath 选择器、渲染策略（DynamicRenderer 字段）、降级链开关
- 试运行：粘贴样例 URL 即时运行该适配器，前端展示提取结果与失败原因

---

### 2.2 AI 智能中枢 (AI Intelligence Engine)

#### 2.2.1 功能定位

接收原始文章内容，调用国产大模型 API 进行多标签分类、置信度评分、智能摘要生成，并为后续封面图生成提供关键词输入。分析完成后，将对应文章状态由 `analyzing` 更新为 `processed`，并将结果写入 `ai_analysis` 表。

#### 2.2.2 分类体系

系统预置 **11 大分类标签**：

1. 最新政策
2. 数字经济
3. 人工智能
4. 数据要素
5. 通信
6. 申报
7. 潜在商机
8. 具身智能
9. 车路云协同
10. 新型工业化
11. 算力

#### 2.2.3 标签决策算法

1. **阈值过滤**：仅当分类置信度得分 $S \ge 0.6$ 时，该标签被视为有效。
2. **Top-K 策略**：若多个标签达标，系统自动选取相关度最高的前 **3** 个标签，按置信度降序排列。
3. **兜底机制**：若所有标签置信度均低于 0.6，标记为"未分类"，触发人工复核队列。

#### 2.2.4 智能摘要

- **长度要求**：150 ~ 200 个汉字（不含标点）。
- **质量要求**：提取文章核心论点、政策要点或商业机会，避免简单摘抄首段。
- **输出格式**：纯文本，段落结构清晰。

#### 2.2.5 封面图生成（预留）

MVP 阶段：AI 引擎返回封面图生成所需的**关键词组合**，由前端或文件服务基于预设模板合成占位图。

后续阶段：接入通义万相 / 文心一格等 AIGC 图像 API，根据标题与分类关键词自动合成**插画式背景图**。

#### 2.2.6 Prompt 工程规范

系统内置标准化 Prompt 模板，要求大模型输出严格的 JSON 格式：

```json
{
  "categories": [
    {"tag": "人工智能", "confidence": 0.92},
    {"tag": "算力", "confidence": 0.75}
  ],
  "summary": "本文围绕...展开，重点阐述了...",
  "keywords_for_cover": ["AI", "智算中心", "算力网络"]
}
```

- **模型参数**： temperature=0.3（保证输出稳定性），max_tokens=1024。
- **容错处理**：若模型返回非标准 JSON，尝试正则提取；若仍失败，记录异常并标记为"待人工处理"。

#### 2.2.7 预留接口

```
POST /api/v1/ai/analyze         # 单篇文章分析（分类+摘要）
POST /api/v1/ai/batch           # 批量文章分析（异步）
GET  /api/v1/ai/categories      # 获取全部分类定义
```

**Crawler → AI Engine 调用协议**：
- **调用通道**：内部 HTTP（进程内模块间通信，不走外部网络）。Crawler 调用 `POST /api/v1/ai/analyze` 投递任务，AI Engine 接口接收请求后将任务写入 APScheduler JobStore，由 APScheduler 调度实际分析执行。MVP 阶段全部异步任务统一由 APScheduler 管理，v2.0 可迁移至 Celery + RabbitMQ/Redis。
- **交互模式**：异步投递。Crawler 调用 AI Engine 接口后，等待返回 `202 Accepted` 即继续处理下一篇，不阻塞爬取；AI 分析由 APScheduler 在独立执行单元中调度执行。
- **数据传递**：Crawler 传递 `article_id`、`raw_title`、`raw_content` 的完整副本，AI Engine 不反向查询 Crawler 数据。
- **状态自驱**：AI Engine 被 APScheduler 调度执行时，在内部事务中查询 `articles.status`。若为 `raw` 则更新为 `analyzing` 并执行分析；若为 `analyzing`/`processed` 则幂等返回（已在处理或处理完成）；若为其他状态则拒绝执行并记录异常。
- **状态回写**：AI Engine 分析完成后，自行写入 `ai_analysis` 表，并将对应 `articles` 记录更新为 `processed`；若失败则更新为 `failed_retryable` 并记录失败原因。
- **时序约束**：Crawler 必须在 `articles` 事务提交成功后，再发起对 AI Engine 的调用。禁止在事务未提交时调用，防止 AI Engine 读到旧状态或查无此文。**实现层强制规则**：
  - 必须使用 `session.commit() → assert session.is_active is False → http.post(ai_engine)` 模式；commit 失败必须抛异常并跳过 HTTP 调用
  - **严禁**在 SQLAlchemy session context manager 内（含 async）调用 AI Engine HTTP，即便其声明为 fire-and-forget
  - 必须使用 SQLAlchemy `after_commit` 事件钩子触发 AI Engine 调用，而非 `after_flush`（后者在事务未提交前即触发）
  - 单元测试**必须覆盖"事务回滚"场景**：mock commit 失败，断言不会发起对 AI Engine 的 HTTP 调用
  - HTTP 客户端（httpx / aiohttp）必须在 commit 之后才创建/获取连接，禁止在事务上下文中预热连接池
- **异常边界**：若 AI Engine 崩溃导致无响应，`analyzing` 超时检测（5 分钟）自动将文章重置为 `failed_retryable`，由重试队列重新投递。

**APScheduler 关键配置**（统一适用 Crawler 任务、AI 分析、定时扫描三类作业，避免各模块各取默认引发不可预测行为）：

| 参数 | 取值 | 说明 |
| :--- | :--- | :--- |
| `jobstore` | `SQLAlchemyJobStore`（PostgreSQL，表名 `apscheduler_jobs`） | **独立 engine**，与业务 SQLAlchemy session 完全隔离，避免业务事务回滚影响任务入队，亦防止 JobStore 故障拖累业务请求 |
| `executors` | `ThreadPoolExecutor(max_workers=8)` 默认；CPU-bound 作业可挂 `ProcessPoolExecutor` | MVP 单实例够用 |
| `misfire_grace_time` | **300s**（默认 1s 不适用） | 任务延迟 5 分钟内仍执行，超时则视为错过（结合 `analyzing` 状态超时检测兜底，避免任务被静默丢弃） |
| `coalesce` | 定时扫描类作业（超时检测、死信归档、缓存 TTL 刷新）= `True`；逐文章触发的分析作业 = **`False`** | 区分对象：周期任务错过多次允许合并；逐 article 任务每条必须独立执行 |
| `max_instances` | AI 分析 = 4；Crawler 抓取 = 2（与单域名并发限一致）；定时任务 = 1 | 防止过载，单 job 类型同一时间运行实例上限 |
| `replace_existing` | `True` | 同 `job_id` 重复入队时覆盖，避免堆积；用于 `analyzing → failed_retryable` 重试场景 |
| `next_run_time` | 显式指定 `datetime.now(tz)` | 入队后立即调度（无显式触发时间需求） |

**任务入队幂等约定**：每个 article 的 AI 分析 `job_id` = `f"ai_analyze:{article_id}"`，依靠 `replace_existing=True` 保证同一 article 重复触发不会产生堆积；Crawler 任务 `job_id` = `f"crawl:{crawler_task_id}"`，定时任务 `job_id` 为模块固定常量（如 `analyzing_timeout_scan`、`dead_letter_archive`）。

---

### 2.3 结构化入库与前端数据服务 (Storage & Frontend Data Service)

#### 2.3.1 功能定位

文章元数据与 AI 加工数据统一存入数据库，为前端管理后台提供实时查询、筛选、统计的数据服务。

#### 2.3.2 入库逻辑

- **幂等性校验**：基于 `original_link` 建立唯一索引，同一 URL 重复抓取不入库，避免内容重复。
- **状态机**：

| 状态 | 含义 | 进入该状态的责任方 | 触发条件 |
| :--- | :--- | :--- | :--- |
| `raw` | 刚爬取，待分析 | Crawler Module | 步骤 7 完成，文章入库 |
| `analyzing` | AI 处理中 | AI Engine Module | 接收任务后内部更新 |
| `processed` | AI 分析完成 | AI Engine Module | 分析结果入库后更新 |
| `failed_retryable` | 可重试失败（AI 超时/异常） | AI Engine / 定时任务 | AI 分析超时/异常，待自动重试 |
| `failed_permanent` | 永久失败（不可修复） | AI Engine / Crawler | 爬取正文为空/被拦截，或重试耗尽 |
| `published` | 已推送微信 | WeChat Module（预留） | 草稿箱发布成功后更新 |
| `archived` | 已归档 | 定时任务 | 超过保留期自动归档 |

**失败补偿机制**：
- **analyzing 超时检测**：定时任务扫描 `analyzing` 状态超过 **5 分钟**的文章，自动置为 `failed_retryable`，由重试队列接管，防止 AI Engine 崩溃导致文章永久挂起。
- `analyzing → failed_retryable → failed_permanent`：AI 分析失败（非标准 JSON、模型异常）后自动重试 1 次；若仍失败，状态置为 `failed_permanent`，记录失败原因，进入人工复核队列。
- `raw → failed_permanent`：**抽取阶段全降级链耗尽**——XPath / Readability / LLMExtractionAdapter 均失败（含 `validate()` 不通过：必填字段空、`stripped_content < 100`、发布时间不可解析），且 AIBrowserAgent 未启用或配额触顶。article 直接以 `failed_permanent` 状态写入（不进入 `raw → analyzing` 流转，不入 AI 队列），失败层标识（`render_timeout` / `extract_validation_failed` / `llm_low_confidence` / `quota_exceeded`）追加至所属 `crawler_tasks.failed_details` 数组中。注：若任一适配器成功提取并通过 `validate()`，文章正常进入 `raw` 状态。
- **死信处理**：每日定时扫描 `failed_permanent` 状态超过 7 天的文章，自动转移至 `archived`，释放队列压力。`failed_retryable` 不参与死信处理，由重试机制单独管理。
- **数据保留策略**：
  - `processed` 文章保留 **90 天**，到期后自动转移至 `archived`
  - `failed_retryable` 文章保留 **7 天**（期间自动重试），若重试耗尽则转为 `failed_permanent`
  - `failed_permanent` 文章保留 **7 天**，到期后自动转移至 `archived`
  - `archived` 文章保留 **365 天**，到期后物理删除（可配置）
- **全文检索**：利用 PostgreSQL `tsvector` 或扩展 `pg_trgm`，支持标题与摘要的关键词搜索。

#### 2.3.3 前端数据展示

管理后台提供实时数据看板，支持按日期、分类、来源等维度浏览文章：

- **文章列表页**：展示当日/历史文章列表，支持按分类标签、发布单位、关键词筛选与分页；`failed_permanent` 文章默认隐藏，可通过"显示失败项"开关查看。
- **文章详情页**：展示单篇文章的完整信息，包括原始标题、发布单位、AI 摘要、分类标签及置信度、原文链接；`failed_permanent` 文章在管理后台可见并标记失败原因（如"正文为空"、"结构解析失败"、"AI 分析异常"）。
- **数据统计看板**：按日期维度展示文章总量、各分类分布数量、来源单位 Top N 等聚合统计；统计口径默认仅包含 `processed` 状态文章，`failed_permanent` 不计入。
- **实时性**：前端直接查询数据库，数据在 AI 分析完成后（`processed` 状态）即刻可见。

#### 2.3.4 数据服务接口

```
GET /api/v1/articles                   # 查询文章列表（支持日期、分类、关键词筛选，分页）
GET /api/v1/articles/{id}              # 查询单篇文章详情
GET /api/v1/stats/daily                # 获取指定日期的分类分布统计
GET /api/v1/dates                      # 获取有数据的日期列表
```

---

### 2.4 微信公众号全自动分发（v2.0 预留）

**目标**：将文章自动发布至微信公众号草稿箱，含排版转义与封面图生成。

**MVP 阶段**：模块目录保留（`app/modules/wechat/`），仅记录日志占位，不实现业务逻辑、不建表、不暴露路由。详细设计延后至 v2.0 规划文档。

**预留接口（MVP 阶段返回 `4002 功能开发中`）**：
```
POST /api/v1/wechat/publish
```
- 请求体：文章 ID 列表 + 排版模板选择（v2.0 详细定义）。
- MVP 阶段：任何调用均返回 `4002`，便于前端提前对接按钮与状态展示。

---

### 2.5 商业级专业文档导出（v2.0 预留）

**目标**：支持自定义 Logo、水印、目录的 Word 导出。

**MVP 阶段**：模块目录保留（`app/modules/export/`），仅记录日志占位。详细设计延后至 v2.0 规划文档。

**预留接口（MVP 阶段返回 `4002 功能开发中`）**：
```
POST /api/v1/export/word
```
- 请求体：文章 ID 列表 + 水印文字 + Logo 配置（v2.0 详细定义）。
- MVP 阶段：任何调用均返回 `4002`，便于前端提前对接导出按钮。

---

### 2.6 智能订阅与定时通知（v2.0 预留）

**目标**：按关键词订阅，每日邮件推送匹配文章。

**MVP 阶段**：模块目录保留（`app/modules/subscription/`），仅记录日志占位。详细设计延后至 v2.0 规划文档。

**预留接口（MVP 阶段返回 `4002 功能开发中`）**：
```
POST /api/v1/subscribe/register
GET  /api/v1/subscribe/list
DELETE /api/v1/subscribe/{id}
```
- 请求体：主题词 + 目标网站 + 接收邮箱（v2.0 详细定义）。
- MVP 阶段：任何调用均返回 `4002`，便于前端提前对接订阅表单。

---

## 3. 技术接口标准 (API Schema)

### 3.1 统一响应格式

所有 API 响应均遵循以下结构：

```json
{
  "code": 0,
  "message": "success",
  "data": { ... },
  "request_id": "uuid-for-tracing"
}
```

- `code`: `0` 表示成功，非零为业务错误码。
- `message`: 人类可读的状态描述。
- `data`: 实际业务数据，`null` 或 `{}` 视接口而定。
- `request_id`: 用于分布式链路追踪的唯一标识。

### 3.2 API 鉴权与访问控制（MVP）

MVP 阶段采用**单管理员模式**，不实现多用户注册登录体系。

**鉴权方案**：
- **管理后台**：基于 HTTP Only Cookie 的 Session 鉴权（`session_id`），登录态由后端维护，前端 Next.js Server Components 直接透传 Cookie。
- **API Key（可选）**：如存在第三方系统调用需求，可通过环境变量配置单个 `ADMIN_API_KEY`，请求头携带 `X-API-Key` 进行鉴权。
- **未鉴权响应**：`401 Unauthorized`，`code: 4001`。

**权限边界**：
- MVP 仅区分"已登录管理员"与"未登录访客"
- 所有管理操作（提交爬取任务、查看文章数据）均需鉴权
- 预留 `users` 与 `roles` 表设计空间，v2.0 迁移至多租户 RBAC

### 3.3 文章结构化数据模型

```json
{
  "article_id": "550e8400-e29b-41d4-a716-446655440000",
  "meta": {
    "title": "关于推动人工智能产业高质量发展的若干措施",
    "source_unit": "北京市经济和信息化局",
    "original_link": "https://example.gov.cn/xxgk/2026-04-23/12345.html",
    "publish_date": "2026-04-23",
    "crawl_time": "2026-04-23T14:30:00+08:00"
  },
  "ai_analysis_id": "550e8400-e29b-41d4-a716-446655440001",
  "content": {
    "format": "markdown",
    "body": "# 关于推动人工智能产业高质量发展的若干措施\n\n各区人民政府..."
  },
  "status": "processed",
  "task_id": "task-uuid-123"
}
```

### 3.4 核心接口 DTO 定义

#### Crawler Task Request

```json
{
  "task_name": "可选",
  "target_date": "2026-04-23",
  "url_list": ["string"],
  "callback_url": "string (URL, 可选)",
  "priority": 1,
  "enable_ai_fallback": false,
  "adapter_hint": "xpath | readability | llm_extraction | null"
}
```

- `enable_ai_fallback`：是否允许在标准降级链耗尽后调用 AIBrowserAgent（v1.1+ 预留），MVP 阶段传 `true` 将返回 `5002`。
- `adapter_hint`：可选，指定首选适配器（用于内部测试或运营定向覆盖默认匹配）。

#### Crawler Task Response

```json
{
  "task_id": "uuid",
  "status": "pending",
  "total_urls": 10,
  "completed_urls": 0,
  "failed_urls": 0,
  "created_at": "2026-04-24T10:00:00+08:00"
}
```

#### AI Analyze Request

```json
{
  "article_id": "uuid",
  "raw_content": "string (Markdown/HTML)",
  "raw_title": "string"
}
```

#### AI Analyze Response

```json
{
  "article_id": "uuid",
  "categories": [{"tag": "string", "confidence": 0.0}],
  "summary": "string",
  "keywords_for_cover": ["string"],
  "processing_time_ms": 1250
}
```

#### Articles Query

```json
{
  "date": "2026-04-23",
  "category": "人工智能",
  "keyword": "算力",
  "source_unit": "",
  "page": 1,
  "page_size": 20
}
```

#### Daily Stats Response

```json
{
  "date": "2026-04-23",
  "total": 15,
  "categories": [
    {"tag": "人工智能", "count": 5},
    {"tag": "算力", "count": 3}
  ],
  "top_sources": [
    {"source_unit": "工信部", "count": 4}
  ]
}
```

#### Site Discover Request

```json
{
  "start_url": "https://example.gov.cn/zwgk/",
  "max_depth": 2,
  "max_urls": 500,
  "respect_robots": true
}
```

#### Subdomain Discover Request

```json
{
  "root_domain": "example.gov.cn",
  "evidence_sources": ["crt_sh", "link_graph"]
}
```

#### Discover Result Response

```json
{
  "task_id": "uuid",
  "status": "completed",
  "type": "site | subdomain",
  "items": [
    {"id": "uuid", "value": "https://example.gov.cn/zwgk/2026-04-23.html", "title_hint": "...", "source": "sitemap"}
  ],
  "total": 42,
  "discovered_at": "2026-04-23T10:00:00+08:00"
}
```

#### Discover Submit Request

```json
{
  "discover_task_id": "uuid",
  "selected_ids": ["uuid", "uuid"],
  "crawler_task_options": {
    "task_name": "可选",
    "target_date": "2026-04-23",
    "priority": 1,
    "enable_ai_fallback": false
  }
}
```

#### Allowlist Item

```json
{
  "id": "uuid",
  "domain_pattern": "example.gov.cn",
  "match_mode": "exact",
  "enabled": true,
  "auto_added": false,
  "source": "manual",
  "remark": "可选备注",
  "created_by": "admin",
  "created_at": "2026-04-23T10:00:00+08:00"
}
```

### 3.5 错误码规范

**HTTP 状态码与业务 code 关系**：HTTP 状态码反映传输/协议层结果，业务 code 反映业务层结果。规则如下：
- 同步 API（参数校验、鉴权、资源查找）：HTTP 4xx/5xx 与业务 code 同时返回，便于前端拦截器分流
- 异步任务结果（爬取失败、AI 失败、降级耗尽）：HTTP 仍返回 `202 Accepted` 或 `200`（请求被成功受理），具体失败码写入 `crawler_tasks.failed_details` / `articles.status` 等持久化字段
- 业务 `code=0` 即视为"请求语义成功"，不论实际处理结果

| 错误码 | HTTP Status | 含义 | 场景示例 | 触发场景 |
| :--- | :--- | :--- | :--- | :--- |
| `0` | `200 / 202` | 成功 | — | 同步成功 / 异步受理 |
| `1001` | `400` | 参数校验失败 | 必填字段缺失、日期格式错误、URL 列表超限 | 同步 |
| `1002` | `404` | 资源不存在 | 查询的 article_id / task_id 不存在 | 同步 |
| `1003` | `400` | 协议非法 | 提交的 URL 协议不是 HTTP/HTTPS（如 `file://`、`ftp://`） | 同步 |
| `1004` | `400` | 域名未在白名单 | URL 域名未命中 `allowed_domains` 已启用记录 | 同步 |
| `1005` | `400` | 命中 SSRF 防护 | URL 解析后指向 Loopback / 内网 / 保留段 IP | 同步 |
| `2001` | `200` | 爬取任务失败 | 目标网站返回 403/404，或反爬拦截耗尽降级链 | 异步（写入 failed_details） |
| `2002` | `200` | AI 分析失败 | 大模型 API 超时或返回异常 | 异步（写入 articles.status） |
| `2003` | `200` | 适配器降级耗尽 | XPath / Readability / LLM 抽取均失败，且未启用 AIBrowserAgent | 异步（写入 failed_details.layer） |
| `4001` | `401` | 未鉴权 | Session 失效或 API Key 错误 | 同步 |
| `4002` | `503` | 服务不可用 | 微信/邮件预留接口，提示"功能开发中" | 同步 |
| `5001` | `500` | 系统内部错误 | 数据库连接异常、未知错误 | 同步 |
| `5002` | `503` | 兜底能力暂未开放 | 任务声明 `enable_ai_fallback=true`，但 MVP 阶段尚未集成 AIBrowserAgent | 同步 |

---

## 4. 数据库 ERD 设计

### 4.1 实体关系概述

- 一个 `crawler_task` 可以产生多个 `article`（1:N）。
- 一个 `article` 经过一次 `ai_analysis` 加工（1:1）。
- 一个 `user` 可以创建多个 `subscription`（1:N）。
- 一个 `user` 可以提交多个 `export_task` 和 `wechat_task`（1:N）。
- 一个 `discover_task` 可以产生多条 `discovered_url`（站点发现型）或多条 `subdomain_candidate`（子域名发现型）（1:N）；后者按 ADR-01 自动写入 `allowed_domains`（`auto_added=true`）。
- `discovered_url` 被勾选并提交后，可生成对应的 `crawler_task`（N:1，通过 `submitted_to_task_id` 字段反向追溯）。
- `allowed_domains` 与 `spider_adapter_configs` 互不强引用，按 `domain_pattern` + `match_mode` 在运行时各自查表，逻辑解耦。

### 4.2 表结构定义

#### `articles` — 文章主表

| 字段名 | 类型 | 约束 | 说明 |
| :--- | :--- | :--- | :--- |
| `id` | UUID | PK, 默认 gen_random_uuid() | 文章唯一标识 |
| `task_id` | UUID | FK → crawler_tasks.id | 关联爬取任务 |
| `original_title` | VARCHAR(512) | NOT NULL | 原始标题 |
| `source_unit` | VARCHAR(256) | | 发布单位（XPath/Readability 命中时必填；LLMExtractionAdapter 兜底允许为空，由前端展示为"未知来源"） |
| `original_link` | TEXT | NOT NULL, UNIQUE | 原文链接 |
| `publish_date` | DATE | NOT NULL | 发布日期 |
| `raw_content` | TEXT | | 原始正文（HTML/Markdown） |
| `status` | VARCHAR(32) | 默认 'raw' | `raw/analyzing/processed/failed_retryable/failed_permanent/published/archived` |
| `created_at` | TIMESTAMPTZ | 默认 now() | 入库时间 |
| `updated_at` | TIMESTAMPTZ | 默认 now() | 更新时间 |

**索引**：
- `idx_articles_publish_date` (publish_date DESC)
- `idx_articles_status` (status)
- `idx_articles_source_unit` (source_unit)
- `idx_articles_original_link` (original_link) UNIQUE

#### `ai_analysis` — AI 分析结果表

| 字段名 | 类型 | 约束 | 说明 |
| :--- | :--- | :--- | :--- |
| `id` | UUID | PK, 默认 gen_random_uuid() | 分析记录唯一标识 |
| `article_id` | UUID | FK → articles.id, UNIQUE | 关联文章（1:1） |
| `categories` | JSONB | 默认 '[]' | 分类标签数组 `[{"tag":"...", "confidence":0.9}]` |
| `summary` | TEXT | | AI 生成摘要 |
| `cover_image` | TEXT | | 封面图相对路径/URL |
| `keywords` | JSONB | 默认 '[]' | 关键词数组 |
| `model_used` | VARCHAR(64) | | 使用的大模型标识（如 deepseek-v3） |
| `processing_time_ms` | INTEGER | | 处理耗时（毫秒） |
| `created_at` | TIMESTAMPTZ | 默认 now() | 分析完成时间 |

**索引**：
- `idx_ai_analysis_article_id` (article_id)
- `idx_ai_analysis_categories` (categories GIN)

#### `crawler_tasks` — 爬取任务表

| 字段名 | 类型 | 约束 | 说明 |
| :--- | :--- | :--- | :--- |
| `id` | UUID | PK | 任务唯一标识 |
| `task_name` | VARCHAR(256) | | 任务名称 |
| `target_date` | DATE | NOT NULL | 目标爬取日期 |
| `url_list` | JSONB | NOT NULL | URL 数组 |
| `total_urls` | INTEGER | 默认 0 | 总 URL 数 |
| `completed_urls` | INTEGER | 默认 0 | 成功数 |
| `failed_urls` | INTEGER | 默认 0 | 失败数 |
| `failed_details` | JSONB | 默认 '[]' | 失败记录 `[{"url":"...", "reason":"...", "layer":"render_timeout|extract_validation_failed|llm_low_confidence|quota_exceeded|..."}]` |
| `status` | VARCHAR(32) | 默认 'pending' | `pending/running/completed/failed/partial_failed` |
| `callback_url` | TEXT | | 异步回调地址 |
| `priority` | INTEGER | 默认 1 | 优先级（数字越小越优先） |
| `started_at` | TIMESTAMPTZ | | 任务开始时间 |
| `completed_at` | TIMESTAMPTZ | | 任务完成时间 |
| `created_at` | TIMESTAMPTZ | 默认 now() | 创建时间 |

#### `discover_tasks` — 站点 / 子域名发现任务

| 字段名 | 类型 | 约束 | 说明 |
| :--- | :--- | :--- | :--- |
| `id` | UUID | PK, 默认 gen_random_uuid() | 任务唯一标识 |
| `type` | VARCHAR(16) | NOT NULL, CHECK in (`site`,`subdomain`) | 任务类型：站内爬虫 / 子域名发现 |
| `input_payload` | JSONB | NOT NULL | 输入参数完整副本（`Site Discover Request` 或 `Subdomain Discover Request`） |
| `status` | VARCHAR(32) | 默认 `pending` | `pending / running / completed / failed / archived` |
| `total_discovered` | INTEGER | 默认 0 | 已发现条数（`discovered_urls` 或 `subdomain_candidates`） |
| `filtered_out_count` | INTEGER | 默认 0 | SiteCrawler 类型任务中被域名边界过滤丢弃的 URL 数（详见 2.1.7） |
| `error_message` | TEXT | | 失败原因（`status=failed` 时填充） |
| `started_at` | TIMESTAMPTZ | | 任务开始时间 |
| `completed_at` | TIMESTAMPTZ | | 任务完成时间 |
| `created_at` | TIMESTAMPTZ | 默认 now() | 创建时间 |

**索引**：
- `idx_discover_tasks_status` (status, created_at DESC)
- `idx_discover_tasks_type` (type)

#### `allowed_domains` — 动态域名白名单

| 字段名 | 类型 | 约束 | 说明 |
| :--- | :--- | :--- | :--- |
| `id` | UUID | PK, 默认 gen_random_uuid() | 主键 |
| `domain_pattern` | VARCHAR(512) | NOT NULL | 域名模式：精确域名 / 后缀（如 `gov.cn`）/ 正则表达式 |
| `match_mode` | VARCHAR(16) | NOT NULL, CHECK in (`exact`,`suffix`,`regex`) | 匹配模式 |
| `enabled` | BOOLEAN | 默认 TRUE | 是否启用（禁用即视为不命中） |
| `auto_added` | BOOLEAN | 默认 FALSE | 是否由 SubdomainDiscover 自动入白；`revoke-auto` 接口仅作用于该字段为 TRUE 的记录 |
| `source` | VARCHAR(32) | 默认 `manual` | 来源：`manual` / `env_seed` / `subdomain_discover` |
| `remark` | TEXT | | 备注（如政策文件出处、维护理由） |
| `created_by` | VARCHAR(64) | | 创建者（admin 用户名 / 系统标识） |
| `created_at` | TIMESTAMPTZ | 默认 now() | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 默认 now() | 最近修改时间 |
| `deleted_at` | TIMESTAMPTZ | | 软删除时间戳，非 NULL 即视为不命中 |

**索引**：
- `idx_allowed_domains_enabled` (enabled, deleted_at)
- `idx_allowed_domains_pattern` (domain_pattern)
- `idx_allowed_domains_auto_added` (auto_added) WHERE auto_added = TRUE

#### `discovered_urls` — 站点发现候选 URL

| 字段名 | 类型 | 约束 | 说明 |
| :--- | :--- | :--- | :--- |
| `id` | UUID | PK, 默认 gen_random_uuid() | 主键 |
| `discover_task_id` | UUID | NOT NULL, FK → discover_tasks.id | 关联的发现任务 ID |
| `url` | TEXT | NOT NULL | 候选文章 URL |
| `title_hint` | VARCHAR(512) | | 抓取的页面标题片段（辅助人工筛选） |
| `source` | VARCHAR(32) | NOT NULL | 来源：`sitemap` / `rss` / `bfs` |
| `status` | VARCHAR(32) | 默认 `pending_review` | `pending_review` / `submitted` / `archived` |
| `submitted_to_task_id` | UUID | FK → crawler_tasks.id | 勾选提交后生成的爬取任务 ID（追溯用） |
| `discovered_at` | TIMESTAMPTZ | 默认 now() | 发现时间 |
| `submitted_at` | TIMESTAMPTZ | | 提交至爬取队列的时间 |

**索引**：
- `idx_discovered_urls_task` (discover_task_id, status)
- `idx_discovered_urls_url` (url) — 同一发现任务内 URL 去重靠业务层处理

#### `subdomain_candidates` — 子域名发现候选

| 字段名 | 类型 | 约束 | 说明 |
| :--- | :--- | :--- | :--- |
| `id` | UUID | PK, 默认 gen_random_uuid() | 主键 |
| `discover_task_id` | UUID | NOT NULL, FK → discover_tasks.id | 关联的发现任务 ID |
| `root_domain` | VARCHAR(256) | NOT NULL | 根域名 |
| `subdomain` | VARCHAR(256) | NOT NULL | 候选子域名 |
| `evidence` | VARCHAR(32) | NOT NULL | 证据来源：`crt_sh` / `link_graph` |
| `reachable` | BOOLEAN | | 是否可访问（HEAD 探测，仅作展示） |
| `auto_allowlisted` | BOOLEAN | 默认 FALSE | 是否已自动写入 `allowed_domains` |
| `discovered_at` | TIMESTAMPTZ | 默认 now() | 发现时间 |

**索引**：
- `idx_subdomain_candidates_task` (discover_task_id)
- `idx_subdomain_candidates_subdomain` (subdomain)

#### `spider_adapter_configs` — SpiderAdapter 站点配置

| 字段名 | 类型 | 约束 | 说明 |
| :--- | :--- | :--- | :--- |
| `id` | UUID | PK, 默认 gen_random_uuid() | 主键 |
| `domain_pattern` | VARCHAR(512) | NOT NULL | 命中本配置的域名模式（exact / suffix / regex） |
| `match_mode` | VARCHAR(16) | NOT NULL, CHECK in (`exact`,`suffix`,`regex`) | 匹配模式 |
| `adapter_name` | VARCHAR(32) | NOT NULL | 首选适配器：`xpath` / `readability` / `llm_extraction` |
| `selectors` | JSONB | 默认 '{}' | XPathAdapter 字段选择器（title / content / source_unit / publish_date） |
| `render_config` | JSONB | 默认 '{}' | DynamicRenderer 配置（详见 2.1.9） |
| `fallback_chain` | JSONB | 默认 '["readability","llm_extraction"]' | 自定义降级链（覆盖默认顺序） |
| `enabled` | BOOLEAN | 默认 TRUE | 是否启用 |
| `priority` | INTEGER | 默认 100 | 同时命中多条配置时按优先级取较小值 |
| `last_success_at` | TIMESTAMPTZ | | 最近一次成功提取时间（运营观测用） |
| `success_rate_7d` | NUMERIC(5,4) | | 近 7 天成功率（定时任务回填） |
| `created_at` | TIMESTAMPTZ | 默认 now() | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 默认 now() | 最近修改时间 |

**索引**：
- `idx_spider_adapter_configs_pattern` (domain_pattern, enabled)
- `idx_spider_adapter_configs_priority` (priority)

> **v2.0 预留表说明**：`users`、`subscriptions`、`export_tasks`、`wechat_tasks` 等表跟随对应功能模块（2.4–2.6）延后设计，MVP 阶段不创建。

---

## 5. 非功能性需求

### 5.1 性能指标

| 指标 | MVP 目标 | 说明 |
| :--- | :--- | :--- |
| 单篇文章爬取 | ≤ 10s | 含页面渲染与内容提取（XPath / Readability 命中场景） |
| 单篇文章爬取（LLM 抽取兜底） | ≤ 25s | 含 LLM 抽取调用，单次 max_tokens=4096 |
| 动态渲染单页（P95） | ≤ 8s | DynamicRenderer 智能等待 + 滚动 + 网络空闲，硬上限 30s 触发降级 |
| 站点发现单任务（500 URL 上限） | ≤ 5min | sitemap + RSS + BFS 综合，遵循 robots.txt 与延迟抖动 |
| 批量爬取 100 篇（同域名） | ≤ 45min | 单域名并发限制 2，含 2~5s 延迟与最多 3 次重试 |
| 批量爬取 100 篇（多域名） | ≤ 15min | 域名分散时可充分利用并发 |
| AI 单篇分析（P95） | ≤ 10s | 含网络往返与大模型推理；超时自动重试 1 次 |
| 接口响应 (P95) | ≤ 500ms | 不涉及 AI 与文件生成的查询类接口 |

### 5.2 安全规范

- **输入过滤**：所有用户输入（URL、关键词、邮箱）必须经过 Pydantic 严格校验与 SQL 注入过滤。
- **URL 安全**：
  - **协议层**：仅允许 HTTP/HTTPS 协议，拒绝 `file://`、`ftp://`、`gopher://` 等其它协议（违反返回 `1003`）。
  - **网络层**（SSRF 防护）：解析后的目标 IP 不得指向 Loopback / 保留段 / 内网网段（10.0.0.0/8、172.16.0.0/12、192.168.0.0/16、127.0.0.0/8、169.254.0.0/16、::1、fc00::/7、fe80::/10），DNS 解析后再次校验避免绕过（违反返回 `1005`）。
  - **应用层**（动态白名单）：URL 域名必须命中 `allowed_domains` 表中**已启用且未软删除**的记录，匹配支持 exact / suffix / regex 三种模式。环境变量 `ALLOWED_DOMAINS` 仅作首次启动 seed，运行时以数据库为准（违反返回 `1004`）。
  - **管理责任**：白名单 CRUD 仅管理员可调用，所有变更写入审计日志；`auto_added=true` 条目可由 `revoke-auto` 接口一键撤回。
- **数据隔离**：多租户场景下（未来），用户仅可见自己提交的任务与文章。
- **日志脱敏**：日志中不得明文记录邮箱、API Key、Cookie 等敏感信息。
- **文件上传限制**：封面图/Logo 上传限制为 5MB，仅接受 JPG/PNG，后端二次校验 MIME 类型。

### 5.3 扩展性预留

- **消息队列**：`crawler_tasks`、`ai_analysis`、`export_tasks`、`wechat_tasks` 均设计为异步任务模型，未来可将 APScheduler 替换为 Celery + RabbitMQ/Redis 实现分布式任务队列。
- **对象存储**：文件路径字段统一使用相对路径 `/static/...`，未来可无缝替换为 CDN 域名前缀。
- **多模型路由**：AI Engine 预留模型供应商配置表，支持按分类或按负载切换不同大模型供应商。
- **插件化爬虫**：爬虫模块已落地多策略 SpiderAdapter 体系（详见 2.1.10），内置 `XPathAdapter` / `ReadabilityAdapter` / `LLMExtractionAdapter` 三类策略，预留 `AIBrowserAgent` 抽象类（v1.1+ 预留，详见 2.1.8）。新增站点适配器仅需配置注册表，无需改动核心流程。

### 5.4 可维护性

- **代码规范**：Python 遵循 PEP8 + Black 格式化；TypeScript 遵循 ESLint + Prettier。
- **接口文档**：FastAPI 原生自动生成 Swagger UI (`/docs`) 和 ReDoc (`/redoc`)，无需额外维护。
- **数据库迁移**：所有表结构变更必须通过 Alembic 迁移脚本执行，禁止手工改表。
- **容器化**：提供 `docker-compose.yml`，一键启动 PostgreSQL + 后端 + 前端全部服务。
- **配置缓存同步**：生产环境通常以 gunicorn 多 worker 进程运行，需要解决"管理员在 worker A 修改配置，worker B 看不到"的一致性问题。MVP 采用如下统一策略：

  | 配置类型 | 缓存载体 | 刷新机制 | 最大延迟 |
  | :--- | :--- | :--- | :--- |
  | `allowed_domains` | 进程本地内存（dict + 索引） | ① 启动时全量加载 ② 每 30s TTL 自然过期重载 ③ CRUD 接口处理后立即重建本机缓存 | 全集群最长 30s |
  | `spider_adapter_configs` | 进程本地内存（按域名索引） | 同上 | 全集群最长 30s |

  - **强制刷新接口**：`POST /api/v1/admin/cache/refresh`（鉴权后调用），返回该 worker 的刷新结果；运维需在所有 worker 上轮询触发，或重启服务保证立即生效
  - **不引入 Redis / LISTEN-NOTIFY**：MVP 阶段单实例部署，30s TTL 足够；v2.0 多实例时可升级为 PostgreSQL `LISTEN/NOTIFY` 跨进程通知，无需 Redis 依赖
  - **TTL 期内的不一致是预期行为**：白名单变更后 30s 内某些 worker 可能仍按旧规则放行/拒绝；运营需在变更前知晓此延迟（管理后台保存按钮提示"变更将在 30 秒内全集群生效"）

### 5.5 可观测性（MVP 最小实践）

**核心监控指标**：

| 指标 | 采集方式 | 告警阈值 |
| :--- | :--- | :--- |
| 爬取成功率 | 定时任务结束后计算 `completed_urls / total_urls` | < 80% 触发告警 |
| AI 分析成功率 | 定时扫描 `articles.status` 中 `failed_retryable` + `failed_permanent` 占总分析任务（`processed` + 两类 failed）的比例 | > 20% 触发告警 |
| 数据查询响应时间 | 定时采样文章列表、统计接口 P95 | > 1s 触发告警 |
| Chromium 内存占用 | 每渲染结束后采样 `process.memory_info().rss` | 软 1.0 GB → `draining` 重建；硬 1.5 GB → 立即 kill（详见 2.1.9） |
| Chromium 实例池可用度 | 每分钟统计可用实例数 / 上限 | < 50% 持续 5 分钟触发告警，提示运维扩容或排查渲染卡顿 |
| SpiderAdapter 降级率 | 统计 LLMExtractionAdapter 命中次数 / 总抽取次数 | > 30% 触发预警，提示 XPath / Readability 配置可能需要补全 |
| 适配器配置成功率（7 天滑窗） | 由 `spider_adapter_configs.success_rate_7d` 字段定时回填 | < 70% 触发告警，提示该站点规则失效 |
| 站点发现耗时 | 单次发现任务结束后记录 | P95 > 8min 触发告警 |
| AI 浏览器代理日调用量（v1.1+） | 预留指标，正式上线后采集 | 接近 `AI_BROWSER_DAILY_QUOTA` 80% 触发预警 |

**日志规范**：
- 统一 JSON 格式，必含字段：`timestamp`、`level`、`message`、`trace_id`（即 `request_id` 或 `task_id`）
- 敏感信息脱敏：邮箱、API Key、Cookie 字段值替换为 `***`

**链路追踪**：
- 单次爬取任务：Crawler Task → Article → AI Analysis，通过 `task_id` 串联
- 单次 API 请求：通过 `request_id` 串联入口到数据库

---

### 5.6 部署架构（Docker Compose）

**服务拓扑**：

```
┌─────────────────────────────────────────┐
│            Docker Compose 网络           │
│  ┌──────────┐  ┌──────────┐            │
│  │  nextjs  │  │ fastapi  │            │
│  │  :3000   │  │  :8000   │            │
│  └────┬─────┘  └────┬─────┘            │
│       │             │                  │
│       └──────┬──────┘                  │
│              │ 内部 HTTP                │
│       ┌──────┴──────┐                  │
│       │ postgresql  │                  │
│       │   :5432     │                  │
│       └─────────────┘                  │
│              │                         │
│       ┌──────┴──────┐                  │
│       │  data volume│ (持久化)          │
│       │  /var/lib/  │                  │
│       └─────────────┘                  │
└─────────────────────────────────────────┘
```

**端口映射**：
- `3000` → Next.js 前端（反向代理或直连）
- `8000` → FastAPI 后端（`/docs` 自动 Swagger）
- `5432` → PostgreSQL（仅内部网络暴露，不映射宿主机端口）

**数据持久化**：
- PostgreSQL 数据卷：`postgres_data`
- 文件存储目录：`./static:/app/static`（宿主机挂载，用于封面图等静态文件）

**环境变量**：
- `.env` 文件管理：数据库连接字符串、AI 模型 API Key、管理员密码哈希
- **禁止**将 `.env` 提交至代码仓库

---

### 5.7 隐私合规底线（MVP）

MVP 阶段须建立数据隐私的**不可突破底线**，确保系统在首日运行时不因合规缺失导致用户数据泄露或版权风险。

#### 5.7.1 内容存储最小化

**约束**：系统对爬取的第三方内容，仅可存储用于检索和摘要展示所必需的元数据（标题、发布单位、发布时间、原文链接、内容摘要）。**禁止在系统内永久存储第三方内容的完整原文副本**。用户阅读全文时，必须通过原文链接跳转至原始发布站点。

**验收标准**：数据库中任意文章记录的正文字段长度不得超过摘要所需上限，且必须提供可追溯的原文链接。

#### 5.7.2 用户凭证与敏感信息保护

**约束**：系统收集或生成的任何用户凭证（密码、API Key、Session Token）必须采用不可逆的密码学算法处理，禁止以明文或弱哈希形式存储。系统日志、接口响应、错误堆栈中不得包含可识别的个人隐私信息（如完整邮箱、密钥原文、Cookie）。

**验收标准**：
- 对数据库进行物理文件导出后，无法直接读取用户密码原文。
- 任意日志级别下，邮箱字段必须脱敏，API Key 必须替换为掩码。

#### 5.7.3 第三方凭证管理

**约束**：所有第三方服务凭证（大模型 API Key、微信 Secret、邮件 SMTP 密码）必须通过环境变量注入，**禁止随代码仓库分发**。代码中不得出现硬编码的密钥字符串。

**验收标准**：删除 `.env` 文件后，系统无法启动，且代码仓库中不存在任何有效密钥。

#### 5.7.4 爬取合规边界

**约束**：爬虫引擎在请求目标 URL 前，必须读取并遵守该站点的 `robots.txt` 协议。若路径被 `Disallow`，则该 URL 在提交时即被拒绝。仅允许 HTTP/HTTPS 协议，禁止爬取 `file://`、`localhost` 及内网 IP 段，防止 SSRF 攻击与越权爬取。

**验收标准**：提交包含 `file://` 或内网 IP 的 URL 时，系统在任务注册阶段即返回参数校验失败，不产生任何网络请求。

---

### 5.8 容错与稳定性底线（MVP）

MVP 阶段须确保系统在遇到外部依赖故障或异常数据时**优雅降级**，而非级联崩溃。

#### 5.8.1 单点故障隔离

**约束**：单个任务（单条 URL 爬取、单篇文章 AI 分析）的失败，不得影响同批次其他任务的执行，不得导致整个进程或容器退出。失败任务须记录原因并进入失败终态，成功任务须正常入库。

**验收标准**：在包含 100 个 URL 的任务中，混入 20% 的已知异常 URL（403/超时/空内容），系统须完成剩余 80% 的正常处理，且进程不重启、内存不溢出。

#### 5.8.2 外部依赖超时降级

**约束**：系统对外部不可控依赖（目标网站、大模型 API）的调用必须设置上限超时时间。超时后，该次调用标记为失败并释放资源，不得无限挂起或阻塞后续队列。

**验收标准**：模拟外部依赖 30 秒无响应，系统在双倍超时时间内必须完成失败判定，且同队列中后续任务在 10 秒内被调度执行。

#### 5.8.3 数据断连自动恢复

**约束**：系统在数据库连接中断后，应在可感知时间内检测到异常，并拒绝新任务（返回服务不可用）。数据库恢复后，系统须无需人工干预即可自动恢复读写能力。已持久化至数据库的任务队列在重启后不得丢失。

**验收标准**：手动重启 PostgreSQL 容器 30 秒，期间新任务收到明确错误响应；数据库恢复后，系统在 60 秒内自动恢复任务调度能力。

#### 5.8.4 内存泄漏基线

**约束**：系统在标准 MVP 负载（单任务 100 URL + 20 篇 AI 分析）下连续运行 30 分钟，内存占用须稳定在物理内存的阈值上限以下，不得出现持续增长趋势。

**验收标准**：30 分钟监控周期内，进程内存曲线峰值与终值的差值不超过初始值的 20%。

---

## 6. 附录

### 6.1 术语表

| 术语 | 说明 |
| :--- | :--- |
| **MVP** | Minimum Viable Product，最小可行产品 |
| **SSRF** | Server-Side Request Forgery，服务端请求伪造 |
| **GIN 索引** | PostgreSQL 的通用倒排索引，适用于 JSONB 字段检索 |
| **Headless** | 无头浏览器，即没有图形界面的浏览器进程 |
| **DTO** | Data Transfer Object，数据传输对象 |
| **SpiderAdapter** | 爬虫适配器抽象基类，定义 `match / render / extract / validate` 四阶段契约（详见 2.1.10） |
| **DynamicRenderer** | 基于 Playwright 的动态渲染编排层，提供智能等待、自动滚动、网络空闲检测、元素交互（详见 2.1.9） |
| **AIBrowserAgent** | AI 浏览器代理兜底，调用大模型驱动浏览器完成爬取，作为 SpiderAdapter 链最末端兜底（v1.1+ 预留，详见 2.1.8） |
| **LLMExtractionAdapter** | 调用大模型从主体 HTML 抽取结构化字段的适配器（详见 2.1.10） |
| **SiteCrawler** | 站内爬虫，基于 sitemap / RSS / BFS 发现候选文章 URL（详见 2.1.7） |
| **SubdomainDiscover** | 子域名发现，基于证书透明度日志与链接图聚合发现候选子域名，自动入白可撤（详见 2.1.7） |
| **动态白名单** | `allowed_domains` 表，运行时以数据库为准；环境变量 `ALLOWED_DOMAINS` 仅作初始 seed |
| **CT 日志（crt.sh）** | 证书透明度日志查询服务，用于发现签发过证书的子域名 |

---

## 文档版本签注

| 项目 | 内容 |
| :--- | :--- |
| **版本** | v1.0（定稿） |
| **编写日期** | 2026-04-24 |
| **定稿日期** | 2026-04-26 |
| **状态** | ✅ 阶段一（PRD）完成，可进入阶段二（实现规划） |

**v1.0 主要修订**（相对初稿）：
- 取消 `.gov.cn` 硬编码白名单 → 动态白名单（数据库管理 + 环境变量 seed + exact/suffix/regex 三类匹配 + 启用/禁用 + 软删除）
- 新增 SiteCrawler / SubdomainDiscover 站点发现模块（2.1.7）
- 新增 DynamicRenderer 动态渲染编排层（2.1.9）
- 新增 SpiderAdapter 多策略体系：XPath / Readability / LLMExtractionAdapter / AIBrowserAgent 降级链（2.1.10）
- 新增 AI 浏览器代理兜底接口契约（2.1.8，v1.1+ 实现）
- 新增 ADR-04 适配器与降级链决策
- 新增 5 张数据表：`discover_tasks` / `allowed_domains` / `discovered_urls` / `subdomain_candidates` / `spider_adapter_configs`
- 错误码扩展至 13 项 + HTTP Status 完整映射（3.5）
- 新增 5.4 配置缓存同步（30s TTL + cache/refresh 强制刷新）
- 强化 2.2.7 Crawler→AI Engine 时序约束为实现层强制规则（commit 后再 HTTP、禁用 session context 内调用、`after_commit` 钩子、回滚场景测试覆盖）
- 新增 2.2.7 APScheduler 关键配置（misfire_grace_time=300s、coalesce 区分对象、max_instances 分级、job_id 幂等约定）
- 强化 2.1.9 DynamicRenderer 实例池规范（作用域分级 / 软硬双阈值重启 / 实例生命周期），同步 5.5 Chromium 监控阈值
- 性能 / 安全 / 可观测性指标全面升级

**冻结约定**：本 PRD 进入"阶段二实现规划"后即视为冻结基线，后续重大决策以 ADR-05+ 增量记录，不直接修改本文档；如确需修改，需配套 v1.1 版本号与变更说明。

**下一步**：进入阶段二，基于本文档编写实现规划文档（含开发任务清单、ADR-05+、MVP 切片）。
