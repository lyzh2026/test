# 拾讯 (shixun) — 资讯采集与分发闭环系统

「数据抓取 → AI 深度加工 → 多渠道精准分发」自动化闭环系统。提交 URL 或设定定时任务后，系统自动完成采集、去噪、AI 分类摘要、结构化入库，并支持导出 Word、推送微信公众号、邮件订阅。

完整需求见 [`docs/prd-core-architecture.md`](docs/prd-core-architecture.md) 与 [`docs/prd-full-requirements.md`](docs/prd-full-requirements.md)。

## 技术栈

- 后端：FastAPI 0.110 / SQLAlchemy 2.0（async）+ asyncpg / Alembic / APScheduler / Playwright / readability-lxml
- 前端：Next.js 14（App Router）+ React 18 + Tailwind CSS + TypeScript
- 数据库：PostgreSQL 15
- 缓存与队列：Redis 7
- AI 模型：Kimi（Moonshot），通过 OpenAI 兼容协议
- 内容处理：jieba + BM25/Pruning 双管道过滤、markdownify、langdetect
- 文档导出：python-docx + docxtpl
- 部署：Docker Compose 一键启动

## 快速开始

### 1. 准备环境变量

```bash
copy .env.example .env       # Windows
# 或
cp .env.example .env         # Linux / macOS
```

打开 `.env`，至少填入：

- `MOONSHOT_API_KEY`：Kimi API Key（从 https://platform.moonshot.cn/console/api-keys 申请）
- `ADMIN_PASSWORD`：管理员登录密码
- `SESSION_SECRET`：随机长字符串（用于 Cookie 签名）
- `POSTGRES_PASSWORD`：数据库密码

其余可选项（代理池、内容过滤、页面缓存、渲染参数）见 `.env.example` 内注释，留空即用默认值。

> ⚠️ **`.env` 的生效范围有坑**：Docker 部署下，根目录 `.env` 只被 `docker-compose.yml` 用于 `${VAR}` 插值，只有 compose 文件中 `environment:` 显式列出的变量才真正传进容器 —— 即 `POSTGRES_PASSWORD`、`ADMIN_PASSWORD`、`SESSION_SECRET`、`MOONSHOT_API_KEY` / `MOONSHOT_BASE_URL` / `MOONSHOT_MODEL`、`ALLOWED_DOMAINS`、`REDIS_HOST` / `REDIS_PORT`，以及前端用的 `NEXT_PUBLIC_API_URL`。像 `RENDER_POOL_SIZE`、`CONTENT_FILTER_*`、`PROXY_*` 这类**只写在 `.env` 里不会生效** —— 容器内没有 `/app/.env`。要调这些参数，需把它们加进 `docker-compose.yml` 的 `fastapi.environment`，或改 `backend/app/core/config.py` 的默认值后重建镜像。

### 2. 启动服务

```bash
docker compose up -d
docker compose ps
```

四个服务（`redis` / `postgres` / `fastapi` / `nextjs`）都应处于 `healthy` 或 `Up` 状态。首次启动 fastapi 镜像时会下载 Playwright 的 Chromium，约 300MB，需要几分钟。

### 3. 访问

- 本机：http://localhost:3000
- API 文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/health

默认管理员账号：`admin` / 你在 `.env` 中设定的 `ADMIN_PASSWORD`

### 4. 局域网内其他设备访问

#### 4.1 找本机 LAN IP

```bash
# Windows
ipconfig
# 找形如 192.168.1.x / 192.168.0.x / 10.0.0.x 的 IPv4 地址
```

#### 4.2 放行防火墙（Windows）

以管理员身份打开 PowerShell 运行：

```powershell
netsh advfirewall firewall add rule name="Shixun-3000" dir=in action=allow protocol=TCP localport=3000
netsh advfirewall firewall add rule name="Shixun-8000" dir=in action=allow protocol=TCP localport=8000
```

#### 4.3 用 LAN IP 访问

