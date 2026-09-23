'use client';

import { useCallback, useEffect, useState } from 'react';
import { api, ApiError } from '@/lib/api';
import { useToast } from '@/components/ui/Toast';

type Policy = {
  id: string;
  domain: string;
  mode: string;
  source: string;
  reason: string | null;
  promoted_at: string | null;
  enabled: boolean;
  created_at: string | null;
};

const MODE_LABEL: Record<string, string> = {
  auto: '自动',
  always_aibrowser: '直连 AI Browser',
  always_static: '强制静态',
};

export default function AiBrowserPanel() {
  const [enabled, setEnabled] = useState(false);
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [domain, setDomain] = useState('');
  const [mode, setMode] = useState('always_aibrowser');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const { toast, confirm } = useToast();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [toggle, list] = await Promise.all([
        api.get<{ enabled: boolean }>('/api/v1/admin/settings/ai-browser'),
        api.get<{ items: Policy[] }>('/api/v1/admin/render-policy'),
      ]);
      setEnabled(toggle.enabled);
      setPolicies(list.items);
    } catch (e: unknown) {
      toast(e instanceof ApiError ? e.message : '加载失败', 'error');
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleToggle(next: boolean) {
    setSaving(true);
    try {
      const res = await api.put<{ enabled: boolean }>('/api/v1/admin/settings/ai-browser', { enabled: next });
      setEnabled(res.enabled);
      toast(next ? '已开启 AI Browser 兜底' : '已关闭 AI Browser 兜底', 'success');
    } catch (e: unknown) {
      toast(e instanceof ApiError ? e.message : '保存失败', 'error');
    } finally {
      setSaving(false);
    }
  }

  async function handleAdd() {
    const d = domain.trim();
    if (!d) return;
    setSaving(true);
    try {
      const item = await api.post<Policy>('/api/v1/admin/render-policy', { domain: d, mode });
      setPolicies((prev) => [...prev, item].sort((a, b) => a.domain.localeCompare(b.domain)));
      setDomain('');
      toast('已加入渲染路由白名单', 'success');
    } catch (e: unknown) {
      toast(e instanceof ApiError ? e.message : '添加失败', 'error');
    } finally {
      setSaving(false);
    }
  }

  async function handleTogglePolicy(item: Policy) {
    try {
      const res = await api.put<Policy>(`/api/v1/admin/render-policy/${item.id}`, { enabled: !item.enabled });
      setPolicies((prev) => prev.map((p) => (p.id === res.id ? res : p)));
    } catch (e: unknown) {
      toast(e instanceof ApiError ? e.message : '保存失败', 'error');
    }
  }

  async function handleDelete(item: Policy) {
    if (!(await confirm(`确认删除 ${item.domain} 的渲染路由策略？`))) return;
    try {
      await api.delete(`/api/v1/admin/render-policy/${item.id}`);
      setPolicies((prev) => prev.filter((p) => p.id !== item.id));
      toast('已删除', 'success');
    } catch (e: unknown) {
      toast(e instanceof ApiError ? e.message : '删除失败', 'error');
    }
  }

  if (loading) {
    return <div className="card p-6 text-xs" style={{ color: '#9ca3af' }}>加载中…</div>;
  }

  return (
    <section className="card p-6">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h2 className="text-sm font-medium" style={{ color: '#18181b' }}>AI Browser 兜底</h2>
          <p className="mt-1 text-xs" style={{ color: '#9ca3af' }}>
            开启后，三层渲染全失败的页面会异步交给 AI Browser 重试；关闭时行为与本功能上线前完全一致。
          </p>
        </div>
        <label className="flex shrink-0 cursor-pointer items-center gap-2">
          <input
            type="checkbox"
            checked={enabled}
            disabled={saving}
            onChange={(e) => handleToggle(e.target.checked)}
          />
          <span className="text-xs" style={{ color: '#6b7280' }}>{enabled ? '已开启' : '已关闭'}</span>
        </label>
      </div>

      <div className="mb-3 flex items-center gap-2">
        <input
          value={domain}
          onChange={(e) => setDomain(e.target.value)}
          placeholder="example.com"
          className="flex-1 rounded-md px-3 py-2 text-sm"
          style={{ border: '1px solid #e5e7eb', color: '#18181b' }}
        />
        <select
          value={mode}
          onChange={(e) => setMode(e.target.value)}
          className="rounded-md px-2 py-2 text-xs"
          style={{ border: '1px solid #e5e7eb', color: '#18181b' }}
        >
          {Object.entries(MODE_LABEL).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>
        <button onClick={handleAdd} disabled={saving || !domain.trim()} className="btn-primary text-xs disabled:opacity-40">
          加入白名单
        </button>
      </div>

      <table className="w-full text-sm">
        <thead>
          <tr style={{ borderBottom: '1px solid #e5e7eb' }}>
            {['域名', '模式', '来源', '原因', '启用', ''].map((h) => (
              <th key={h} className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider" style={{ color: '#9ca3af' }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {policies.length === 0 && (
            <tr><td colSpan={6} className="px-3 py-8 text-center text-xs" style={{ color: '#9ca3af' }}>暂无渲染路由策略</td></tr>
          )}
          {policies.map((p) => (
            <tr key={p.id} style={{ borderBottom: '1px solid #f3f4f6' }}>
              <td className="px-3 py-2" style={{ color: '#18181b' }}>{p.domain}</td>
              <td className="px-3 py-2 text-xs" style={{ color: '#6b7280' }}>{MODE_LABEL[p.mode] || p.mode}</td>
              <td className="px-3 py-2 text-xs" style={{ color: p.source === 'auto' ? '#a855f7' : '#6b7280' }}>
                {p.source === 'auto' ? '自动晋升' : '手动'}
              </td>
              <td className="max-w-[280px] truncate px-3 py-2 text-xs" style={{ color: '#9ca3af' }} title={p.reason || ''}>{p.reason || '-'}</td>
              <td className="px-3 py-2">
                <input type="checkbox" checked={p.enabled} onChange={() => handleTogglePolicy(p)} />
              </td>
              <td className="px-3 py-2">
                <button onClick={() => handleDelete(p)} className="text-xs" style={{ color: '#ef4444' }}>删除</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
