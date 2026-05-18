'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import { api } from '@/lib/api';
import { TaskTable } from '@/components/tasks/TaskTable';
import { ScheduledTasksPanel } from '@/components/tasks/ScheduledTasksPanel';

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

type TaskListResp = { items: Task[]; total: number; limit: number; offset: number };

const STATUS_OPTIONS = [
  { value: '', label: '全部状态' },
  { value: 'pending', label: '等待中' },
  { value: 'running', label: '运行中' },
  { value: 'completed', label: '已完成' },
  { value: 'partial_failed', label: '部分失败' },
  { value: 'failed', label: '失败' },
  { value: 'cancelled', label: '已取消' },
];

const PAGE_SIZE = 20;
const POLL_INTERVAL = 3000;

export default function TasksPage() {
  const [tab, setTab] = useState<'once' | 'scheduled'>('once');

  return (
    <main className="min-h-screen p-8 animate-fade-in">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold" style={{ color: '#18181b' }}>任务列表</h1>
        <p className="mt-1.5 text-sm" style={{ color: '#9ca3af' }}>管理与监控采集任务</p>
      </div>

      <div className="mb-6 flex gap-1 p-1 rounded-lg" style={{ background: '#f3f4f6', width: 'fit-content' }}>
        <button
          onClick={() => setTab('once')}
          className="px-4 py-1.5 rounded-md text-sm font-medium transition-all"
          style={{
            background: tab === 'once' ? '#ffffff' : 'transparent',
            color: tab === 'once' ? '#18181b' : '#6b7280',
            boxShadow: tab === 'once' ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
          }}
        >
          一次性任务
        </button>
        <button
          onClick={() => setTab('scheduled')}
          className="px-4 py-1.5 rounded-md text-sm font-medium transition-all"
          style={{
            background: tab === 'scheduled' ? '#ffffff' : 'transparent',
            color: tab === 'scheduled' ? '#18181b' : '#6b7280',
            boxShadow: tab === 'scheduled' ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
          }}
        >
          定时任务
        </button>
      </div>

      {tab === 'once' ? <OnceTasksTab /> : <ScheduledTasksPanel />}
    </main>
  );
}


function OnceTasksTab() {
  const [items, setItems] = useState<Task[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [offset, setOffset] = useState(0);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const [statusFilter, setStatusFilter] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [keyword, setKeyword] = useState('');

  const fetchTasks = useCallback(async (newOffset: number = 0, silent = false) => {
    if (!silent) setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set('limit', String(PAGE_SIZE));
      params.set('offset', String(newOffset));
      if (statusFilter) params.set('status', statusFilter);
      if (dateFrom) params.set('date_from', dateFrom);
      if (dateTo) params.set('date_to', dateTo);
      if (keyword.trim()) params.set('keyword', keyword.trim());

      const data = await api.get<TaskListResp>(`/api/v1/crawler/tasks?${params.toString()}`);
      setItems(data.items);
      setTotal(data.total);
      setOffset(newOffset);
    } catch {
      // ignore
    } finally {
      if (!silent) setLoading(false);
    }
  }, [statusFilter, dateFrom, dateTo, keyword]);

  useEffect(() => { fetchTasks(0); }, [fetchTasks]);

  // Poll when there are running/pending tasks
  useEffect(() => {
    const hasActive = items.some(t => t.status === 'running' || t.status === 'pending');
    if (hasActive && !pollRef.current) {
      pollRef.current = setInterval(() => fetchTasks(offset, true), POLL_INTERVAL);
    } else if (!hasActive && pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [items, offset, fetchTasks]);

  function handleSearch() { fetchTasks(0); }
  function handleReset() {
    setStatusFilter(''); setDateFrom(''); setDateTo(''); setKeyword('');
  }

  const totalPages = Math.ceil(total / PAGE_SIZE);
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  return (
    <>
      <div className="card p-4 mb-6">
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="block text-xs mb-1" style={{ color: '#9ca3af' }}>状态</label>
            <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} className="input" style={{ width: 140 }}>
              {STATUS_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs mb-1" style={{ color: '#9ca3af' }}>开始日期</label>
            <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} className="input" style={{ width: 150 }} />
          </div>
          <div>
            <label className="block text-xs mb-1" style={{ color: '#9ca3af' }}>结束日期</label>
            <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} className="input" style={{ width: 150 }} />
          </div>
          <div>
            <label className="block text-xs mb-1" style={{ color: '#9ca3af' }}>关键词</label>
            <input value={keyword} onChange={e => setKeyword(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSearch()} className="input" placeholder="搜索任务名称" style={{ width: 180 }} />
          </div>
          <button onClick={handleSearch} className="btn-primary">查询</button>
          <button onClick={handleReset} className="btn-secondary">重置</button>
        </div>
      </div>

      <div className="mb-4">
        <span className="text-xs" style={{ color: '#9ca3af' }}>共 {total} 个任务</span>
      </div>

      {loading ? (
        <p className="text-sm" style={{ color: '#9ca3af' }}>加载中…</p>
      ) : (
        <TaskTable items={items} onRefresh={() => fetchTasks(offset)} />
      )}

      {totalPages > 1 && (
        <div className="mt-4 flex items-center justify-center gap-3">
          <button onClick={() => fetchTasks(offset - PAGE_SIZE)} disabled={currentPage <= 1}
            className="btn-secondary text-xs disabled:opacity-40">上一页</button>
          <span className="text-xs" style={{ color: '#6b7280' }}>第 {currentPage} / {totalPages} 页</span>
          <button onClick={() => fetchTasks(offset + PAGE_SIZE)} disabled={currentPage >= totalPages}
            className="btn-secondary text-xs disabled:opacity-40">下一页</button>
        </div>
      )}
    </>
  );
}
