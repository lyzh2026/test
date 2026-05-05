# 爬虫系统优化设计文档

> 日期：2026-05-02
> 参考项目：Crawl4AI (unclecode/crawl4ai), Crawlee-Python (apify/crawlee-python), Scrapy (scrapy/scrapy)

---

## 1. 总体架构

采用"混合策略"：保留现有渲染引擎和代理池，按管道化重构内部处理链。

```
┌─────────────┐  ┌───────────────┐  ┌────────────────┐  ┌──────────────┐
│ Renderer    │→ │ Content       │→ │ Extractor      │→ │ Post-Process │
│ (现有Playwright│  │ Filter Pipeline│  │ Chain          │  │ (去重+入库)    │
│  + Stealth) │  │ BM25+Pruning  │  │ Readability→LLM│  │ (现有逻辑)     │
└─────────────┘  └───────────────┘  └────────────────┘  └──────────────┘
                          ↑                    ↑
                    ┌───────────┐       ┌───────────┐
                    │Cache Layer│       │Chunking   │
                    │(Redis)    │       │Strategy   │
                    └───────────┘       └───────────┘
```

---

## 2. Renderer 增强

### 2.1 Stealth 反检测

在 `renderer.py` 中添加浏览器初始化脚本（参考 `playwright-stealth` + Crawl4AI）：

```python
STEALTH_INIT_SCRIPTS = [
    "Object.defineProperty(navigator, 'webdriver', { get: () => undefined })",
    "window.chrome = { runtime: {} }",
    "Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] })",
    "Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh'] })",
    """
    window.navigator.permissions.query =
        (() => Promise.resolve({ state: 'granted' }));
    """,
]
```

**植入位置**：`DynamicRenderer._ensure_browser()` 中，在创建 `context` 后为每个新的 page 调用 `context.add_init_script()`。

### 2.2 浏览器上下文隔离

- 每个 URL 爬取时创建独立 `browser.new_context()`，爬完即关闭
- 每个 Context 绑定一个特定 Proxy（从代理池选取），实现 Session-Proxy 绑定
- 参考 Crawlee 的 `retireBrowserAfterPageCount` 机制：每 N 个 URL 后重启浏览器进程（N 可配置，默认 30）
- 新 Context 继承全局 UA、视口等配置，但拥有独立 Cookie/缓存

### 2.3 随机行为模拟

- 页面滚动轮数 5-10 轮随机（现为固定 8 轮）
- 每次滚动间隔 0.5-2s 随机（现为固定间隔）
- 增加随机鼠标悬停操作（可选轻量，在关键元素上悬停）

---

## 3. Content Filter Pipeline（新增模块）

**文件**：`backend/app/modules/crawler/content_filter.py`

### 3.1 Pruning（去噪）

对 `clean_html()` 的增强，额外过滤：

| 类别 | 具体规则 |
|------|---------|
| 低密度节点 | 平均文本长度 < 20 字符的 div/section |
| 重复模板 | sidebar、related-links、comments、广告容器 |
| 关键词黑名单 | class/id 包含: sidebar, ad, comment, related, footer, nav, menu, social, widget |

实现策略：基于 lxml 遍历 DOM 树，对每个节点计算文本密度 = 文本长度/HTML 长度，低于阈值则移除。

### 3.2 BM25 核心提取

算法流程：

1. **文本块分块**：将去噪后 HTML 按语义标签分块（`<p>`, `<h1>-<h6>`, `<li>`, `<td>`, `<article>`, `<section>`）
2. **计算 BM25 分数**：对每个块计算 BM25 相关性分数
   - 词频（TF）：块内词频
   - 文档频率（DF）：利用 `<title>` 和 `<meta keywords>` 中的关键词作为查询
   - 如果页面没有关键词元数据，使用标题分词作为查询
3. **Top-K 保留**：按分数降序保留前 K 个块，同时保留原始 HTML 结构
4. **长内容分块**：超长内容自动分割为多个 chunk

### 3.3 Pipeline 数据流

```
raw_html
  → Pruning（去噪）
    → pruned_html
      → BM25（提取核心）
        → filtered_html（进入缓存层）
          → Extractor Chain
```

---

## 4. 缓存层（新增模块）

