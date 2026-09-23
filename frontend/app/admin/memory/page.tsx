'use client';

import { useCallback, useEffect, useState } from 'react';
import { api, ApiError } from '@/lib/api';
import { useToast } from '@/components/ui/Toast';

type EditRecord = {
  id: string;
  target_type: string;
  target_id: string;
  field: string;
  old_value: unknown;
  new_value: unknown;
  editor: string | null;
  created_at: string | null;
};

type SiteStat = { domain: string; attempts: number; fail_count: number; fail_rate: number };

export default function MemoryPage() {
  const [type, setType] = useState('');
  const [records, setRecords] = useState<EditRecord[]>([]);
  const [stats, setStats] = useState<SiteStat[]>([]);
  const [loading, setLoading] = useState(true);
  const { toast } = useToast();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const qs = type ? `?type=${type}&limit=50` : '?limit=50';
      const [recRes, statRes] = await Promise.all([
        api.get<{ items: EditRecord[]; total: number }>(`/api/v1/admin/memory/edit-records${qs}`),
        api.get<{ items: SiteStat[] }>('/api/v1/admin/memory/site-stats?days=7'),
      ]);
      setRecords(recRes.items);
      setStats(statRes.items);
    } catch (e: unknown) {
      toast(e instanceof ApiError ? e.message : '加载失败', 'error');
    } finally {
      setLoading(false);
    }
  }, [type, toast]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <main className="min-h-screen p-8 animate-fade-in">
      <h1 className="mb-6 text-lg font-semibold" style={{ color: '#18181b' }}>记忆</h1>

      <section className="card mb-6 p-6">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-sm font-medium" style={{ color: '#18181b' }}>站点降级排行（近 7 天）</h2>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr style={{ borderBottom: '1px solid #e5e7eb' }}>
              {['域名', '尝试', '失败', '失败率'].map((h) => (
                <th key={h} className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider" style={{ color: '#9ca3af' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {stats.length === 0 && (
              <tr><td colSpan={4} className="px-3 py-8 text-center text-xs" style={{ color: '#9ca3af' }}>暂无统计数据</td></tr>
            )}
            {stats.map((s) => (
              <tr key={s.domain} style={{ borderBottom: '1px solid #f3f4f6' }}>
                <td className="px-3 py-2" style={{ color: '#18181b' }}>{s.domain}</td>
                <td className="px-3 py-2" style={{ color: '#6b7280' }}>{s.attempts}</td>
                <td className="px-3 py-2" style={{ color: '#ef4444' }}>{s.fail_count}</td>
                <td className="px-3 py-2" style={{ color: '#6b7280' }}>{Math.round(s.fail_rate * 100)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="card p-6">
        <div className="mb-4 flex items-center gap-3">
          <h2 className="text-sm font-medium" style={{ color: '#18181b' }}>修改记录</h2>
          <select
            value={type}
            onChange={(e) => setType(e.target.value)}
            className="rounded-md px-2 py-1 text-xs"
            style={{ border: '1px solid #e5e7eb', color: '#18181b' }}
          >
            <option value="">全部</option>
            <option value="category">分类</option>
            <option value="tweet">推文</option>
          </select>
          {loading && <span className="text-xs" style={{ color: '#9ca3af' }}>加载中…</span>}
        </div>

        <table className="w-full text-sm">
          <thead>
            <tr style={{ borderBottom: '1px solid #e5e7eb' }}>
              {['时间', '类型', '字段', '改前', '改后', '操作人'].map((h) => (
                <th key={h} className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider" style={{ color: '#9ca3af' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {records.length === 0 && (
              <tr><td colSpan={6} className="px-3 py-8 text-center text-xs" style={{ color: '#9ca3af' }}>暂无修改记录</td></tr>
            )}
            {records.map((r) => (
              <tr key={r.id} style={{ borderBottom: '1px solid #f3f4f6' }}>
                <td className="px-3 py-2 text-xs" style={{ color: '#9ca3af' }}>{r.created_at?.slice(0, 19).replace('T', ' ') || '-'}</td>
                <td className="px-3 py-2 text-xs" style={{ color: '#6b7280' }}>{r.target_type}</td>
                <td className="px-3 py-2 text-xs" style={{ color: '#6b7280' }}>{r.field}</td>
                <td className="max-w-[240px] truncate px-3 py-2 text-xs" style={{ color: '#6b7280' }} title={JSON.stringify(r.old_value)}>{JSON.stringify(r.old_value)}</td>
                <td className="max-w-[240px] truncate px-3 py-2 text-xs" style={{ color: '#18181b' }} title={JSON.stringify(r.new_value)}>{JSON.stringify(r.new_value)}</td>
                <td className="px-3 py-2 text-xs" style={{ color: '#6b7280' }}>{r.editor || '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </main>
  );
}
