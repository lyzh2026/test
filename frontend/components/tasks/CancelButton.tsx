'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';

export function CancelButton({ taskId, status }: { taskId: string; status: string }) {
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  if (status !== 'running' && status !== 'pending') return null;

  async function handleCancel() {
    if (!confirm('确认取消此任务？')) return;
    setLoading(true);
    try {
      await api.post(`/api/v1/crawler/task/${taskId}/cancel`);
      router.refresh();
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : '取消失败');
    } finally {
      setLoading(false);
    }
  }

  return (
    <button
      onClick={handleCancel}
      disabled={loading}
      className="rounded-md px-3 py-1.5 text-xs font-medium transition-all duration-150 disabled:opacity-50"
      style={{ background: 'rgba(239, 68, 68, 0.1)', color: '#ef4444' }}
    >
      {loading ? '取消中…' : '取消任务'}
    </button>
  );
}
