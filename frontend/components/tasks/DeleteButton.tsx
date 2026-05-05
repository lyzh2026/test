'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';

export function DeleteButton({ taskId }: { taskId: string }) {
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  async function handleDelete() {
    if (!confirm('确认删除此任务？此操作不可撤销。')) return;
    setLoading(true);
    try {
      await api.post(`/api/v1/crawler/task/${taskId}/cancel`).catch(() => {});
      await api.delete(`/api/v1/crawler/task/${taskId}`);
      router.push('/tasks');
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : '删除失败');
    } finally {
      setLoading(false);
    }
  }

  return (
    <button
      onClick={handleDelete}
      disabled={loading}
      className="rounded-md px-3 py-1.5 text-xs font-medium transition-all duration-150 disabled:opacity-50"
      style={{ background: 'rgba(228, 90, 90, 0.1)', color: '#e45a5a' }}
    >
      {loading ? '删除中…' : '删除任务'}
    </button>
  );
}
