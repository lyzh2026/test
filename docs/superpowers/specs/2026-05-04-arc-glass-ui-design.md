# 拾讯 · Adaline 风格 UI 设计

**日期**: 2026-05-04
**状态**: 已实施

## 设计参考

参考 Adaline（Daybreak Studio 设计，Awwwards SOTD）的生物亲和风格：
- "A landscape for thought" — 清晰与平静
- Biophilic 色板：柔和绿 + 中性暖白
- 深度通过光影传递（下层深色，上层浅色），模仿自然环境

---

## 1. 色彩系统

| Token | Value | 用途 |
|-------|-------|------|
| `--bg-primary` | `#fbfdf6` | 页面主背景（极淡绿白） |
| `--bg-muted` | `#eff2e8` | 次要背景、代码块、摘要区 |
| `--bg-cream` | `#fcf9f2` | 暖色强调背景 |
| `--bg-dark` | `#203b14` | 深色按钮、深色背景元素 |
| `--brand` | `#b1cc7a` | 品牌主色（鼠尾草绿） |
| `--brand-dark` | `#8fb35a` | 品牌深色（hover） |
| `--brand-light` | `#d7e8b5` | 品牌浅色 |
| `--text-primary` | `#0a1d08` | 主文本（近乎黑的深绿） |
| `--text-secondary` | `#203b14` | 辅助文本 |
| `--text-muted` | `#8a9a7a` | 弱化文本 |
| `--border-light` | `#e0e5d5` | 卡片、输入框边框 |
| `--border` | `#c5ccb6` | 强化边框、分隔线 |

### 语义色

| Token | Hex | 用途 |
|-------|-----|------|
| `--danger` | `#d4584a` | 错误/删除 |
| `--success` | `#5a9e6f` | 成功/完成 |
| `--warning` | `#c5a45a` | 警告/进行中 |
| `--info` | `#7a9ec4` | 信息/提示 |

---

## 2. 布局

### 侧边栏（窄版图标栏）
- 宽度: 60px
- 背景: `#fbfdf6` + 右侧 `1px solid #e0e5d5` 边框
- Logo: `#b1cc7a` 实色背景 + `#203b14` 文字
- 图标: 26x26 居中，hover 时背景变 `rgba(177, 204, 122, 0.12)`
- 激活态: `#b1cc7a` 左侧 2px 指示条 + `rgba(177, 204, 122, 0.12)` 背景
- Tooltip: `#203b14` 深色背景 + 圆角 20px

### 内容区
- 左侧距: 60px（侧边栏宽度）
- 内边距: 32px（页面）
- 最大内容宽度: 1200px

### 圆角体系
| 层级 | 值 | 用途 |
|------|-----|------|
| 微 | 6px | 内联元素、小控件 |
| 标准 | 12px | 输入框、卡片内元素 |
| 卡片 | 16px | 标准卡片、面板、模态框 |
| 全圆 | 20px | 按钮（药丸形） |
| 超大 | 9999px | 徽标、状态点 |

---

## 3. 组件设计

### 按钮

**Primary**
```css
background: #203b14;
color: #fbfdf6;
border-radius: 20px;
padding: 8px 20px;
font-size: 14px;
font-weight: 500;
```
Hover: `opacity: 0.9`

**Secondary**
```css
background: #fbfdf6;
border: 1px solid #e0e5d5;
color: #203b14;
border-radius: 20px;
```
Hover: `border-color: #c5ccb6; background: #eff2e8`

### 卡片
```css
background: #fbfdf6;
border: 1px solid #e0e5d5;
border-radius: 16px;
```
Hover: `border-color: #c5ccb6; background: #eff2e8`

### 输入框
```css
background: #fbfdf6;
border: 1px solid #e0e5d5;
border-radius: 12px;
color: #0a1d08;
```
Focus: `border-color: #b1cc7a; box-shadow: 0 0 0 2px rgba(177, 204, 122, 0.15)`

### 登录页
- 居中布局，`#fbfdf6` 背景
- Logo: 12x12 `#b1cc7a` 实色方块 + "SX"
- 表单卡片: 16px 圆角，`#fbfdf6` + `1px solid #e0e5d5`

### 统计卡片（Dashboard）
- 4 列网格，每列卡片
- 数值 24px semibold
- 颜色按语义区分（绿/红/蓝）

### 表格（任务列表、分发配置等）
- 行背景透明，hover 时 `bg-surface-50`
- 表头用 `#e0e5d5` 底线分隔
- 文字用 `#8a9a7a` muted 色

### 筛选栏（文章列表）
- 卡片风格面板
- 筛选控件用标准输入框

---

## 4. 徽标色

| Class | 背景 | 文字 | 用途 |
|-------|------|------|------|
| `.badge-green` | `rgba(90, 158, 111, 0.1)` | `#5a9e6f` | 成功/已处理 |
| `.badge-red` | `rgba(212, 88, 74, 0.1)` | `#d4584a` | 失败/错误 |
| `.badge-amber` | `rgba(197, 164, 90, 0.1)` | `#c5a45a` | 进行中/警告 |
| `.badge-blue` | `rgba(122, 158, 196, 0.1)` | `#7a9ec4` | 信息/提示 |
| `.badge-gray` | `rgba(138, 154, 122, 0.1)` | `#8a9a7a` | 默认/禁用 |

---

## 5. 滚动条
```css
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-thumb { background: #c5ccb6; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #8a9a7a; }
```

---

## 6. 动画
- 页面进入: `fade-in` 0.3s ease
- 卡片 hover: 边框 + 背景 0.2s ease
- 侧边栏 hover: 0.15s ease
- 过渡: 0.15s ease

---

## 7. 参考站点
- **Adaline** — https://www.adaline.ai
- 字体: Akkurat / Inter / -apple-system
- 风格: 生物亲和、极简、清晰、大量留白