**文件**：`backend/app/modules/crawler/cache.py`

### 4.1 页面级缓存

基于 Redis 实现：

```python
# 缓存 key
PAGE_CACHE_PREFIX = "crawl_page_cache:"
cache_key = f"{PAGE_CACHE_PREFIX}{md5(url.encode()).hexdigest()}"

# 缓存结构（Hash）
{
    "url": str,
    "filtered_html": str,    # 经 Content Filter Pipeline 处理后的 HTML
    "pruned_html": str,      # 仅去噪后的 HTML（备用）
    "title": str,
    "cached_at": float,      # timestamp
    "ttl": int               # 过期时间（秒）
}
```

### 4.2 缓存策略

| 场景 | 行为 |
|------|------|
| 命中缓存且未过期 | 跳过渲染，直接用缓存进入提取链 |
| 未命中 | 正常渲染 → 写入缓存（默认 TTL=3600s） |
| 过期 | 视为未命中，重新渲染并刷新缓存 |
| 缓存写入失败 | 打日志，不阻塞主流程 |

### 4.3 配置项

```python
CRAWLER_CACHE_ENABLED: bool = True
CRAWLER_CACHE_DEFAULT_TTL: int = 3600       # 默认 1 小时
CRAWLER_CACHE_MAX_TTL: int = 86400          # 最大 24 小时
```

---

## 5. Extractor Chain 增强

### 5.1 改造点

**ReadabilityAdapter**：
- 输入从 `raw_html` 改为 `filtered_html`
- 其余保持不变（提取标题、正文、日期、来源）

**LLMExtractionAdapter**：
- 输入从裁剪后的 HTML 改为 `filtered_html`
- 增加分块策略：
  - `chunk_token_threshold = 4000`（超过 4000 token 分块）
  - `overlap_rate = 0.1`（块间 10% 重叠，保证信息不丢失）
  - 分块后调用 LLM 提取，结果合并后再返回
- 当已通过 Readability 成功提取时，如果 confidence < 0.7，仍可触发 LLM 提取作为补充

### 5.2 降级链

```
filtered_html
  → ReadabilityAdapter(f filtered_html)
    → 成功且 confidence >= 0.7 → 直接返回
    → 失败或 confidence < 0.7
      → LLMExtractionAdapter(filtered_html, chunking=True)
        → confidence >= 0.5 → 返回
        → 失败 → 返回错误码 2002
```

---

## 6. 去重增强

在现有 Redis MD5 指纹基础上增加：

| 改进 | 实现方式 |
|------|---------|
| URL 规范化去重 | 去除 URL 中 `utm_*`、`fbclid`、`gclid`、`ref`、`from` 等跟踪参数，再计算指纹 |
| 相似标题检测 | 存储文章标题的 SimHash（Redis Set），新文章标题与现有标题的 Hamming 距离 < 3 视为重复 |

---

## 7. 涉及文件清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `backend/app/modules/crawler/renderer.py` | 修改 | 添加 stealth 脚本、上下文隔离、行为模拟 |
| `backend/app/modules/crawler/content_filter.py` | 新增 | BM25 + Pruning 内容过滤管道 |
| `backend/app/modules/crawler/cache.py` | 新增 | Redis 页面级缓存 |
| `backend/app/modules/crawler/adapters/readability_adapter.py` | 修改 | 输入改为 filtered_html |
| `backend/app/modules/crawler/adapters/llm_extraction_adapter.py` | 修改 | 输入改为 filtered_html，增加分块策略 |
| `backend/app/modules/crawler/service.py` | 修改 | 串联 Content Filter + Cache + Extractor |
| `backend/app/core/config.py` | 修改 | 新增缓存/过滤相关配置项 |

---

## 8. 预期效果

| 指标 | 当前 | 优化后（预估） |
|------|------|---------------|
| 爬取成功率 | 基准 | +15-25%（反检测增强） |
| LLM token 消耗 | 基准 | -50-70%（BM25 预过滤） |
| 重复 URL 渲染 | 存在 | -40-60%（缓存层） |
| 内容提取准确率 | 基准 | +10-20%（过滤后 LLM 更专注） |
| 被检测/封禁率 | 基准 | -30-50%（stealth + 隔离） |
