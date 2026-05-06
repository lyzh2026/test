'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { useToast } from '@/components/ui/Toast';

export function ReanalyzeButton({ articleId, status }: { articleId: string; status: string }) {
  const [loading, setLoading] = useState(false);
  const router = useRouter();
  const { toast, confirm } = useToast();

  if (status !== 'failed_retryable' && status !== 'failed_permanent') return null;

  async function handleReanalyze() {
    if (!await confirm('确认重新分析此文章？')) return;
    setLoading(true);
    try {
      await api.post(`/api/v1/articles/${articleId}/reanalyze`);
      router.refresh();
    } catch (e: unknown) {
      toast(e instanceof Error ? e.message : '重新分析失败', 'error');
    } finally {
      setLoading(false);
    }
  }

  return (
    <button
      onClick={handleReanalyze}
      disabled={loading}
      className="btn-primary text-xs disabled:opacity-50"
      style={{ background: '#bc8cff' }}
    >
      {loading ? '分析中…' : '重新分析'}
    </button>
  );
}
