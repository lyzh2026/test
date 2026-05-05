'use client';

export function ExportDocButton({ articleId, compact }: { articleId: string; compact?: boolean }) {
  const href = `/api/proxy/api/v1/articles/${articleId}/export/doc`;

  if (compact) {
    return (
      <a
        href={href}
        download
        className="text-sm transition-colors"
        style={{ color: '#6b7280' }}
        title="导出文档"
      >
        导出
      </a>
    );
  }

  return (
    <a href={href} download className="btn-secondary">
      导出文档
    </a>
  );
}

export async function batchExportDoc(articleIds: string[]) {
  for (const id of articleIds) {
    const a = document.createElement('a');
    a.href = `/api/proxy/api/v1/articles/${id}/export/doc`;
    a.download = '';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    // 间隔避免浏览器阻止批量下载
    await new Promise((r) => setTimeout(r, 300));
  }
}
