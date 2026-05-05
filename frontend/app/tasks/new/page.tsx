'use client';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { api, ApiError } from '@/lib/api';
import { todayISO } from '@/lib/utils';

type LinkItem = { url: string; score: number };
type ScanResp = { entry_url: string; links: LinkItem[]; count: number };
type CreateResp = {
  task_id: string;
  status: string;
  total_urls: number;
  failed_urls: number;
};

export default function NewTaskPage() {
  const router = useRouter();
  const [taskName, setTaskName] = useState('');
  const [dateFrom, setDateFrom] = useState(todayISO());
  const [dateTo, setDateTo] = useState(todayISO());
  const [urlText, setUrlText] = useState('');
  const [priority, setPriority] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Preview state
  const [scanning, setScanning] = useState(false);
  const [links, setLinks] = useState<LinkItem[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [previewDone, setPreviewDone] = useState(false);

  async function onPreview() {
    setError(null);
    setLinks([]);
    setSelected(new Set());
    setPreviewDone(false);
    const entryUrl = urlText.split(/\s+/).map((s) => s.trim()).filter(Boolean)[0];
    if (!entryUrl) {
      setError('请输入入口 URL');
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
      url_list = urlText.split(/\s+/).map((s) => s.trim()).filter(Boolean);
    }

    if (url_list.length === 0) {
      setError('请至少选择一个链接');
      return;
    }

    setLoading(true);
    try {
      const data = await api.post<CreateResp>('/api/v1/crawler/task', {
        url_list,
        target_date: dateFrom,
        date_to: dateTo !== dateFrom ? dateTo : null,
        task_name: taskName || null,
        priority,
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
      <div className="mb-8">
        <h1 className="text-2xl font-semibold" style={{ color: '#e8e9ed' }}>新建采集任务</h1>
        <p className="mt-1.5 text-sm" style={{ color: '#6b6d7b' }}>配置入口 URL 与采集参数</p>
      </div>

      <form className="card p-6 space-y-6 max-w-3xl">
        <div>
          <label className="mb-1.5 block text-sm" style={{ color: '#a8abb8' }}>任务名称（可选）</label>
          <input
            className="input"
            value={taskName}
            onChange={(e) => setTaskName(e.target.value)}
            placeholder="如：政务公告每日采集"
          />
        </div>

        <div className="grid grid-cols-3 gap-4">
          <div>
            <label className="mb-1.5 block text-sm" style={{ color: '#a8abb8' }}>起始日期</label>
            <input
              type="date"
              className="input"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              required
            />
          </div>
          <div>
            <label className="mb-1.5 block text-sm" style={{ color: '#a8abb8' }}>截止日期</label>
            <input
              type="date"
              className="input"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              required
            />
          </div>
          <div>
            <label className="mb-1.5 block text-sm" style={{ color: '#a8abb8' }}>优先级</label>
            <select
              className="input"
              value={priority}
              onChange={(e) => setPriority(parseInt(e.target.value, 10))}
            >
              <option value={1}>普通 (1)</option>
              <option value={2}>较高 (2)</option>
              <option value={3}>最高 (3)</option>
            </select>
          </div>
        </div>

        <div>
          <label className="mb-1.5 block text-sm" style={{ color: '#a8abb8' }}>
            入口 URL（每行一个，系统将自动扫描站点发现文章）
          </label>
          <textarea
            className="input h-36 resize-y font-mono text-xs"
            style={{ background: '#181b25' }}
            value={urlText}
            onChange={(e) => setUrlText(e.target.value)}
            placeholder="https://www.tsinghua.edu.cn/"
            required
          />
          <p className="mt-1.5 text-xs" style={{ color: '#6b6d7b' }}>
            提交后系统自动从入口 URL 发现该域名下的文章链接，爬取后按目标日期过滤入库。
          </p>
        </div>

        {error && (
          <div className="rounded-[12px] px-4 py-2.5 text-sm" style={{ background: 'rgba(228, 90, 90, 0.08)', color: '#e45a5a', border: '1px solid rgba(228, 90, 90, 0.15)' }}>{error}</div>
        )}

        <div className="flex gap-3">
          <button
            type="button"
            disabled={scanning}
            onClick={onPreview}
            className="btn-primary disabled:opacity-50"
          >
            {scanning ? '扫描中…' : '预览发现链接'}
          </button>
          <button
            type="button"
            disabled={loading}
            onClick={(e) => onSubmit(e, false)}
            className="btn-primary disabled:opacity-50"
          >
            {loading ? '提交中…' : '直接提交任务'}
          </button>
          <button type="button" onClick={() => router.push('/tasks')} className="btn-secondary">
            取消
          </button>
        </div>
      </form>

      {previewDone && (
        <section className="card p-6 mt-6 max-w-3xl">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-sm font-medium" style={{ color: '#e8e9ed' }}>
              发现链接（{links.length} 条）
            </h2>
            <div className="flex items-center gap-4">
              <label className="flex items-center gap-2 text-sm" style={{ color: '#a8abb8' }} cursor-pointer>
                <input
                  type="checkbox"
                  checked={selected.size === links.length && links.length > 0}
                  onChange={toggleAll}
                  style={{ accentColor: '#6b8cff' }}
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
                style={{ background: '#181b25' }}
              >
                <input
                  type="checkbox"
                  checked={selected.has(item.url)}
                  onChange={() => toggle(item.url)}
                  className="mt-0.5"
                  style={{ accentColor: '#6b8cff' }}
                />
                <div className="min-w-0 flex-1">
                  <p className="break-all text-xs" style={{ color: '#e8e9ed' }}>{item.url}</p>
                  <p className="mt-0.5 text-xs" style={{ color: '#6b6d7b' }}>评分 {item.score}</p>
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
    </main>
  );
}
