'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { useToast } from '@/components/ui/Toast';

export function RetryButton({ taskId, status }: { taskId: string; status: string }) {
  const [loading, setLoading] = useState(false);
  const router = useRouter();
  const { toast, confirm } = useToast();

  if (status !== 'partial_failed' && status !== 'failed') return null;

  async function handleRetry() {
    if (!await confirm('确认重试该任务的所有失败 URL？')) return;
    setLoading(true);
    try {
      await api.post(`/api/v1/crawler/task/${taskId}/retry`);
      router.refresh();
    } catch (e: unknown) {
      toast(e instanceof Error ? e.message : '重试失败', 'error');
    } finally {
      setLoading(false);
    }
  }

  return (
    <button
      onClick={handleRetry}
      disabled={loading}
      className="rounded-md px-3 py-1.5 text-xs font-medium transition-all duration-150 disabled:opacity-50"
      style={{ background: 'rgba(245, 158, 11, 0.1)', color: '#f59e0b' }}
    >
      {loading ? '重试中…' : '重试失败项'}
    </button>
  );
}
