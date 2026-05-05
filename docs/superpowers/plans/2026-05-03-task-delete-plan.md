# 任务删除功能实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在任务详情页增加删除按钮，任务列表页增加批量删除功能。

**Architecture:** 后端新增 2 个 API（单删 + 批量删），删除前自动取消正在运行的任务。前端新增 DeleteButton 组件和 TaskTable 客户端组件。

**Tech Stack:** FastAPI, Next.js 14 (App Router), SQLAlchemy

---

### Task 1: 后端 — `delete_task()` / `batch_delete_tasks()`

**Files:**
- Modify: `backend/app/modules/crawler/service.py` — 末尾追加两个异步函数

- [ ] **Step 1: 在 service.py 末尾追加 delete_task**

```python
async def delete_task(task_id: str) -> bool:
    """取消（如需要）并删除任务记录。返回是否实际删除了记录。"""
    await cancel_task(task_id)
    async with AsyncSessionLocal() as session:
        t = await session.get(CrawlerTask, task_id)
        if not t:
            return False
        await session.delete(t)
        await session.commit()
    logger.info("task deleted: %s", task_id)
    return True


async def batch_delete_tasks(task_ids: list[str]) -> dict:
    """批量取消+删除。不存在的 ID 静默跳过。"""
    deleted = 0
    for tid in task_ids:
        try:
            ok = await delete_task(tid)
            if ok:
                deleted += 1
        except Exception as e:
            logger.warning("batch delete: skip %s (%r)", tid, e)
    return {"deleted": deleted, "skipped": len(task_ids) - deleted}
```

- [ ] **Step 2: 在 routes.py 追加两个路由**

```python
@router.delete("/task/{task_id}")
async def delete_task_route(
    task_id: str,
    request: Request,
    _: object = Depends(current_admin),
):
    """删除单条任务（先取消，再删记录）。"""
    ok = await service.delete_task(task_id)
    if not ok:
        return error(2003, "任务不存在", http_status=404, request=request)
    return success({"ok": True}, request=request)


@router.post("/tasks/batch-delete")
async def batch_delete_tasks_route(
    payload: dict,
    request: Request,
    _: object = Depends(current_admin),
    session: AsyncSession = Depends(get_session),
):
    """批量删除任务。"""
    task_ids = (payload or {}).get("task_ids", [])
    if not task_ids or not isinstance(task_ids, list):
        return error(1001, "task_ids 必须是非空数组", http_status=400, request=request)
    result = await service.batch_delete_tasks(task_ids)
    return success(result, request=request)
```

需要在 routes.py 顶部将 `from app.modules.crawler import service` 保留（已导入），`AsyncSession` 和 `get_session` 已在顶部 import。

- [ ] **Step 3: 验证导入完整性**

确保 `routes.py` 顶部已有 `from sqlalchemy.ext.asyncio import AsyncSession` 和 `from app.core.database import get_session`。

---

### Task 2: 前端 — DeleteButton 组件

**Files:**
- Create: `frontend/components/tasks/DeleteButton.tsx`

- [ ] **Step 1: 创建 DeleteButton.tsx**

```tsx
'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';

export function DeleteButton({ taskId }: { taskId: string }) {
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  async function handleDelete() {
    if (!confirm('确认删除此任务？（已入库文章不受影响）')) return;
    setLoading(true);
    try {
      await api.post(`/api/v1/crawler/task/${taskId}/cancel`);
      await api.delete(`/api/v1/crawler/task/${taskId}`);
      router.push('/tasks');
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : '删除失败');
    } finally {
      setLoading(false);
    }
  }

  return (
    <button
      onClick={handleDelete}
      disabled={loading}
      className="rounded-md px-3 py-1.5 text-xs font-medium transition-all duration-150 disabled:opacity-50"
      style={{ background: 'rgba(248, 81, 73, 0.1)', color: '#f85149' }}
    >
      {loading ? '删除中…' : '删除'}
    </button>
  );
}
```

- [ ] **Step 2: 在详情页引入 DeleteButton**

修改 `frontend/app/tasks/[id]/page.tsx`：

导入 DeleteButton：
```tsx
import { DeleteButton } from '@/components/tasks/DeleteButton';
```

删除按钮始终显示，在 RetryButton 后面加：
```tsx
<DeleteButton taskId={task.id} />
```

So line 84 becomes:
```tsx
<CancelButton taskId={task.id} status={task.status} />
<RetryButton taskId={task.id} status={task.status} />
<DeleteButton taskId={task.id} />
```

---

### Task 3: 前端 — TaskTable 客户端组件

**Files:**
- Create: `frontend/components/tasks/TaskTable.tsx`
- Modify: `frontend/app/tasks/page.tsx`

- [ ] **Step 1: 新建 TaskTable.tsx**

将原 `tasks/page.tsx` 的表格部分抽为 `'use client'` 组件：

