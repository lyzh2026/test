'use client';

import { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import { api, ApiError } from '@/lib/api';
import { TaskTable } from '@/components/tasks/TaskTable';
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

// ── 定时任务类型 ──

type ScheduledCrawl = {
  id: string;
  name: string;
  url_list: string[];
  weekdays: number[];
  weekday_labels: string[];
  email_config_id: string;
  enabled: boolean;
  last_run_at: string | null;
  last_task_id: string | null;
  created_at: string | null;
};

type DistConfig = {
  id: string;
  channel_type: string;
  name: string;
  enabled: boolean;
};

const WEEKDAY_OPTIONS = [
  { value: 1, label: '周一' },
  { value: 2, label: '周二' },
  { value: 3, label: '周三' },
  { value: 4, label: '周四' },
  { value: 5, label: '周五' },
  { value: 6, label: '周六' },
  { value: 0, label: '周日' },
];

export default function TasksPage() {
  const [tab, setTab] = useState<'once' | 'scheduled'>('once');

  return (
    <main className="min-h-screen p-8 animate-fade-in">
      {/* Tab 切换 */}
      <div className="mb-6 flex items-center gap-1">
        {(['once', 'scheduled'] as const).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className="px-4 py-2 text-sm font-medium rounded-lg transition-colors"
            style={{
              background: tab === t ? '#18181b' : 'transparent',
              color: tab === t ? '#fff' : '#6b7280',
            }}
          >
            {t === 'once' ? '一次性任务' : '定时任务'}
          </button>
        ))}
      </div>

      {tab === 'once' ? <OnceTasksTab /> : <ScheduledTasksTab />}
    </main>
  );
}


// ── 一次性任务 ──

