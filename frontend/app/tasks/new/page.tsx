'use client';
import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { api, ApiError } from '@/lib/api';
import { todayISO } from '@/lib/utils';
import { useToast } from '@/components/ui/Toast';

type LinkItem = { url: string; score: number };
type ScanResp = { entry_url: string; links: LinkItem[]; count: number };
type CreateResp = {
  task_id: string;
  status: string;
  total_urls: number;
  failed_urls: number;
};

type DistConfig = { id: string; channel_type: string; name: string; enabled: boolean };

const WEEKDAY_OPTIONS = [
  { value: 1, label: '周一' },
  { value: 2, label: '周二' },
  { value: 3, label: '周三' },
  { value: 4, label: '周四' },
  { value: 5, label: '周五' },
  { value: 6, label: '周六' },
  { value: 0, label: '周日' },
];

type PastTask = {
  id: string;
  task_name: string | null;
  target_date: string;
  date_to: string | null;
  url_list: string[];
  direct_urls?: string[];
  total_urls: number;
  status: string;
};

export default function NewTaskPage() {
  const router = useRouter();
  const [mode, setMode] = useState<'once' | 'scheduled'>('once');
  const [taskName, setTaskName] = useState('');
  const [dateFrom, setDateFrom] = useState(todayISO());
  const [dateTo, setDateTo] = useState(todayISO());
  const [noDateLimit, setNoDateLimit] = useState(false);
  const [directUrlText, setDirectUrlText] = useState('');
  const [entryUrlText, setEntryUrlText] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Preview state
  const [scanning, setScanning] = useState(false);
  const [links, setLinks] = useState<LinkItem[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [previewDone, setPreviewDone] = useState(false);

  // Past tasks history
  const [pastTasks, setPastTasks] = useState<PastTask[]>([]);
  const [showHistory, setShowHistory] = useState(false);

  useEffect(() => {
    api.get<{ items: PastTask[] }>('/api/v1/crawler/tasks?limit=20&offset=0')
      .then(data => setPastTasks(data.items.filter(t => t.task_name)))
      .catch(() => {});
  }, []);

  function selectPastTask(t: PastTask) {
    setTaskName(t.task_name || '');
    setDateFrom(t.target_date);
    setDateTo(t.date_to || t.target_date);
    if (t.url_list?.length) setEntryUrlText(t.url_list.join('\n'));
    setShowHistory(false);
  }

  async function onPreview() {
    setError(null);
    setLinks([]);
    setSelected(new Set());
    setPreviewDone(false);
    const entryUrl = entryUrlText.split(/\s+/).map((s) => s.trim()).filter(Boolean)[0];
    if (!entryUrl) {
      setError('请输入入口页 URL');
      return;
    }
    setScanning(true);
    try {
      const data = await api.post<ScanResp>('/api/v1/discovery/scan', {
        entry_url: entryUrl,
        max_depth: 2,
        max_links: 50,
      });
      setLinks(data.links);
      setSelected(new Set(data.links.map((l) => l.url)));
      setPreviewDone(true);
    } catch (err) {
      const e = err as ApiError;
      setError(`扫描失败 (${e.code}): ${e.message}`);
    } finally {
      setScanning(false);
    }
  }

  async function onSubmit(e: React.FormEvent, usePreviewUrls: boolean) {
    e.preventDefault();
    setError(null);

    let url_list: string[];
    if (usePreviewUrls && previewDone && selected.size > 0) {
      url_list = Array.from(selected);
    } else {
      url_list = entryUrlText.split(/\s+/).map((s) => s.trim()).filter(Boolean);
    }

    const direct_urls = directUrlText.split(/\s+/).map((s) => s.trim()).filter(Boolean);

    if (url_list.length === 0 && direct_urls.length === 0) {
      setError('请至少输入一个 URL（精确文章 URL 或入口页 URL）');
      return;
    }

    setLoading(true);
    try {
      const data = await api.post<CreateResp>('/api/v1/crawler/task', {
        url_list,
        direct_urls,
        target_date: noDateLimit ? '1970-01-01' : dateFrom,
        date_to: noDateLimit ? '2099-12-31' : (dateTo !== dateFrom ? dateTo : null),
        task_name: taskName || null,
      });
      router.push(`/tasks/${data.task_id}`);
    } catch (err) {
      const e = err as ApiError;
      setError(`提交失败 (${e.code}): ${e.message}`);
    } finally {
      setLoading(false);
    }
  }

  function toggle(url: string) {
    const next = new Set(selected);
    if (next.has(url)) next.delete(url);
    else next.add(url);
    setSelected(next);
  }

  function toggleAll() {
    if (selected.size === links.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(links.map((l) => l.url)));
    }
  }

  return (
    <main className="min-h-screen p-8 animate-fade-in">
      <div className="max-w-3xl mx-auto">
      <div className="mb-8 text-center">
        <h1 className="text-3xl font-semibold" style={{ color: '#18181b' }}>智能采集岛</h1>
      </div>

      {/* 顶部切换栏 */}
      <div className="flex justify-center mb-6">
        <div className="inline-flex items-center rounded-full p-1" style={{ background: '#f3f4f6' }}>
          <button
            type="button"
            onClick={() => setMode('once')}
            className="px-5 py-2 text-sm font-medium rounded-full transition-all duration-200"
            style={{
              background: mode === 'once' ? '#ffffff' : 'transparent',
              color: mode === 'once' ? '#18181b' : '#9ca3af',
              boxShadow: mode === 'once' ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
            }}
          >
            即时采集任务
          </button>
          <button
            type="button"
            onClick={() => setMode('scheduled')}
            className="px-5 py-2 text-sm font-medium rounded-full transition-all duration-200"
            style={{
              background: mode === 'scheduled' ? '#ffffff' : 'transparent',
              color: mode === 'scheduled' ? '#18181b' : '#9ca3af',
              boxShadow: mode === 'scheduled' ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
            }}
          >
            定时监控任务
          </button>
        </div>
      </div>

      {mode === 'once' && (
      <>
      <form className="card p-6 space-y-6">
        <div className="relative">
          <label className="mb-1.5 block text-sm" style={{ color: '#6b7280' }}>任务名称（可选）</label>
          <div className="relative">
            <input
              className="input pr-8"
              value={taskName}
              onChange={(e) => setTaskName(e.target.value)}
              onFocus={() => setShowHistory(true)}
              onBlur={() => setTimeout(() => setShowHistory(false), 200)}
              placeholder="如：政务公告每日采集"
            />
            {pastTasks.length > 0 && (
              <button
                type="button"
                className="absolute right-2 top-1/2 -translate-y-1/2 text-base px-1"
                style={{ color: '#9ca3af' }}
                onClick={() => setShowHistory(!showHistory)}
              >
                ▾
              </button>
            )}
          </div>
          {showHistory && pastTasks.length > 0 && (
            <div
              className="absolute z-10 mt-1 w-full max-h-48 overflow-y-auto rounded-lg shadow-lg"
              style={{ background: '#fff', border: '1px solid #e5e7eb' }}
            >
              {pastTasks.map(t => (
                <button
                  key={t.id}
                  type="button"
                  className="w-full text-left px-3 py-2 text-sm transition-colors hover:bg-gray-50"
                  style={{ color: '#18181b' }}
                  onMouseDown={(e) => { e.preventDefault(); selectPastTask(t); }}
                >
                  <span className="font-medium">{t.task_name}</span>
                  <span className="ml-2 text-xs" style={{ color: '#9ca3af' }}>
                    {t.target_date}{t.date_to ? ` ~ ${t.date_to}` : ''} · {t.total_urls} 条
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="grid grid-cols-3 gap-4">
          <div>
            <label className="mb-1.5 block text-sm" style={{ color: '#6b7280' }}>起始日期</label>
            <input
              type="date"
              className="input"
              value={noDateLimit ? '' : dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              disabled={noDateLimit}
              required={!noDateLimit}
            />
          </div>
          <div>
            <label className="mb-1.5 block text-sm" style={{ color: '#6b7280' }}>截止日期</label>
            <input
              type="date"
              className="input"
              value={noDateLimit ? '' : dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              disabled={noDateLimit}
              required={!noDateLimit}
            />
          </div>
          <div className="flex items-end">
            <button
              type="button"
              onClick={() => setNoDateLimit(!noDateLimit)}
              className="px-4 py-2.5 text-sm rounded-lg transition-all"
              style={{
                background: noDateLimit ? '#3b82f6' : '#f3f4f6',
                color: noDateLimit ? '#fff' : '#6b7280',
                border: '1px solid',
                borderColor: noDateLimit ? '#3b82f6' : '#e5e7eb',
              }}
            >
              无日期限制
            </button>
          </div>
        </div>

        <div>
          <label className="mb-1.5 block text-sm" style={{ color: '#6b7280' }}>
            精确文章 URL（每行一个，跳过发现直接爬取）
          </label>
          <textarea
            className="input h-28 resize-y font-mono text-xs"
            style={{ background: '#f9fafb' }}
            value={directUrlText}
            onChange={(e) => setDirectUrlText(e.target.value)}
            placeholder="https://example.com/news/2026/05/article-123.html"
          />
          <p className="mt-1.5 text-xs" style={{ color: '#9ca3af' }}>
            已知的文章直链，系统将直接爬取内容，不做站点发现。
          </p>
        </div>

        <div>
          <label className="mb-1.5 block text-sm" style={{ color: '#6b7280' }}>
            入口页 URL（每行一个，系统将扫描站点发现文章）
          </label>
          <textarea
            className="input h-28 resize-y font-mono text-xs"
            style={{ background: '#f9fafb' }}
            value={entryUrlText}
            onChange={(e) => setEntryUrlText(e.target.value)}
            placeholder="https://www.tsinghua.edu.cn/"
          />
          <p className="mt-1.5 text-xs" style={{ color: '#9ca3af' }}>
            列表页或首页，系统自动从入口发现该域名下的文章链接，再爬取入库。
          </p>
        </div>

        {error && (
          <div className="rounded-[12px] px-4 py-2.5 text-sm" style={{ background: 'rgba(239, 68, 68, 0.08)', color: '#ef4444', border: '1px solid rgba(239, 68, 68, 0.15)' }}>{error}</div>
        )}

        <div className="flex gap-3">
          <button
            type="button"
            disabled={scanning || !entryUrlText.trim()}
            onClick={onPreview}
            className="btn-primary disabled:opacity-50"
          >
            {scanning ? '扫描中…' : '预览入口页发现链接'}
          </button>
          <button
            type="button"
            disabled={loading}
            onClick={(e) => onSubmit(e, false)}
            className="btn-primary disabled:opacity-50"
          >
            {loading ? '提交中…' : '提交任务'}
          </button>
          <button type="button" onClick={() => router.push('/tasks')} className="btn-secondary">
            取消
          </button>
          <button type="button" onClick={() => router.push('/tasks')} className="btn-secondary">
            查看任务列表
          </button>
        </div>
      </form>

      {previewDone && (
        <section className="card p-6 mt-6 max-w-3xl">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-sm font-medium" style={{ color: '#18181b' }}>
              发现链接（{links.length} 条）
            </h2>
            <div className="flex items-center gap-4">
              <label className="flex items-center gap-2 text-sm cursor-pointer" style={{ color: '#6b7280' }}>
                <input
                  type="checkbox"
                  checked={selected.size === links.length && links.length > 0}
                  onChange={toggleAll}
                  style={{ accentColor: '#3b82f6' }}
                />
                全选
              </label>
            </div>
          </div>
          <div className="max-h-72 space-y-2 overflow-y-auto">
            {links.map((item) => (
              <label
                key={item.url}
                className="flex items-start gap-3 rounded-md p-3 cursor-pointer transition-colors duration-150"
                style={{ background: '#f9fafb' }}
              >
                <input
                  type="checkbox"
                  checked={selected.has(item.url)}
                  onChange={() => toggle(item.url)}
                  className="mt-0.5"
                  style={{ accentColor: '#3b82f6' }}
                />
                <div className="min-w-0 flex-1">
                  <p className="break-all text-xs" style={{ color: '#18181b' }}>{item.url}</p>
                  <p className="mt-0.5 text-xs" style={{ color: '#9ca3af' }}>评分 {item.score}</p>
                </div>
              </label>
            ))}
          </div>
          {links.length > 0 && (
            <div className="mt-4 flex justify-end">
              <button
                type="button"
                disabled={loading || selected.size === 0}
                onClick={(e) => onSubmit(e, true)}
                className="btn-primary disabled:opacity-50"
              >
                {loading ? '提交中…' : `以选中链接提交任务（${selected.size} 条）`}
              </button>
            </div>
          )}
        </section>
      )}
      </>
      )}

      {mode === 'scheduled' && (
      <section className="mt-8">
        <ScheduledTaskForm />
      </section>
      )}
      </div>
    </main>
  );
}

const CHANNEL_LABELS: Record<string, string> = {
  email: '邮件',
  webhook: '飞书',
};

function ScheduledTaskForm() {
  const [formName, setFormName] = useState('');
  const [formUrls, setFormUrls] = useState('');
  const [formWeekdays, setFormWeekdays] = useState<number[]>([1, 3, 5]);
  const [formConfigId, setFormConfigId] = useState('');
  const [formEnabled, setFormEnabled] = useState(true);
  const [allConfigs, setAllConfigs] = useState<DistConfig[]>([]);
  const [saving, setSaving] = useState(false);
  const { toast } = useToast();
  const router = useRouter();

  // 定时任务历史
  const [pastScheduled, setPastScheduled] = useState<{ id: string; name: string; url_list: string[]; weekdays: number[]; email_config_id: string; enabled: boolean }[]>([]);
  const [showScheduledHistory, setShowScheduledHistory] = useState(false);

  const fetchConfigs = useCallback(async () => {
    try {
      const data = await api.get<{ items: DistConfig[] }>('/api/v1/distribution/configs');
      setAllConfigs(data.items.filter(c => c.enabled));
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    fetchConfigs();
    api.get<{ items: { id: string; name: string; url_list: string[]; weekdays: number[]; email_config_id: string; enabled: boolean }[] }>('/api/v1/crawler/scheduled-crawls')
      .then(data => setPastScheduled(data.items))
      .catch(() => {});
  }, [fetchConfigs]);

  function selectPastScheduled(t: { name: string; url_list: string[]; weekdays: number[]; email_config_id: string; enabled: boolean }) {
    setFormName(t.name);
    setFormUrls(t.url_list.join('\n'));
    setFormWeekdays(t.weekdays);
    setFormConfigId(t.email_config_id);
    setFormEnabled(t.enabled);
    setShowScheduledHistory(false);
  }

  function toggleWeekday(day: number) {
    setFormWeekdays(prev => prev.includes(day) ? prev.filter(d => d !== day) : [...prev, day].sort());
  }

  async function handleSave() {
    if (!formName.trim()) { toast('请输入任务名称', 'error'); return; }
    const urls = formUrls.split('\n').map(s => s.trim()).filter(Boolean);
    if (urls.length === 0) { toast('请输入至少一个 URL', 'error'); return; }
    if (formWeekdays.length === 0) { toast('请选择至少一个执行日', 'error'); return; }
    if (!formConfigId) { toast('请选择发送通道', 'error'); return; }
    setSaving(true);
    try {
      await api.post('/api/v1/crawler/scheduled-crawls', {
        name: formName.trim(),
        url_list: urls,
        weekdays: formWeekdays,
        email_config_id: formConfigId,
        enabled: formEnabled,
      });
      toast('定时任务创建成功', 'success');
      setFormName(''); setFormUrls(''); setFormWeekdays([1, 3, 5]); setFormConfigId(''); setFormEnabled(true);
    } catch (e: unknown) {
      toast(e instanceof ApiError ? e.message : '创建失败', 'error');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="card p-6">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h2 className="text-base font-medium" style={{ color: '#18181b' }}>新建定时任务</h2>
          <p className="mt-1 text-xs" style={{ color: '#9ca3af' }}>定时从固定网站爬取文章并自动推送</p>
        </div>
      </div>

      <div className="space-y-4">
        <div className="relative">
          <label className="block text-xs mb-1" style={{ color: '#9ca3af' }}>任务名称</label>
          <div className="relative">
            <input value={formName} onChange={e => setFormName(e.target.value)} onFocus={() => setShowScheduledHistory(true)} onBlur={() => setTimeout(() => setShowScheduledHistory(false), 200)} className="input pr-8" placeholder="如：每日政策爬取" />
            {pastScheduled.length > 0 && (
              <button type="button" className="absolute right-2 top-1/2 -translate-y-1/2 text-base px-1" style={{ color: '#9ca3af' }} onClick={() => setShowScheduledHistory(!showScheduledHistory)}>▾</button>
            )}
          </div>
          {showScheduledHistory && pastScheduled.length > 0 && (
            <div className="absolute z-10 mt-1 w-full max-h-48 overflow-y-auto rounded-lg shadow-lg" style={{ background: '#fff', border: '1px solid #e5e7eb' }}>
              {pastScheduled.map(t => (
                <button key={t.id} type="button" className="w-full text-left px-3 py-2 text-sm transition-colors hover:bg-gray-50" style={{ color: '#18181b' }} onMouseDown={(e) => { e.preventDefault(); selectPastScheduled(t); }}>
                  <span className="font-medium">{t.name}</span>
                  <span className="ml-2 text-xs" style={{ color: '#9ca3af' }}>{t.url_list.length} 条 URL</span>
                </button>
              ))}
            </div>
          )}
        </div>
        <div>
          <label className="block text-xs mb-1" style={{ color: '#9ca3af' }}>URL 列表（每行一个）</label>
          <textarea value={formUrls} onChange={e => setFormUrls(e.target.value)} className="input" rows={4}
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
          <label className="block text-xs mb-1" style={{ color: '#9ca3af' }}>发送通道</label>
          <select value={formConfigId} onChange={e => setFormConfigId(e.target.value)} className="input">
            <option value="">请选择</option>
            {allConfigs.map(c => <option key={c.id} value={c.id}>{c.name}（{CHANNEL_LABELS[c.channel_type] || c.channel_type}）</option>)}
          </select>
          {allConfigs.length === 0 && (
            <p className="mt-1 text-xs" style={{ color: '#ef4444' }}>
              暂无可用通道，请先在设置页分发配置中添加
            </p>
          )}
        </div>
        <label className="flex items-center gap-2 text-sm cursor-pointer" style={{ color: '#6b7280' }}>
          <input type="checkbox" checked={formEnabled} onChange={e => setFormEnabled(e.target.checked)}
            className="h-4 w-4 rounded" style={{ accentColor: '#3b82f6' }} />
          启用
        </label>
      </div>

      <div className="mt-5 flex items-center gap-3">
        <button onClick={handleSave} disabled={saving} className="btn-primary">
          {saving ? '创建中…' : '创建定时任务'}
        </button>
        <button onClick={() => router.push('/tasks')} className="btn-secondary text-xs">
          查看任务列表
        </button>
      </div>
    </div>
  );
}
