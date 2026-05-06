'use client';

import { downloadWithPicker } from '@/lib/download';

export function ExportDocButton({ articleId, compact, filename }: { articleId: string; compact?: boolean; filename?: string }) {
  const href = `/api/proxy/api/v1/articles/${articleId}/export/doc`;
  const defaultName = filename || `文章_${articleId.slice(0, 8)}.doc`;

  async function handleClick(e: React.MouseEvent) {
    e.preventDefault();
    await downloadWithPicker(href, defaultName);
  }

  if (compact) {
    return (
      <button
        onClick={handleClick}
        className="text-sm transition-colors"
        style={{ color: '#6b7280' }}
        title="导出文档"
      >
        导出
      </button>
    );
  }

  return (
    <button onClick={handleClick} className="btn-secondary">
      导出文档
    </button>
  );
}

export async function batchExportDoc(articleIds: string[]) {
  const { downloadWithPicker } = await import('@/lib/download');
  for (const id of articleIds) {
    await downloadWithPicker(
      `/api/proxy/api/v1/articles/${id}/export/doc`,
      `文章_${id.slice(0, 8)}.doc`,
    );
    // 间隔避免浏览器阻止批量下载
    await new Promise((r) => setTimeout(r, 300));
  }
}
