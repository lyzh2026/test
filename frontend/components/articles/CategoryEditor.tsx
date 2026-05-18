'use client';

import { useEffect, useState } from 'react';
import { api, ApiError } from '@/lib/api';

type Category = { label: string; confidence: number };

export function CategoryEditor({
  articleId,
  initialCategories,
}: {
  articleId: string;
  initialCategories: Category[];
}) {
  const [categories, setCategories] = useState<Category[]>(initialCategories);
  const [allLabels, setAllLabels] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.get<{ labels: string[] }>('/api/v1/articles/category-labels')
      .then((data) => setAllLabels(data.labels || []))
      .catch(() => setAllLabels([]));
  }, []);

  const available = allLabels.filter(
    (l) => !categories.some((c) => c.label === l)
  );

  async function handleAdd(label: string) {
    if (categories.length >= 3) return;
    // "未分类"具有排他性
    if (label === '未分类') {
      setCategories([{ label, confidence: 1.0 }]);
      return;
    }
    // 添加其他标签时移除"未分类"
    const next = categories.filter((c) => c.label !== '未分类');
    setCategories([...next, { label, confidence: 1.0 }]);
  }

  function handleRemove(label: string) {
    setCategories((prev) => prev.filter((c) => c.label !== label));
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      await api.put(`/api/v1/articles/${articleId}/categories`, { categories });
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : '保存失败');
      setSaving(false);
      return;
    }
    setSaving(false);
  }

  return (
    <div className="rounded-[12px] p-4" style={{ background: '#f9fafb' }}>
      <div className="mb-2 flex items-center gap-2">
        <h2 className="text-xs font-semibold uppercase tracking-wider" style={{ color: '#9ca3af' }}>AI 分类</h2>
        {categories.length < 3 && available.length > 0 && (
          <select
            defaultValue=""
            onChange={(e) => {
              if (e.target.value) handleAdd(e.target.value);
              e.target.value = '';
            }}
            className="input text-xs py-1 w-auto"
          >
            <option value="" disabled>+ 添加分类</option>
            {available.map((l) => (
              <option key={l} value={l}>{l}</option>
            ))}
          </select>
        )}
      </div>

      <div className="flex flex-wrap gap-2">
        {categories.map((c) => (
          <span
            key={c.label}
            className="badge-green inline-flex items-center gap-1"
          >
            {c.label}
            <button
              onClick={() => handleRemove(c.label)}
              className="ml-0.5 opacity-60 hover:opacity-100"
            >
              ✕
            </button>
          </span>
        ))}
        {categories.length === 0 && (
          <span className="text-xs text-text-muted">暂无分类</span>
        )}
      </div>

      <div className="mt-3 flex items-center gap-3">
        <button onClick={handleSave} disabled={saving} className="btn-primary text-xs disabled:opacity-50">
          {saving ? '保存中…' : '保存'}
        </button>
        {error && <span className="text-xs" style={{ color: '#ef4444' }}>{error}</span>}
      </div>
    </div>
  );
}
