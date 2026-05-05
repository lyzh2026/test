# 任务删除功能设计

## 概述

任务详情页增加删除按钮，任务列表页增加批量删除功能。删除操作：先取消正在运行的任务，再删除 `crawler_tasks` 记录，不涉及 `articles` 表。

## 后端

### `DELETE /api/v1/crawler/task/{task_id}`

- 调用 `cancel_task()` 取消任务（如为 running/pending 状态）
- 从数据库删除 `CrawlerTask` 记录
- 返回 `{"ok": true}`
- 任务不存在时返回 404

### `POST /api/v1/crawler/tasks/batch-delete`

请求体：`{ "task_ids": ["uuid1", "uuid2", ...] }`

- 遍历每个 ID：取消 → 删除
- 忽略不存在的 ID（幂等）
- 返回 `{"deleted": count, "skipped": count}`

### service.py 新增函数

```python
async def delete_task(task_id: str) -> bool
async def batch_delete_tasks(task_ids: list[str]) -> dict
```

`delete_task` 复用 `cancel_task` 的取消逻辑（通过 `_cancelled_tasks` 通知运行中的 job），然后删库。

## 前端

### DeleteButton（详情页）

新建 `components/tasks/DeleteButton.tsx`：

- 始终显示（不限状态），红色危险按钮
- 点击弹出 confirm 确认
- 确认后先 POST `/api/v1/crawler/task/{taskId}/cancel`（兼容 running/pending 状态，已结束的也无害）
- 再调用 DELETE `/api/v1/crawler/task/{taskId}`
- 成功后 `router.push('/tasks')` 回到列表页
- 与 CancelButton、RetryButton 并列显示

### TaskTable（列表页）

新建 `components/tasks/TaskTable.tsx`，从 `app/tasks/page.tsx` 抽出 table 部分改为 `'use client'`：

- 表头 th 前加全选 checkbox
- 每行 td 前加 checkbox
- 选中 ≥ 1 行时底部浮出操作栏：显示"删除选中 (N)"按钮
- 批量删除调用 POST `/api/v1/crawler/tasks/batch-delete`
- 完成后 `router.refresh()`
- 删除按钮在加载时 disabled，显示"删除中…"
- 全选逻辑：所有行勾选/取消，已隐藏的行不影响

## 文件清单

| 文件 | 改动 |
|------|------|
| `backend/app/modules/crawler/routes.py` | + 2 路由 |
| `backend/app/modules/crawler/service.py` | + `delete_task()`, `batch_delete_tasks()` |
| `frontend/components/tasks/DeleteButton.tsx` | 新建 |
| `frontend/components/tasks/TaskTable.tsx` | 新建 |
| `frontend/app/tasks/page.tsx` | 用 TaskTable 替换原表格 |
| `frontend/app/tasks/[id]/page.tsx` | 引入 DeleteButton |

## 边界处理

- **正在运行的任务**：先取消再删除，`_cancelled_tasks` 通知运行中的 job 停止处理新 URL
- **已删除后再次请求**：404
- **批量删除混合存在/不存在的 ID**：存在的删，不存在的跳过，返回计数
- **文章不删除**：仅删 task 记录，article 表数据保留