function OnceTasksTab() {
  const [items, setItems] = useState<Task[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [offset, setOffset] = useState(0);

  const [statusFilter, setStatusFilter] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [keyword, setKeyword] = useState('');

  const fetchTasks = useCallback(async (newOffset: number = 0) => {
    setLoading(true);
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
      setLoading(false);
    }
  }, [statusFilter, dateFrom, dateTo, keyword]);

  useEffect(() => { fetchTasks(0); }, [fetchTasks]);

  function handleSearch() { fetchTasks(0); }
  function handleReset() {
    setStatusFilter(''); setDateFrom(''); setDateTo(''); setKeyword('');
  }

  const totalPages = Math.ceil(total / PAGE_SIZE);
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  return (
    <>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold" style={{ color: '#18181b' }}>任务列表</h1>
          <p className="mt-1.5 text-sm" style={{ color: '#9ca3af' }}>管理与监控采集任务</p>
        </div>
        <Link href="/tasks/new" className="btn-primary">
          + 新建任务
        </Link>
      </div>

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


// ── 定时任务 ──

function ScheduledTasksTab() {
  const [items, setItems] = useState<ScheduledCrawl[]>([]);
  const [loading, setLoading] = useState(true);
  const [formOpen, setFormOpen] = useState(false);
  const [editId, setEditId] = useState<string | null>(null);

  const [formName, setFormName] = useState('');
  const [formUrls, setFormUrls] = useState('');
  const [formWeekdays, setFormWeekdays] = useState<number[]>([1, 3, 5]);
  const [formConfigId, setFormConfigId] = useState('');
  const [formEnabled, setFormEnabled] = useState(true);
  const [emailConfigs, setEmailConfigs] = useState<DistConfig[]>([]);
  const { toast, confirm } = useToast();

  const fetchList = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.get<{ items: ScheduledCrawl[] }>('/api/v1/crawler/scheduled-crawls');
      setItems(data.items);
    } catch { /* ignore */ } finally {
      setLoading(false);
    }
  }, []);

  const fetchEmailConfigs = useCallback(async () => {
    try {
      const data = await api.get<{ items: DistConfig[] }>('/api/v1/distribution/configs');
      setEmailConfigs(data.items.filter(c => c.channel_type === 'email' && c.enabled));
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { fetchList(); fetchEmailConfigs(); }, [fetchList, fetchEmailConfigs]);

  function openNew() {
    setEditId(null); setFormName(''); setFormUrls(''); setFormWeekdays([1, 3, 5]);
    setFormConfigId(''); setFormEnabled(true); setFormOpen(true);
  }

  function openEdit(item: ScheduledCrawl) {
    setEditId(item.id); setFormName(item.name); setFormUrls(item.url_list.join('\n'));
    setFormWeekdays(item.weekdays); setFormConfigId(item.email_config_id);
    setFormEnabled(item.enabled); setFormOpen(true);
  }

  function toggleWeekday(day: number) {
    setFormWeekdays(prev => prev.includes(day) ? prev.filter(d => d !== day) : [...prev, day].sort());
  }

  async function handleSave() {
    if (!formName.trim()) return;
    const urls = formUrls.split('\n').map(s => s.trim()).filter(Boolean);
    if (urls.length === 0 || formWeekdays.length === 0 || !formConfigId) return;
    try {
      const payload = { name: formName.trim(), url_list: urls, weekdays: formWeekdays, email_config_id: formConfigId, enabled: formEnabled };
      if (editId) {
        await api.put(`/api/v1/crawler/scheduled-crawls/${editId}`, payload);
      } else {
        await api.post('/api/v1/crawler/scheduled-crawls', payload);
      }
      setFormOpen(false); fetchList();
    } catch (e: unknown) { toast(e instanceof ApiError ? e.message : '保存失败', 'error'); }
  }

  async function handleToggle(id: string) {
    try { await api.post(`/api/v1/crawler/scheduled-crawls/${id}/toggle`); fetchList(); }
    catch (e: unknown) { toast(e instanceof ApiError ? e.message : '操作失败', 'error'); }
  }

  async function handleDelete(id: string) {
    if (!await confirm('确认删除此定时任务？')) return;
    try { await api.delete(`/api/v1/crawler/scheduled-crawls/${id}`); fetchList(); }
    catch (e: unknown) { toast(e instanceof ApiError ? e.message : '删除失败', 'error'); }
  }

  async function handleRunNow(id: string) {
    if (!await confirm('确认立即执行一次？')) return;
    try { await api.post(`/api/v1/crawler/scheduled-crawls/${id}/run`); toast('已触发执行', 'success'); }
    catch (e: unknown) { toast(e instanceof ApiError ? e.message : '触发失败', 'error'); }
  }

  return (
    <>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold" style={{ color: '#18181b' }}>定时任务</h1>
          <p className="mt-1.5 text-sm" style={{ color: '#9ca3af' }}>定时从固定网站爬取文章并逐篇邮件推送</p>
        </div>
        <button onClick={openNew} className="btn-primary">+ 新建定时任务</button>
      </div>

      {loading ? (
        <p className="text-sm" style={{ color: '#9ca3af' }}>加载中…</p>
      ) : items.length === 0 ? (
        <div className="card p-8 text-center text-sm" style={{ color: '#9ca3af' }}>暂无定时任务</div>
      ) : (
        <div className="card overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr style={{ borderBottom: '1px solid #e5e7eb' }}>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider" style={{ color: '#9ca3af' }}>任务名称</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider" style={{ color: '#9ca3af' }}>URL 数</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider" style={{ color: '#9ca3af' }}>执行日</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider" style={{ color: '#9ca3af' }}>状态</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider" style={{ color: '#9ca3af' }}>上次执行</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider" style={{ color: '#9ca3af' }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {items.map(item => (
                <tr key={item.id} className="transition-colors duration-150 hover:bg-surface-50" style={{ borderBottom: '1px solid #e5e7eb' }}>
                  <td className="px-4 py-3" style={{ color: '#18181b' }}>{item.name}</td>
                  <td className="px-4 py-3 text-xs" style={{ color: '#6b7280' }}>{item.url_list.length}</td>
                  <td className="px-4 py-3 text-xs" style={{ color: '#6b7280' }}>{item.weekday_labels.join('、')}</td>
                  <td className="px-4 py-3">
                    <button onClick={() => handleToggle(item.id)}
                      className={item.enabled ? 'badge-green cursor-pointer' : 'badge-gray cursor-pointer'}>
                      {item.enabled ? '已启用' : '已禁用'}
                    </button>
                  </td>
                  <td className="px-4 py-3 text-xs" style={{ color: '#9ca3af' }}>
                    {item.last_run_at ? new Date(item.last_run_at).toLocaleString('zh-CN') : '从未执行'}
                  </td>
                  <td className="px-4 py-3">
                    <button onClick={() => handleRunNow(item.id)} className="text-xs transition-colors mr-3" style={{ color: '#3b82f6' }}>立即执行</button>
                    <button onClick={() => openEdit(item)} className="text-xs transition-colors mr-3" style={{ color: '#6b7280' }}>编辑</button>
                    <button onClick={() => handleDelete(item.id)} className="text-xs" style={{ color: '#ef4444' }}>删除</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Form Modal */}
      {formOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center animate-fade-in" style={{ background: 'rgba(0,0,0,0.6)' }}>
          <div className="w-full max-w-lg card p-6 animate-slide-up" style={{ background: '#fcfcfc' }}>
            <h2 className="mb-5 text-base font-medium" style={{ color: '#18181b' }}>
              {editId ? '编辑' : '新建'}定时任务
            </h2>
            <div className="space-y-4">
              <div>
                <label className="block text-xs mb-1" style={{ color: '#9ca3af' }}>任务名称</label>
                <input value={formName} onChange={e => setFormName(e.target.value)} className="input" placeholder="如：每日政策爬取" />
              </div>
              <div>
                <label className="block text-xs mb-1" style={{ color: '#9ca3af' }}>URL 列表（每行一个）</label>
                <textarea value={formUrls} onChange={e => setFormUrls(e.target.value)} className="input" rows={5}
                  placeholder={"https://example.gov.cn/news\nhttps://another.gov.cn/policy"} style={{ resize: 'vertical' }} />
              </div>
              <div>
                <label className="block text-xs mb-1" style={{ color: '#9ca3af' }}>执行日</label>
                <div className="flex flex-wrap gap-2">
                  {WEEKDAY_OPTIONS.map(opt => (
                    <button key={opt.value} type="button" onClick={() => toggleWeekday(opt.value)}
                      className="px-3 py-1 rounded-full text-xs font-medium transition-colors"
                      style={{ background: formWeekdays.includes(opt.value) ? '#3b82f6' : '#f3f4f6', color: formWeekdays.includes(opt.value) ? '#fff' : '#6b7280' }}>
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label className="block text-xs mb-1" style={{ color: '#9ca3af' }}>邮件通道</label>
                <select value={formConfigId} onChange={e => setFormConfigId(e.target.value)} className="input">
                  <option value="">请选择</option>
                  {emailConfigs.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
                {emailConfigs.length === 0 && (
                  <p className="mt-1 text-xs" style={{ color: '#ef4444' }}>暂无可用邮件通道，请先在分发配置中添加</p>
                )}
              </div>
              <label className="flex items-center gap-2 text-sm cursor-pointer" style={{ color: '#6b7280' }}>
                <input type="checkbox" checked={formEnabled} onChange={e => setFormEnabled(e.target.checked)}
                  className="h-4 w-4 rounded" style={{ accentColor: '#3b82f6' }} />
                启用
              </label>
            </div>
            <div className="mt-6 flex justify-end gap-3">
              <button onClick={() => setFormOpen(false)} className="btn-secondary">取消</button>
              <button onClick={handleSave} className="btn-primary">保存</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
