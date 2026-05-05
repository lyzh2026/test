# Arc 毛玻璃 UI 风格实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将拾讯前端从 Linear 暗色风（`#0a0a0b`/`#5e6ad2`）重构为 Arc 毛玻璃浅色风（`#f5f5f0`/`#f97316`），仅修改 CSS 和展示组件。

**Architecture:** 纯 CSS 变量替换 + 组件 class 重构。核心策略：修改 `globals.css` 中的设计令牌和组件类，Sidebar 重构为 60px 窄栏，其余页面自动继承新样式。不改任何 API/Server Component 逻辑。

**Tech Stack:** Tailwind CSS, Next.js (App Router), CSS 自定义属性

**约束:** 
- 不改任何 API 请求、数据获取、路由逻辑
- 不改 `serverFetch`、`page.tsx` 中的 Server Component 数据逻辑
- 不改后端代码
- 保持所有交互行为一致

---

### Task 1: 全局 CSS — 设计令牌替换

**Files:**
- Modify: `frontend/app/globals.css`

将暗色主题令牌替换为 Arc 毛玻璃风格，保留 tailwind 指令。

**变更内容:**
- `:root` 中的颜色变量全部替换
- 组件类 `.card` / `.btn` / `.input` / `.badge-*` 样式重写
- 滚动条、选中色等细节更新
- 品牌色从 `#5e6ad2` → `#f97316`
- 删除不再需要的 `.badge-purple`（保留其他 badge 颜色但调整色值）

---

### Task 2: 侧边栏 — 窄版图标栏重构

**Files:**
- Modify: `frontend/components/layout/Sidebar.tsx`
- Modify: `frontend/components/layout/PageShell.tsx`

Sidebar 从 240px 宽文字栏 → 60px 图标栏：
- 背景 `rgba(255,255,255,0.4)` + `backdrop-filter: blur(8px)`
- 右侧圆角 12px
- 图标 26x26 居中，hover 时浅橙背景
- 激活态：橙色填充图标 + 左侧 2px 橙色指示条
- hover tooltip 右侧弹出文字标签
- Logo 从 "SX" 方块 → 橙色渐变圆角方块

PageShell 调整 `ml-[240px]` → `ml-[60px]`。

---

### Task 3: 登录页 — 毛玻璃卡片

**Files:**
- Modify: `frontend/app/login/page.tsx`

- 背景从 `#0a0a0b` → `#f5f5f0`
- 登录卡片从深色 → 毛玻璃 `blur(12px)` + 12px 圆角
- 品牌色元素改为橙色
- Logo 方块改为橙色渐变
- 文字颜色适配浅色背景

---

### Task 4: Dashboard — 颜色适配

**Files:**
- Modify: `frontend/app/dashboard/page.tsx`

- 无结构改动，仅 color/bg 属性值从 `#5e6ad2` → `#f97316`
- 统计卡片颜色橙化
- 图表柱状颜色改为品牌橙

---

### Task 5: 文章/任务页面 — 颜色适配

**Files:**
- Modify: `frontend/app/articles/page.tsx`（调整 `<select>` 等内联颜色）
- Modify: `frontend/app/tasks/page.tsx`（无内联颜色需改，仅验证）
- Modify: `frontend/app/tasks/new/page.tsx`（如有内联颜色）
- Modify: `frontend/app/tasks/[id]/page.tsx`（如有内联颜色）
- Modify: `frontend/app/admin/distribution/page.tsx`（如有内联颜色）

搜索所有 `#5e6ad2` 引用替换为 `#f97316`，以及 `#0a0a0b` → `#f5f5f0` 等背景色。

---

### Task 6: 验证 — 样式不影响功能

**验证清单:**
1. `npm run dev` 正常启动
2. 登录页正常渲染
3. 侧边栏导航点击可正确跳转
4. Dashboard 数据正常加载（API 未改动）
5. 文章列表筛选正常提交
6. 所有交互（按钮 hover、链接点击）正常
