'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { useToast } from '@/components/ui/Toast';

export function DeleteButton({ taskId }: { taskId: string }) {
  const [loading, setLoading] = useState(false);
  const router = useRouter();
  const { toast, confirm } = useToast();

  async function handleDelete() {
    if (!await confirm('确认删除此任务？此操作不可撤销。')) return;
    setLoading(true);
    try {
      await api.post(`/api/v1/crawler/task/${taskId}/cancel`).catch(() => {});
      await api.delete(`/api/v1/crawler/task/${taskId}`);
      router.push('/tasks');
    } catch (e: unknown) {
      toast(e instanceof Error ? e.message : '删除失败', 'error');
    } finally {
      setLoading(false);
    }
  }

  return (
    <button
      onClick={handleDelete}
      disabled={loading}
      className="rounded-md px-3 py-1.5 text-xs font-medium transition-all duration-150 disabled:opacity-50"
      style={{ background: 'rgba(239, 68, 68, 0.1)', color: '#ef4444' }}
    >
      {loading ? '删除中…' : '删除任务'}
    </button>
  );
}
