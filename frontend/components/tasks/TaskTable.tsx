'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { formatDate } from '@/lib/utils';
import { useToast } from '@/components/ui/Toast';

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

function ProgressBar({ completed, total, failed }: { completed: number; total: number; failed: number }) {
  if (total === 0) return <span style={{ color: '#9ca3af' }}>-</span>;
  const pct = Math.round((completed / total) * 100);
  const failedPct = Math.round((failed / total) * 100);
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-20 overflow-hidden rounded-full" style={{ background: '#f3f4f6' }}>
        <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, background: '#22c55e' }} />
        {failedPct > 0 && (
          <div className="h-full rounded-full -mt-1.5" style={{ width: `${pct + failedPct}%`, background: '#ef4444', opacity: 0.6 }} />
        )}
      </div>
      <span className="text-xs" style={{ color: '#6b7280' }}>{completed}/{total}</span>
      {failed > 0 && (
        <span className="text-xs" style={{ color: '#ef4444' }}>-{failed}</span>
      )}
    </div>
  );
}

export function TaskTable({ items, onRefresh }: { items: Task[]; onRefresh?: () => void }) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [deleting, setDeleting] = useState(false);
  const router = useRouter();
  const { toast, confirm } = useToast();

  const allSelected = items.length > 0 && selected.size === items.length;

  function toggleSelect(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleSelectAll() {
    if (allSelected) {
      setSelected(new Set());
    } else {
      setSelected(new Set(items.map((t) => t.id)));
    }
  }

  async function handleBatchDelete() {
    if (!await confirm(`确认删除选中的 ${selected.size} 个任务？此操作不可撤销。`)) return;
    setDeleting(true);
    try {
      await api.post('/api/v1/crawler/tasks/batch-delete', { task_ids: Array.from(selected) });
      setSelected(new Set());
      if (onRefresh) onRefresh();
      else router.refresh();
    } catch (e: unknown) {
      toast(e instanceof Error ? e.message : '批量删除失败', 'error');
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="card overflow-hidden">
      {selected.size > 0 && (
        <div
          className="flex items-center justify-end px-4 py-2"
          style={{ borderBottom: '1px solid #e5e7eb', background: 'rgba(228, 90, 90, 0.03)' }}
        >
          <span className="text-xs mr-3" style={{ color: '#6b7280' }}>已选择 {selected.size} 项</span>
          <button
            onClick={handleBatchDelete}
            disabled={deleting}
            className="rounded-[20px] px-3 py-1.5 text-xs font-medium transition-all duration-150 disabled:opacity-50"
            style={{ background: 'rgba(239, 68, 68, 0.1)', color: '#ef4444' }}
          >
            {deleting ? '删除中…' : `删除选中 (${selected.size})`}
          </button>
        </div>
      )}
      <table className="w-full text-sm">
        <thead>
          <tr style={{ borderBottom: '1px solid #e5e7eb' }}>
            <th className="px-4 py-3 text-left">
              <input
                type="checkbox"
                checked={allSelected}
                onChange={toggleSelectAll}
                className="h-4 w-4 cursor-pointer rounded"
                style={{ accentColor: '#3b82f6' }}
              />
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider" style={{ color: '#9ca3af' }}>名称</th>
            <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider" style={{ color: '#9ca3af' }}>目标日期</th>
            <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider" style={{ color: '#9ca3af' }}>进度</th>
            <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider" style={{ color: '#9ca3af' }}>状态</th>
            <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider" style={{ color: '#9ca3af' }}>创建时间</th>
            <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider" style={{ color: '#9ca3af' }}>操作</th>
          </tr>
        </thead>
        <tbody>
          {items.length === 0 && (
            <tr>
              <td colSpan={7} className="px-4 py-12 text-center text-sm" style={{ color: '#9ca3af' }}>
                暂无任务
              </td>
            </tr>
          )}
          {items.map((t) => (
            <tr
              key={t.id}
              className="transition-colors duration-150"
              style={{ borderBottom: '1px solid #e5e7eb' }}
            >
              <td className="px-4 py-3">
                <input
                  type="checkbox"
                  checked={selected.has(t.id)}
                  onChange={() => toggleSelect(t.id)}
                  className="h-4 w-4 cursor-pointer rounded"
                  style={{ accentColor: '#3b82f6' }}
                />
              </td>
              <td className="px-4 py-3">
                <Link href={`/tasks/${t.id}`} className="transition-colors" style={{ color: '#18181b' }}>
                  {t.task_name || t.id.slice(0, 8)}
                </Link>
              </td>
              <td className="px-4 py-3 text-xs" style={{ color: '#6b7280' }}>
                {t.date_to ? `${t.target_date} ~ ${t.date_to}` : (t.target_date || '-')}
              </td>
              <td className="px-4 py-3">
                <ProgressBar completed={t.completed_urls} total={t.total_urls} failed={t.failed_urls} />
              </td>
              <td className="px-4 py-3">
                <span className={STATUS_BADGE[t.status] || 'badge-gray'}>
                  {STATUS_LABEL[t.status] || t.status}
                </span>
              </td>
              <td className="px-4 py-3 text-xs" style={{ color: '#9ca3af' }}>{formatDate(t.created_at)}</td>
              <td className="px-4 py-3">
                <Link
                  href={`/articles?task_id=${t.id}`}
                  className="text-xs transition-colors"
                  style={{ color: '#3b82f6' }}
                >
                  查看文章
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
