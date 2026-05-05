'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { api, ApiError } from '@/lib/api';
import { EmailSendButton } from '@/components/articles/EmailSendButton';

type ArticleItem = {
  id: string;
  task_id: string | null;
  original_title: string;
  source_unit: string | null;
  original_link: string;
  publish_date: string | null;
  status: string;
  bookmarked: boolean;
  ai: { categories: { label: string; confidence: number }[]; summary: string; keywords: string[] };
  created_at: string;
};

export function ArticleListClient({ items, total, limit, offset, prevHref, nextHref }: {
  items: ArticleItem[];
  total: number;
  limit: number;
  offset: number;
  prevHref: string;
  nextHref: string;
}) {
  const router = useRouter();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState('');

  function toggle(id: string) {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelected(next);
  }

  function toggleAll() {
    if (selected.size === items.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(items.map((a) => a.id)));
    }
  }

  async function handleBatchDelete() {
    setDeleting(true);
    setError('');
    try {
      await api.post('/api/v1/articles/batch-delete', { article_ids: Array.from(selected) });
      setSelected(new Set());
      setConfirmOpen(false);
      setDeleting(false);
      router.refresh();
    } catch (err) {
      const e = err as ApiError;
      setError(`删除失败 (${e.code}): ${e.message}`);
      setDeleting(false);
    }
  }

  async function toggleBookmark(articleId: string, current: boolean) {
    try {
      await api.patch(`/api/v1/articles/${articleId}/bookmark`);
      router.refresh();
    } catch { }
  }

  async function deleteSingle(articleId: string) {
    try {
      await api.delete(`/api/v1/articles/${articleId}`);
      router.refresh();
    } catch { }
  }

  return (
    <>
      {/* Batch action bar */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm" style={{ color: '#a8abb8' }} cursor-pointer>
            <input
              type="checkbox"
              checked={selected.size === items.length && items.length > 0}
              onChange={toggleAll}
              style={{ accentColor: '#6b8cff' }}
            />
            全选
          </label>
          <span className="text-sm" style={{ color: '#6b6d7b' }}>共 {total} 条</span>
        </div>
        <div className="flex items-center gap-4">
          {selected.size > 0 && (
            <span className="text-sm" style={{ color: '#6b6d7b' }}>已选 {selected.size} 条</span>
          )}
          <button
            onClick={() => setConfirmOpen(true)}
            disabled={selected.size === 0}
            className="rounded-[20px] px-4 py-1.5 text-sm font-medium transition-all disabled:opacity-30"
            style={{ background: '#e45a5a', color: '#0f1117' }}
          >
            批量删除
          </button>
        </div>
      </div>

      <div className="space-y-3">
        {items.length === 0 && (
          <div className="card p-8 text-center text-sm" style={{ color: '#6b6d7b' }}>
            没有符合条件的文章
          </div>
        )}
        {items.map((a) => (
          <article key={a.id} className="card p-5 card-hover transition-all duration-200 animate-slide-up">
            <div className="mb-3 flex items-center gap-2 text-xs" style={{ color: '#6b6d7b' }}>
              <input
                type="checkbox"
                checked={selected.has(a.id)}
                onChange={() => toggle(a.id)}
                style={{ accentColor: '#6b8cff' }}
              />
              <span>{a.publish_date || '日期未识别'}</span>
              <span className="opacity-30">·</span>
              <span>{a.source_unit || '来源未识别'}</span>
              <span className={STATUS_STYLE[a.status] || 'badge-gray'}>{STATUS_LABEL[a.status] || a.status}</span>
            </div>
            <div className="mb-2 flex items-start gap-3">
              <h2 className="text-base font-medium flex-1">
                <a href={`/articles/${a.id}`} className="transition-opacity" style={{ color: '#e8e9ed' }}>
                  {a.original_title}
                </a>
              </h2>
              <button
                onClick={() => toggleBookmark(a.id, a.bookmarked)}
                className="text-lg transition-colors leading-none"
                style={{ color: a.bookmarked ? '#d4a84a' : '#33364a' }}
                title={a.bookmarked ? '取消收藏' : '收藏'}
              >
                {a.bookmarked ? '★' : '☆'}
              </button>
              <EmailSendButton articleId={a.id} compact />
              <button
                onClick={() => deleteSingle(a.id)}
                className="text-sm transition-colors"
                style={{ color: '#e45a5a' }}
              >
                删除
              </button>
            </div>
            <div className="flex flex-wrap gap-2">
              {a.ai.categories.map((c) => (
                <span key={c.label} className="badge-green" title={`置信度 ${c.confidence}`}>
                  {c.label}
                </span>
              ))}
              {a.ai.keywords.slice(0, 5).map((k) => (
                <span key={k} className="badge-gray">#{k}</span>
              ))}
            </div>
          </article>
        ))}
      </div>

      {/* Pagination */}
      <div className="mt-8 flex items-center justify-between text-sm">
        <a
          href={prevHref}
          className={`btn-secondary ${offset <= 0 ? 'pointer-events-none opacity-30' : ''}`}
        >
          上一页
        </a>
        <span style={{ color: '#6b6d7b' }}>{offset + 1} - {Math.min(offset + limit, total)}</span>
        <a
          href={nextHref}
          className={`btn-secondary ${offset + limit >= total ? 'pointer-events-none opacity-30' : ''}`}
        >
          下一页
        </a>
      </div>

      {/* Confirmation modal */}
      {confirmOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center" onClick={() => setConfirmOpen(false)}>
          <div className="absolute inset-0 bg-black/20" />
          <div
            className="relative rounded-[16px] p-6 w-80"
            style={{ background: '#0f1117', border: '1px solid #262933' }}
            onClick={(e) => e.stopPropagation()}
          >
            <p className="text-sm font-medium" style={{ color: '#e8e9ed' }}>确认批量删除</p>
            <p className="text-sm mt-1 mb-5" style={{ color: '#6b6d7b' }}>确定删除选中的 {selected.size} 篇文章？删除后不可恢复。</p>
            {error && <p className="mb-4 text-sm" style={{ color: '#e45a5a' }}>{error}</p>}
            <div className="flex justify-end gap-3">
              <button onClick={() => setConfirmOpen(false)} className="btn-secondary text-sm" disabled={deleting}>
                取消
              </button>
              <button
                onClick={handleBatchDelete}
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

const STATUS_LABEL: Record<string, string> = {
  raw: '已抓取',
  analyzing: '分析中',
  processed: '已分析',
  failed_retryable: '分析失败可重试',
  failed_permanent: '分析失败',
};

const STATUS_STYLE: Record<string, string> = {
  raw: 'badge-gray',
  analyzing: 'badge-amber',
  processed: 'badge-green',
  failed_retryable: 'badge-amber',
  failed_permanent: 'badge-red',
};
