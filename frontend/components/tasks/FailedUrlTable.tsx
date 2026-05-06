'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { useToast } from '@/components/ui/Toast';

type FailedDetail = {
  url: string;
  code: number;
  reason: string;
  stage?: string;
};

type BrowseResult = {
  success: number;
  failed: { url: string; reason: string }[];
  total: number;
};

const STAGE_BADGE: Record<string, string> = {
  render: 'badge-red',
  extract: 'badge-amber',
  validate: 'badge-gray',
  date_filter: 'badge-blue',
  dedup: 'badge-green',
};

export function FailedUrlTable({
  taskId,
  failedDetails,
  taskStatus,
}: {
  taskId: string;
  failedDetails: FailedDetail[];
  taskStatus: string;
}) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [browsing, setBrowsing] = useState(false);
  const [result, setResult] = useState<BrowseResult | null>(null);
  const router = useRouter();
  const { toast, confirm } = useToast();

  const canBrowse = taskStatus === 'partial_failed' || taskStatus === 'failed';

  function toggle(url: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(url)) next.delete(url);
      else next.add(url);
      return next;
    });
  }

  function toggleAll() {
    if (selected.size === failedDetails.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(failedDetails.map((d) => d.url)));
    }
  }

  async function handleAIBrowse() {
    if (!await confirm(`确认使用 AI 浏览选中的 ${selected.size} 个 URL？`)) return;
    setBrowsing(true);
    setResult(null);
    try {
      const data = await api.post<BrowseResult>(
        `/api/v1/crawler/task/${taskId}/ai-browse`,
        { urls: Array.from(selected) },
      );
      setResult(data);
      setSelected(new Set());
      router.refresh();
    } catch (e: unknown) {
      toast(e instanceof Error ? e.message : 'AI 浏览失败', 'error');
    } finally {
      setBrowsing(false);
    }
  }

  return (
    <section className="card p-6 mb-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-medium" style={{ color: '#18181b' }}>
          失败详情
        </h2>
        {canBrowse && selected.size > 0 && (
          <button
            onClick={handleAIBrowse}
            disabled={browsing}
            className="rounded-md px-3 py-1.5 text-xs font-medium transition-all duration-150 disabled:opacity-50"
            style={{ background: 'rgba(59, 130, 246, 0.1)', color: '#3b82f6' }}
          >
            {browsing ? 'AI 浏览中…' : `AI 浏览 (${selected.size})`}
          </button>
        )}
      </div>

      {result && (
        <div
          className="mb-4 rounded-md p-3 text-xs"
          style={{ background: 'rgba(59, 130, 246, 0.05)', color: '#6b7280' }}
        >
          成功 {result.success}/{result.total}
          {result.failed.length > 0 && <>，失败 {result.failed.length} 个</>}
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-xs" style={{ color: '#9ca3af' }}>
            <tr style={{ borderBottom: '1px solid #e5e7eb' }}>
              {canBrowse && (
                <th className="pb-2 pr-2 w-8">
                  <input
                    type="checkbox"
                    checked={selected.size === failedDetails.length && failedDetails.length > 0}
                    onChange={toggleAll}
                    className="h-4 w-4 cursor-pointer rounded"
                    style={{ accentColor: '#3b82f6' }}
                  />
                </th>
              )}
              <th className="pb-2 pr-4">URL</th>
              <th className="pb-2 pr-4 w-20">code</th>
              <th className="pb-2 pr-4 w-20">阶段</th>
              <th className="pb-2">原因</th>
            </tr>
          </thead>
          <tbody>
            {failedDetails.map((d, i) => (
              <tr key={i} style={{ borderBottom: '1px solid #e5e7eb' }}>
                {canBrowse && (
                  <td className="py-2 pr-2">
                    <input
                      type="checkbox"
                      checked={selected.has(d.url)}
                      onChange={() => toggle(d.url)}
                      className="h-4 w-4 cursor-pointer rounded"
                      style={{ accentColor: '#3b82f6' }}
                    />
                  </td>
                )}
                <td className="break-all py-2 pr-2 text-xs" style={{ color: '#6b7280' }}>
                  {d.url}
                </td>
                <td className="py-2 pr-4" style={{ color: '#ef4444' }}>
                  {d.code}
                </td>
                <td className="py-2 pr-4">
                  {d.stage ? (
                    <span className={STAGE_BADGE[d.stage] || 'badge-gray'}>{d.stage}</span>
                  ) : (
                    '-'
                  )}
                </td>
                <td className="py-2 text-xs" style={{ color: '#6b7280' }}>
                  {d.reason}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
