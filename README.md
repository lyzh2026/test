# 拾讯 (shixun.com) — 核心闭环 MVP

「数据抓取 → AI 深度加工 → 多渠道精准分发」自动化闭环系统。本仓库是核心闭环 MVP（提交 URL → 爬取 → AI 分析 → 文章列表/详情/看板）。

完整需求见 [`docs/prd-core-architecture.md`](docs/prd-core-architecture.md)。

## 技术栈

- 后端：FastAPI 0.110+ / SQLAlchemy 2.0 / Alembic / APScheduler / Playwright / Readability-lxml
- 前端：Next.js 14（App Router）+ Tailwind CSS + shadcn 风格组件
- 数据库：PostgreSQL 15
- AI 模型：Kimi（Moonshot），通过 OpenAI 兼容协议
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

### 2. 启动服务

```bash
docker compose up -d
docker compose ps
```

三个服务（postgres / fastapi / nextjs）都应处于 `healthy` 或 `Up` 状态。首次启动 fastapi 镜像时会下载 Playwright 的 Chromium，约 300MB，需要几分钟。

### 3. 访问

- 本机：http://localhost:3000
- API 文档：http://localhost:8000/docs

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

> 备注：如果走 LAN，浏览器用 LAN IP 即可，不需要 `shixun.com` 域名解析；公网部署本次不在范围内。

## 核心闭环演示

1. 登录后台
2. 「任务 → 新建」：粘贴 3-5 个白名单内的政务/媒体 URL（如 `gov.cn` 子域）
3. 30 秒~2 分钟后查看「任务列表」状态变为 `completed`
4. 进「文章列表」查看 AI 分类标签与摘要
5. 点击单篇文章查看详情（含原文跳转）

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
```

## 项目结构

```
shixun/
├── docs/                     # PRD 文档
├── backend/                  # FastAPI 后端
│   ├── app/                  # 应用代码
│   ├── alembic/              # 数据库迁移
│   └── Dockerfile
├── frontend/                 # Next.js 前端
│   ├── app/                  # App Router 页面
│   └── Dockerfile
├── static/                   # 静态文件卷挂载点
├── docker-compose.yml
├── .env.example
└── README.md
```

## 已实现 / 待实现范围

✅ 本次实现：登录鉴权、URL 三层校验、爬虫降级链（Readability + LLM 抽取）、AI 分类摘要、文章列表/详情/看板、APScheduler 任务调度、内存阈值监控

⏸ 留接口骨架：XPathAdapter、AIBrowserAgent、白名单管理 UI、SpiderAdapter 配置面板

⏸ 不在 MVP：站点发现、微信公众号、邮件订阅、Word 导出（PRD 已说明）

后续迭代方向见 PRD 第 11 节。

## 常见问题

### Q1：Playwright 启动报 Chromium 缺失？
镜像基于 `mcr.microsoft.com/playwright/python` 已自带 Chromium，不需要再 `playwright install`。

### Q2：AI 分析始终失败？
检查 `.env` 中 `MOONSHOT_API_KEY` 是否有效，余额是否充足；`docker compose logs fastapi | grep -i kimi` 查看具体错误。

### Q3：白名单外的 URL 被拒绝？
登录后台后，调用 `GET /api/v1/admin/allowlist` 查看当前白名单；初始种子在 `.env` 的 `ALLOWED_DOMAINS` 字段。

### Q4：内存占用过高？
默认 Chromium 实例池上限 3 个，每个软阈值 1.0GB。若机器较小可在 `backend/app/core/config.py` 把 `RENDER_POOL_SIZE` 改小（重新构建镜像）。
