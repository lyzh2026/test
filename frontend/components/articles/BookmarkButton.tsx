'use client';

import { useState } from 'react';
import { api } from '@/lib/api';

export function BookmarkButton({
  articleId,
  initialBookmarked,
}: {
  articleId: string;
  initialBookmarked: boolean;
}) {
  const [bookmarked, setBookmarked] = useState(initialBookmarked);

  async function handleToggle() {
    const prev = bookmarked;
    setBookmarked((b) => !b);
    try {
      const data = await api.patch<{ bookmarked: boolean }>(`/api/v1/articles/${articleId}/bookmark`);
      setBookmarked(data.bookmarked);
    } catch {
      setBookmarked(prev);
    }
  }

  return (
    <button
      onClick={handleToggle}
      className={`inline-flex items-center gap-1 text-sm transition-colors flex-shrink-0 ${
        bookmarked ? 'text-accent-amber' : 'text-text-muted hover:text-accent-amber'
      }`}
      title={bookmarked ? '取消收藏' : '收藏'}
    >
      <svg className="h-5 w-5" fill={bookmarked ? 'currentColor' : 'none'} stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M11.48 3.499a.562.562 0 0 1 1.04 0l2.125 5.111a.563.563 0 0 0 .475.345l5.518.442c.499.04.701.663.321.988l-4.204 3.602a.563.563 0 0 0-.182.557l1.285 5.385a.562.562 0 0 1-.84.61l-4.725-2.885a.562.562 0 0 0-.586 0L6.982 20.54a.562.562 0 0 1-.84-.61l1.285-5.386a.562.562 0 0 0-.182-.557l-4.204-3.602a.562.562 0 0 1 .321-.988l5.518-.442a.563.563 0 0 0 .475-.345L11.48 3.5Z" />
      </svg>
    </button>
  );
}