```tsx
'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { formatDate } from '@/lib/utils';

type Task = {
  id: string;
  task_name: string | null;
  target_date: string;
  date_to: string | null;
  total_urls: number;
  completed_urls: number;
  failed_urls: number;
  status: string;
  created_at: string;
};

const STATUS_BADGE: Record<string, string> = {
  pending: 'badge-gray',
  running: 'badge-amber',
  completed: 'badge-green',
  partial_failed: 'badge-amber',
  failed: 'badge-red',
  cancelled: 'badge-gray',
};

const STATUS_LABEL: Record<string, string> = {
  pending: '等待中',
  running: '运行中',
  completed: '已完成',
  partial_failed: '部分失败',
  failed: '失败',
  cancelled: '已取消',
};

export function TaskTable({ items }: { items: Task[] }) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [deleting, setDeleting] = useState(false);
  const router = useRouter();

  const allSelected = items.length > 0 && selected.size === items.length;

  function toggleAll() {
    if (allSelected) {
      setSelected(new Set());
    } else {
      setSelected(new Set(items.map((t) => t.id)));
    }
  }

  function toggleOne(id: string) {
    const next = new Set(selected);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    setSelected(next);
  }

  async function handleBatchDelete() {
    const count = selected.size;
    if (!confirm(`确认删除选中的 ${count} 个任务？（已入库文章不受影响）`)) return;
    setDeleting(true);
    try {
      await api.post('/api/v1/crawler/tasks/batch-delete', { task_ids: Array.from(selected) });
      setSelected(new Set());
      router.refresh();
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : '批量删除失败');
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="card overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr style={{ borderBottom: '1px solid #1f1f23' }}>
            <th className="w-10 px-2 py-3 text-left">
              <input
                type="checkbox"
                checked={allSelected}
                onChange={toggleAll}
                className="cursor-pointer"
              />
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-text-muted">名称</th>
            <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-text-muted">目标日期</th>
            <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-text-muted">进度</th>
            <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-text-muted">状态</th>
            <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-text-muted">创建时间</th>
          </tr>
        </thead>
        <tbody>
          {items.length === 0 && (
            <tr>
              <td colSpan={6} className="px-4 py-12 text-center text-sm text-text-muted">
                暂无任务
              </td>
            </tr>
          )}
          {items.map((t) => (
            <tr key={t.id} className="transition-colors duration-150 hover:bg-surface-50" style={{ borderBottom: '1px solid #1f1f23' }}>
              <td className="px-2 py-3 text-center">
                <input
                  type="checkbox"
                  checked={selected.has(t.id)}
                  onChange={() => toggleOne(t.id)}
                  className="cursor-pointer"
                />
              </td>
              <td className="px-4 py-3">
                <Link href={`/tasks/${t.id}`} className="text-text-primary hover:text-brand-500 transition-colors">
                  {t.task_name || t.id.slice(0, 8)}
                </Link>
              </td>
              <td className="px-4 py-3 text-text-secondary">
                {t.date_to ? `${t.target_date}~${t.date_to}` : t.target_date}
              </td>
              <td className="px-4 py-3 text-text-secondary">
                {t.completed_urls} / {t.total_urls}
                {t.failed_urls > 0 && (
                  <span className="ml-2" style={{ color: '#f85149' }}>失败 {t.failed_urls}</span>
                )}
              </td>
              <td className="px-4 py-3">
                <span className={STATUS_BADGE[t.status] || 'badge-gray'}>
                  {STATUS_LABEL[t.status] || t.status}
                </span>
              </td>
              <td className="px-4 py-3 text-text-muted text-xs">{formatDate(t.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {selected.size > 0 && (
        <div className="sticky bottom-0 flex items-center justify-between border-t px-4 py-3" style={{ borderColor: '#1f1f23', background: '#161618' }}>
          <span className="text-xs text-text-muted">已选中 {selected.size} 项</span>
          <button
            onClick={handleBatchDelete}
            disabled={deleting}
            className="rounded-md px-3 py-1.5 text-xs font-medium transition-all duration-150 disabled:opacity-50"
            style={{ background: 'rgba(248, 81, 73, 0.1)', color: '#f85149' }}
          >
            {deleting ? '删除中…' : `删除选中 (${selected.size})`}
          </button>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: 修改 `frontend/app/tasks/page.tsx`**

顶部加导入：
```tsx
import { TaskTable } from '@/components/tasks/TaskTable';
```

替换从 `<div className="card overflow-hidden">` 到末尾 `</div>` 的整个表格部分为：
```tsx
<TaskTable items={items} />
```

最终 `page.tsx` 保持服务端组件，只负责 fetch 数据，渲染交给 TaskTable。

---

### Task 4: 验证

- [ ] **Step 1: 检查后端 import**

确认 `routes.py` 顶部已有 `from sqlalchemy.ext.asyncio import AsyncSession` 和 `from app.core.database import get_session`（或 `Depends(get_session)` 已在参数中使用）。

- [ ] **Step 2: 检查前端编译**

```bash
cd frontend && npm run build 2>&1 | head -30
```

无 TypeScript 或 lint 错误。

- [ ] **Step 3: 检查修改范围**

确认只涉及 spec 中列出的 6 个文件，无意外改动。
