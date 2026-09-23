'use client';

import { useCallback, useEffect, useState } from 'react';
import { api, ApiError } from '@/lib/api';
import { useToast } from '@/components/ui/Toast';

type Draft = { title: string; body: string; template: string; version: number };

export default function DraftEditor({ articleId }: { articleId: string }) {
  const [draft, setDraft] = useState<Draft | null>(null);
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const { toast } = useToast();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const d = await api.get<Draft>(`/api/v1/wechat/draft/${articleId}`);
      setDraft(d);
      setTitle(d.title);
      setBody(d.body);
    } catch (e: unknown) {
      toast(e instanceof ApiError ? e.message : '草稿加载失败', 'error');
    } finally {
      setLoading(false);
    }
  }, [articleId, toast]);

  useEffect(() => {
    load();
  }, [load]);

  const dirty = draft !== null && (title !== draft.title || body !== draft.body);

  async function handleSave() {
    setSaving(true);
    try {
      const d = await api.put<Draft>(`/api/v1/wechat/draft/${articleId}`, {
        title,
        body,
        template: draft?.template || 'green-simple',
      });
      setDraft(d);
      toast(`已保存为 v${d.version}`, 'success');
      // 延迟刷新：立刻 reload 会抢在 toast 首次绘制之前卸载页面，用户看不到保存反馈
      setTimeout(() => window.location.reload(), 500);
    } catch (e: unknown) {
      toast(e instanceof ApiError ? e.message : '保存失败', 'error');
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <div className="card p-4 text-xs" style={{ color: '#9ca3af' }}>草稿加载中…</div>;
  }

  return (
    <div className="card p-4">
      <div className="mb-3 flex items-center justify-between">
        <span className="text-sm font-medium" style={{ color: '#18181b' }}>
          推文草稿 {draft && <span className="text-xs" style={{ color: '#9ca3af' }}>v{draft.version}</span>}
        </span>
        <button
          onClick={handleSave}
          disabled={saving || !dirty}
          className="btn-primary text-xs disabled:opacity-40"
        >
          {saving ? '保存中…' : '保存为新版本'}
        </button>
      </div>

      <label className="mb-1 block text-xs" style={{ color: '#6b7280' }}>标题</label>
      <input
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        className="mb-3 w-full rounded-md px-3 py-2 text-sm"
        style={{ border: '1px solid #e5e7eb', color: '#18181b' }}
      />

      <label className="mb-1 block text-xs" style={{ color: '#6b7280' }}>正文（Markdown，空行分段）</label>
      <textarea
        value={body}
        onChange={(e) => setBody(e.target.value)}
        rows={16}
        className="w-full rounded-md px-3 py-2 text-sm font-mono"
        style={{ border: '1px solid #e5e7eb', color: '#18181b' }}
      />

      <p className="mt-2 text-xs" style={{ color: '#9ca3af' }}>
        每次保存都会写入新版本，不覆盖历史；保存后上方预览会重新渲染最新版本。
      </p>
    </div>
  );
}
