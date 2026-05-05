'use client';

import { useEffect, useState, useCallback } from 'react';
import { api, ApiError } from '@/lib/api';

type AllowItem = {
  id: string;
  domain_pattern: string;
  match_mode: string;
  enabled: boolean;
  auto_added: boolean;
  source: string;
  remark: string | null;
  created_at: string | null;
};

export default function AllowlistPage() {
  const [items, setItems] = useState<AllowItem[]>([]);
  const [loading, setLoading] = useState(true);

  const [formOpen, setFormOpen] = useState(false);
  const [editId, setEditId] = useState<string | null>(null);
  const [formPattern, setFormPattern] = useState('');
  const [formMode, setFormMode] = useState('exact');
  const [formEnabled, setFormEnabled] = useState(true);
  const [formRemark, setFormRemark] = useState('');

  const fetchList = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.get<{ items: AllowItem[] }>('/api/v1/admin/allowlist');
      setItems(data.items);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchList(); }, [fetchList]);

  function openNew() {
    setEditId(null);
    setFormPattern('');
    setFormMode('exact');
    setFormEnabled(true);
    setFormRemark('');
    setFormOpen(true);
  }

  function openEdit(item: AllowItem) {
    setEditId(item.id);
    setFormPattern(item.domain_pattern);
    setFormMode(item.match_mode);
    setFormEnabled(item.enabled);
    setFormRemark(item.remark || '');
    setFormOpen(true);
  }

  async function handleSave() {
    if (!formPattern.trim()) return;
    try {
      if (editId) {
        await api.put(`/api/v1/admin/allowlist/${editId}`, {
          domain_pattern: formPattern.trim(),
          match_mode: formMode,
          enabled: formEnabled,
          remark: formRemark.trim(),
        });
      } else {
        await api.post('/api/v1/admin/allowlist', {
          domain_pattern: formPattern.trim(),
          match_mode: formMode,
          enabled: formEnabled,
          remark: formRemark.trim(),
        });
      }
      setFormOpen(false);
      fetchList();
    } catch (e: unknown) {
      alert(e instanceof ApiError ? e.message : '保存失败');
    }
  }

  async function handleDelete(id: string) {
    if (!confirm('确认删除此白名单条目？')) return;
    try {
      await api.delete(`/api/v1/admin/allowlist/${id}`);
      fetchList();
    } catch (e: unknown) {
      alert(e instanceof ApiError ? e.message : '删除失败');
    }
  }

  return (
    <main className="min-h-screen p-8 animate-fade-in">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold" style={{ color: '#18181b' }}>域名白名单</h1>
          <p className="mt-1.5 text-sm" style={{ color: '#9ca3af' }}>管理允许采集的域名</p>
        </div>
        <button onClick={openNew} className="btn-primary">
          新增
        </button>
      </div>

      {loading ? (
        <p className="text-sm" style={{ color: '#9ca3af' }}>加载中…</p>
      ) : items.length === 0 ? (
        <div className="card p-8 text-center text-sm" style={{ color: '#9ca3af' }}>暂无白名单条目</div>
      ) : (
        <div className="card overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr style={{ borderBottom: '1px solid #e5e7eb' }}>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider" style={{ color: '#9ca3af' }}>域名</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider" style={{ color: '#9ca3af' }}>匹配模式</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider" style={{ color: '#9ca3af' }}>状态</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider" style={{ color: '#9ca3af' }}>来源</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider" style={{ color: '#9ca3af' }}>备注</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider" style={{ color: '#9ca3af' }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id} className="transition-colors duration-150 hover:bg-surface-50" style={{ borderBottom: '1px solid #e5e7eb' }}>
                  <td className="px-4 py-3 font-mono text-xs" style={{ color: '#18181b' }}>{item.domain_pattern}</td>
                  <td className="px-4 py-3 text-xs" style={{ color: '#6b7280' }}>{item.match_mode}</td>
                  <td className="px-4 py-3">
                    <span className={item.enabled ? 'badge-green' : 'badge-gray'}>
                      {item.enabled ? '启用' : '禁用'}
                    </span>
                    {item.auto_added && <span className="ml-1 badge-blue">自动</span>}
                  </td>
                  <td className="px-4 py-3 text-xs" style={{ color: '#6b7280' }}>{item.source}</td>
                  <td className="px-4 py-3 text-xs" style={{ color: '#9ca3af' }}>{item.remark || '-'}</td>
                  <td className="px-4 py-3">
                    <button onClick={() => openEdit(item)} className="text-xs transition-colors mr-3" style={{ color: '#6b7280' }}>编辑</button>
                    <button onClick={() => handleDelete(item.id)} className="text-xs" style={{ color: '#ef4444' }}>删除</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {formOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center animate-fade-in" style={{ background: 'rgba(0,0,0,0.6)' }}>
          <div className="w-full max-w-md card p-6 animate-slide-up" style={{ background: '#fcfcfc' }}>
            <h2 className="mb-5 text-base font-medium" style={{ color: '#18181b' }}>{editId ? '编辑' : '新增'}白名单</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-xs mb-1" style={{ color: '#9ca3af' }}>域名</label>
                <input value={formPattern} onChange={e => setFormPattern(e.target.value)} className="input" placeholder="example.gov.cn" />
              </div>
              <div>
                <label className="block text-xs mb-1" style={{ color: '#9ca3af' }}>匹配模式</label>
                <select value={formMode} onChange={e => setFormMode(e.target.value)} className="input">
                  <option value="exact">精确匹配 (exact)</option>
                  <option value="suffix">后缀匹配 (suffix)</option>
                  <option value="regex">正则匹配 (regex)</option>
                </select>
              </div>
              <label className="flex items-center gap-2 text-sm cursor-pointer" style={{ color: '#6b7280' }}>
                <input type="checkbox" checked={formEnabled} onChange={e => setFormEnabled(e.target.checked)} className="rounded" style={{ accentColor: '#3b82f6' }} />
                启用
              </label>
              <div>
                <label className="block text-xs mb-1" style={{ color: '#9ca3af' }}>备注</label>
                <input value={formRemark} onChange={e => setFormRemark(e.target.value)} className="input" placeholder="可选备注" />
              </div>
            </div>
            <div className="mt-6 flex justify-end gap-3">
              <button onClick={() => setFormOpen(false)} className="btn-secondary">取消</button>
              <button onClick={handleSave} className="btn-primary">保存</button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