同局域网手机/电脑浏览器打开 `http://192.168.1.x:3000`（替换为实际 IP）。

> 备注：如果走 LAN，浏览器用 LAN IP 即可，不需要 `shixun.com` 域名解析；公网部署需自行处理反向代理与 HTTPS。

## 功能概览

### 采集与渲染（三层降级 + 持久化兜底队列）

单篇抓取逐层降级，任一层成功即返回，避免 JS 空壳或反爬站点拖垮整个任务：

1. **页面缓存**：开启时先查缓存，命中直接进入抽取，跳过渲染。
2. **白名单直连旁路**：若该站点的路由策略为「强制 AI 浏览器」，跳过下面两层直接进兜底队列。
3. **层 1 · 静态快速请求**：httpx `fast_fetch` 拉取原始 HTML（按域名指纹决定是否需要 Playwright；层 1 失败会自动回落到层 2）。
4. **层 2 · 动态渲染**：Playwright `DynamicRenderer`，启用 stealth、代理轮换、上下文隔离；实例池并发 8，每 30 次回收，空闲 5 分钟回收。针对 Cloudflare / 限流 / 通用拦截分别采取不同退避与回收策略。
5. **层 3 · AI 浏览器兜底**：前两层均失败（或命中直连策略）时，URL 写入 `fallback_queue` 表，再由该队列串行消费、调用 AI 浏览器取回正文。队列持久化带来三个能力：任务进度实时展示（`fallback_running` 状态）、取消、**服务重启后自动恢复中断的队列**。

抽取环节统一交给 Readability，产出 Markdown；正文经 BM25 / Pruning 双管道过滤（取长策略，避免 BM25 对长文截断过狠）。

> 第 3 层当前**按设计降级**：接口完整保留在 `app/modules/crawler/ai_browser.py`，但未安装 `browser-use` 依赖（其 0.13.x 用 `==` 精确锁死约 40 个包，与现有 pin 冲突）。未安装时该层自动返回失败原因，前两层链路不受影响；任务最终显示为失败并给出阶段与原因。

### 站点发现与定时采集

- **站点发现**：给一个栏目页入口 URL，自动识别列表并做深层发现 —— 支持翻页、sitemap 解析、多级深度与日期过滤。`POST /api/v1/discovery/scan` 只返回候选链接；`POST /api/v1/discovery/task` 扫描后直接生成爬取任务。
- **定时采集**：维护采集计划（周期、日期范围、目标白名单域名），支持启停与手动触发；服务重启后计划自动恢复。

### AI 加工与分类

- 正文入库后由 Kimi 生成摘要、关键词与分类标签。
- **11 维分类标签**：最新政策、数字经济、人工智能、数据要素、通信、申报、潜在商机、具身智能、车路云协同、新型工业化、算力。标签可在「系统设置」中自定义。
- 支持单篇重新分析、批量导出。

### 记忆层

把运行过程中产生的「经验」沉淀为可查询的数据，用于运营复盘、版本追溯与路由决策：

- **人工修改记录**（`edit_records`）：记录对文章分类标签、推文草稿的每次编辑，保存字段名 + 改前值 + 改后值 + 操作者，可追溯「谁在何时把标签从 A 改成了 B」。
- **推文草稿版本**（`tweet_drafts`）：AI 首次生成写 v1，之后每次保存写新版本、不覆盖，草稿历史完整可回溯。
- **站点渲染统计**（`site_render_stats`）：按（域名, 日期）按天累加，分别统计三层链路各自的成功/失败次数 —— `ff_*` 静态快速请求、`pw_*` Playwright、`ab_*` AI 浏览器。
- **运营周报**：每周一 08:30 自动按 ISO 周生成并分发（幂等，重复触发不会重发），每次生成结果写入分发日志。
- 后台入口：`/admin/memory`，可查询修改记录与站点统计。

### 路由自进化

