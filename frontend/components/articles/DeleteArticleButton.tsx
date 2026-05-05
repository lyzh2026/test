'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';

export function DeleteArticleButton({ articleId, redirectTo }: { articleId: string; redirectTo?: string }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState('');

  const handleDelete = async () => {
    setDeleting(true);
    setError('');
    try {
      await api.delete(`/api/v1/articles/${articleId}`);
      setOpen(false);
      if (redirectTo) {
        router.push(redirectTo);
      } else {
        router.refresh();
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '删除失败');
      setDeleting(false);
    }
  };

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="text-sm transition-colors"
        style={{ color: '#e45a5a' }}
      >
        删除
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center" onClick={() => setOpen(false)}>
          <div className="absolute inset-0 bg-black/20" />
          <div
            className="relative rounded-[16px] p-6 w-80"
            style={{ background: '#0f1117', border: '1px solid #262933' }}
            onClick={(e) => e.stopPropagation()}
          >
            <p className="text-sm font-medium" style={{ color: '#e8e9ed' }}>确认删除</p>
            <p className="text-sm mt-1 mb-5" style={{ color: '#6b6d7b' }}>删除后不可恢复，确定要删除这篇文章吗？</p>
            {error && (
              <p className="mb-4 text-sm" style={{ color: '#e45a5a' }}>{error}</p>
            )}
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setOpen(false)}
                className="btn-secondary text-sm"
                disabled={deleting}
              >
                取消
              </button>
              <button
                onClick={handleDelete}
                className="rounded-[20px] px-4 py-1.5 text-sm font-medium transition-all"
                style={{ background: '#e45a5a', color: '#0f1117' }}
                disabled={deleting}
              >
                {deleting ? '删除中…' : '确认删除'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
