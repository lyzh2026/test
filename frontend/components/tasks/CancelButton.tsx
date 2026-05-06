'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { useToast } from '@/components/ui/Toast';

export function CancelButton({ taskId, status }: { taskId: string; status: string }) {
  const [loading, setLoading] = useState(false);
  const router = useRouter();
  const { toast, confirm } = useToast();

  if (status !== 'running' && status !== 'pending') return null;

  async function handleCancel() {
    if (!await confirm('确认取消此任务？')) return;
    setLoading(true);
    try {
      await api.post(`/api/v1/crawler/task/${taskId}/cancel`);
      router.refresh();
    } catch (e: unknown) {
      toast(e instanceof Error ? e.message : '取消失败', 'error');
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