- **路由策略**（`render_route_policy`）：为指定域名配置渲染模式（自动 / 强制 AI 浏览器 / 强制静态），可手工维护，也接受自动写入。
- **自动晋升**：每日 03:17 跑 `promote_render_policies` —— 扫描近 7 天站点统计，若某域名的 **AI 浏览器兜底成功率 ≥ 60% 且样本 ≥ 5 次**，自动把它晋升为「强制 AI 浏览器」直连（`source=auto`，附成功率说明），跳过前两层直接走兜底，省掉注定失败的渲染开销。
- **只增不减**：已存在的条目（含手工配置）一律跳过，不做自动降级。

这条闭环即「**渲染结果 → 站点统计 → 阈值判定 → 白名单回流**」：链路每一层的成败都写进 `site_render_stats`，晋升任务只读统计、只写策略，二者不互相调用。

### 分发与导出

- **Word 导出**：单篇导出、多篇合并导出（含标题、发布单位、摘要、原文链接）；支持上传 `.docx` 模板（`static/templates/export_template.docx`，≤10MB）自定义版式，模板内使用 `{{ doc_title }}` / `{{ articles }}` 等占位符。
- **微信公众号**：正文一键排版为微信样式，生成草稿，支持导出 Markdown / HTML。
- **邮件订阅**：配置 SMTP 与收件人后，命中主题词的文章自动邮件通知。

### 系统能力

- 白名单域名管理（后缀匹配、启停、来源标记），初始种子来自 `ALLOWED_DOMAINS`。
- URL 三层校验：格式 → 白名单 → DNS 解析后二次校验（SSRF 防护，拦截内网/保留网段）。
- 任务 WebSocket 实时进度（`/api/v1/crawler/ws/task/{task_id}`）+ 轮询降级。
- 统一响应结构与错误码、`x-request-id` 全链路追踪。
- 渲染进程内存监控（psutil）：超软阈值（1.0GB）预警、超硬阈值（1.5GB）强制回收浏览器。

## 核心闭环演示

1. 登录后台
2. 「任务 → 新建」：粘贴 3-5 个白名单内的政务/媒体 URL（如 `gov.cn` 子域）
3. 30 秒~2 分钟后查看「任务列表」状态变为 `completed`（若走了兜底会先出现 `fallback_running`）
4. 进「文章列表」查看 AI 分类标签与摘要
5. 点击单篇文章查看详情，可导出 Word 或排版为微信草稿

## 常用命令

```bash
# 查看日志
docker compose logs -f fastapi
docker compose logs -f nextjs

# 重启某服务
docker compose restart fastapi

# 停止全部
docker compose down

# 完全清空（含数据库数据）
docker compose down -v

# 跑测试
docker compose exec fastapi python -m pytest -q

# 数据库迁移
docker compose exec fastapi alembic upgrade head
docker compose exec fastapi alembic current
```

## 数据库迁移

迁移脚本位于 `backend/alembic/versions/`，当前版本链：

```
0001 → … → 0006_add_scheduled_crawl → 0007_drop_crawler_priority
     → 0008_memory_layer → 0009_fallback_routing
```

- `0008` 引入记忆层表（`edit_records`、`tweet_drafts`、`site_render_stats`）。
- `0009` 引入路由与兜底表（`render_route_policy`、`fallback_queue`），并为 `crawler_tasks` 增加兜底计数字段。

**注意**：容器启动时 fastapi 会自动 `alembic upgrade head`。若 `versions/` 下有新增迁移文件，必须重建镜像后再启动，否则容器会因迁移 head 与 current 不一致而启动失败：

```bash
docker compose up -d --build fastapi
```

## 项目结构

```
shixun/
├── backend/                      # FastAPI 后端
│   ├── app/
│   │   ├── core/                 # 配置、数据库、调度器、安全
│   │   ├── models/               # SQLAlchemy 模型
│   │   └── modules/
│   │       ├── auth/             # 登录鉴权
│   │       ├── admin/            # 白名单、系统设置、记忆层查询、路由策略
│   │       ├── crawler/          # 采集、三层渲染链、兜底队列、定时采集、反检测
│   │       ├── discovery/        # 站点发现（frontier / scoring / link_extractor）
│   │       ├── ai/               # Kimi 分析与超时扫描
│   │       ├── articles/         # 文章、看板统计、Word 导出
│   │       ├── distribution/     # 微信公众号与邮件分发
│   │       ├── wechat_format/    # 微信排版与草稿
│   │       └── memory/           # 记忆层服务
│   ├── alembic/                  # 数据库迁移
│   ├── tests/                    # pytest 测试
│   └── Dockerfile
├── frontend/                     # Next.js 前端
│   ├── app/                      # App Router 页面（登录/任务/文章/看板/admin 系列）
│   ├── components/               # UI 组件
│   └── Dockerfile
├── static/                       # 静态文件卷挂载点（导出模板、渲染失败快照）
├── docs/                         # PRD 与设计文档
├── ppt/                          # 演示材料
├── skills/                       # 项目内 SOP
├── docker-compose.yml
├── .env.example
└── README.md
```

### 主要页面

| 路径 | 说明 |
|---|---|
| `/login` | 登录 |
| `/tasks`、`/tasks/new`、`/tasks/[id]` | 任务列表、新建（一次性/定时）、任务详情与实时进度 |
| `/articles`、`/articles/[id]` | 文章列表、详情 |
| `/articles/[id]/wechat` | 微信排版与草稿 |
| `/dashboard` | 数据看板 |
| `/admin/allowlist` | 白名单管理 |
| `/admin/scheduled-crawls` | 定时采集计划 |
| `/admin/memory` | 记忆层（修改记录、站点统计） |
| `/admin/settings` | 系统设置（AI 模型、导出模板、分类标签、渲染兜底） |
| `/admin/distribution`、`/admin/distribution/logs` | 分发配置与日志 |

## 测试

```bash
docker compose exec fastapi python -m pytest -q
```

当前 366 个用例全部通过，覆盖适配器抽取质量、内容过滤、URL/SSRF 校验、兜底队列与路由策略、记忆层统计、分发适配器等。

## 常见问题

### Q1：Playwright 启动报 Chromium 缺失？
镜像基于 `mcr.microsoft.com/playwright/python` 已自带 Chromium，不需要再 `playwright install`。

### Q2：AI 分析始终失败？
检查 `.env` 中 `MOONSHOT_API_KEY` 是否有效，余额是否充足；`docker compose logs fastapi | grep -i kimi` 查看具体错误。

### Q3：白名单外的 URL 被拒绝？
登录后台后，在「白名单管理」页面查看当前列表，或调用 `GET /api/v1/admin/allowlist`；初始种子在 `.env` 的 `ALLOWED_DOMAINS` 字段。

### Q4：内存占用过高？
默认 Chromium 实例池上限 8 个（`RENDER_POOL_SIZE = 8`），每个浏览器软阈值 1.0GB、硬阈值 1.5GB，空闲 5 分钟回收。机器较小可调小这几个值：`RENDER_POOL_SIZE`、`RENDER_SOFT_MEM_MB`、`RENDER_HARD_MEM_MB`、`RENDER_IDLE_RECYCLE_SEC`。

注意这些参数**不能只写 `.env`**（见「快速开始」的生效范围说明）——要加进 `docker-compose.yml` 的 `fastapi.environment` 后 `docker compose up -d`，或改 `backend/app/core/config.py` 默认值后重建镜像。

### Q5：任务卡在「兜底中」怎么办？
说明进入了第三层（AI 浏览器）的兜底队列。若该能力未启用（按设计降级），任务最终会计为失败；详情页会给出失败原因与阶段。也可在任务详情页手动取消或重试。

### Q6：修改了后端代码但不生效？
容器内代码是构建时烘焙进去的，`./static` 是唯一挂载卷。改完必须重建：

```bash
docker compose up -d --build fastapi
```
