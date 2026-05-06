'use client';

import { useEffect, useState, useCallback } from 'react';
import { api, ApiError } from '@/lib/api';
import { useToast } from '@/components/ui/Toast';

type AiConfig = {
  provider: string;
  api_key: string;
  base_url: string;
  model: string;
};

const PRESETS: Record<string, { base_url: string; model: string }> = {
  kimi: { base_url: 'https://api.moonshot.cn/v1', model: 'moonshot-v1-32k' },
  openai: { base_url: 'https://api.openai.com/v1', model: 'gpt-4o' },
  deepseek: { base_url: 'https://api.deepseek.com/v1', model: 'deepseek-chat' },
  custom: { base_url: '', model: '' },
};

const PRESET_LABELS: Record<string, string> = {
  kimi: 'Kimi (Moonshot)',
  openai: 'OpenAI',
  deepseek: 'DeepSeek',
  custom: '自定义',
};

export default function SettingsPage() {
type TemplateStatus = {
  exists: boolean;
  filename: string | null;
  uploaded_at: string | null;
};

  const [provider, setProvider] = useState('kimi');
  const [apiKey, setApiKey] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [model, setModel] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);
  const [testOk, setTestOk] = useState<boolean | null>(null);
  const [saved, setSaved] = useState(false);
  const [template, setTemplate] = useState<TemplateStatus | null>(null);
  const [uploading, setUploading] = useState(false);
  const [categoryLabels, setCategoryLabels] = useState<string[]>([]);
  const [categoryInput, setCategoryInput] = useState('');
  const [savingCategories, setSavingCategories] = useState(false);
  const { toast } = useToast();

  const fetchConfig = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.get<AiConfig>('/api/v1/admin/settings/ai');
      setProvider(data.provider || 'kimi');
      setApiKey(''); // 不回填 key，用户需重新输入
      setBaseUrl(data.base_url || '');
      setModel(data.model || '');
    } catch {
      // ignore
    }
  }, []);

  const fetchTemplate = useCallback(async () => {
    try {
      const data = await api.get<TemplateStatus>('/api/v1/admin/settings/export-template');
      setTemplate(data);
    } catch {
      // ignore
    }
  }, []);

  const fetchCategoryLabels = useCallback(async () => {
    try {
      const data = await api.get<{ labels: string[] }>('/api/v1/admin/settings/category-labels');
      setCategoryLabels(data.labels || []);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    fetchConfig();
    fetchTemplate();
    fetchCategoryLabels();
  }, [fetchConfig, fetchTemplate, fetchCategoryLabels]);

  function applyPreset(key: string) {
    setProvider(key);
    const p = PRESETS[key];
    if (p) {
      setBaseUrl(p.base_url);
      setModel(p.model);
    }
  }

  async function handleSave() {
    if (!apiKey.trim() || !baseUrl.trim() || !model.trim()) return;
    setSaving(true);
    setSaved(false);
    try {
      await api.put('/api/v1/admin/settings/ai', {
        provider,
        api_key: apiKey.trim(),
        base_url: baseUrl.trim(),
        model: model.trim(),
      });
      setSaved(true);
      setApiKey('');
      setTimeout(() => setSaved(false), 3000);
    } catch (e: unknown) {
      toast(e instanceof ApiError ? e.message : '保存失败', 'error');
    } finally {
      setSaving(false);
    }
  }

  async function handleTest() {
    setTesting(true);
    setTestResult(null);
    setTestOk(null);
    try {
      const data = await api.post<{ model: string; reply: string }>('/api/v1/admin/settings/ai/test', {});
      setTestOk(true);
      setTestResult(`模型 ${data.model} 响应正常：${data.reply}`);
    } catch (e: unknown) {
      setTestOk(false);
      setTestResult(e instanceof ApiError ? e.message : '测试失败');
    } finally {
      setTesting(false);
    }
  }

  async function handleTemplateUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.docx')) {
      toast('仅支持 .docx 文件', 'error');
      return;
    }
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      await api.upload('/api/v1/admin/settings/export-template', formData);
      toast('模板上传成功', 'success');
      fetchTemplate();
    } catch (err: unknown) {
      toast(err instanceof ApiError ? err.message : '上传失败', 'error');
    } finally {
      setUploading(false);
      // 清空 input 以允许重新选择同一文件
      e.target.value = '';
    }
  }

  async function handleDeleteTemplate() {
    try {
      await api.delete('/api/v1/admin/settings/export-template');
      toast('模板已删除', 'success');
      fetchTemplate();
    } catch (err: unknown) {
      toast(err instanceof ApiError ? err.message : '删除失败', 'error');
    }
  }

  async function handleSaveCategoryLabels() {
    if (categoryLabels.length === 0) {
      toast('至少需要保留 1 个分类标签', 'error');
      return;
    }
    setSavingCategories(true);
    try {
      await api.put('/api/v1/admin/settings/category-labels', { labels: categoryLabels });
      toast('分类标签已保存', 'success');
    } catch (err: unknown) {
      toast(err instanceof ApiError ? err.message : '保存失败', 'error');
    } finally {
      setSavingCategories(false);
    }
  }

  function handleAddCategory() {
    const text = categoryInput.trim();
    if (!text) return;
    if (categoryLabels.includes(text)) {
      toast('该标签已存在', 'error');
      return;
    }
    setCategoryLabels([...categoryLabels, text]);
    setCategoryInput('');
  }

  function handleRemoveCategory(index: number) {
    setCategoryLabels(categoryLabels.filter((_, i) => i !== index));
  }

  if (loading) {
    return (
      <main className="min-h-screen p-8 animate-fade-in">
        <p className="text-sm" style={{ color: '#9ca3af' }}>加载中…</p>
      </main>
    );
  }

  return (
    <main className="min-h-screen p-8 animate-fade-in">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold" style={{ color: '#18181b' }}>系统设置</h1>
        <p className="mt-1.5 text-sm" style={{ color: '#9ca3af' }}>管理 AI 模型等系统配置</p>
      </div>

      {/* AI 模型配置 */}
      <div className="card p-6" style={{ maxWidth: 640 }}>
        <h2 className="text-base font-medium mb-5" style={{ color: '#18181b' }}>AI 模型配置</h2>

        {/* 预设按钮 */}
        <div className="mb-5">
          <label className="block text-xs mb-2" style={{ color: '#9ca3af' }}>快速选择</label>
          <div className="flex gap-2 flex-wrap">
            {Object.entries(PRESET_LABELS).map(([key, label]) => (
              <button
                key={key}
                onClick={() => applyPreset(key)}
                className="px-3 py-1.5 text-xs rounded-lg transition-colors"
                style={{
                  background: provider === key ? '#EEF2FF' : '#f4f4f5',
                  color: provider === key ? '#3b82f6' : '#6b7280',
                  border: provider === key ? '1px solid #93c5fd' : '1px solid transparent',
                }}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-4">
          <div>
            <label className="block text-xs mb-1" style={{ color: '#9ca3af' }}>API Key</label>
            <input
              type="password"
              value={apiKey}
              onChange={e => setApiKey(e.target.value)}
              className="input"
              placeholder="输入 API Key（保存后生效）"
            />
            <p className="mt-1 text-xs" style={{ color: '#d1d5db' }}>已配置的 Key 已脱敏显示，留空则不修改</p>
          </div>
          <div>
            <label className="block text-xs mb-1" style={{ color: '#9ca3af' }}>Base URL</label>
            <input
              value={baseUrl}
              onChange={e => setBaseUrl(e.target.value)}
              className="input"
              placeholder="https://api.moonshot.cn/v1"
            />
          </div>
          <div>
            <label className="block text-xs mb-1" style={{ color: '#9ca3af' }}>Model</label>
            <input
              value={model}
              onChange={e => setModel(e.target.value)}
              className="input"
              placeholder="moonshot-v1-32k"
            />
          </div>
        </div>

        <div className="mt-6 flex items-center gap-3">
          <button onClick={handleSave} disabled={saving} className="btn-primary">
            {saving ? '保存中…' : '保存'}
          </button>
          <button onClick={handleTest} disabled={testing} className="btn-secondary">
            {testing ? '测试中…' : '测试连接'}
          </button>
          {saved && (
            <span className="text-xs" style={{ color: '#22c55e' }}>已保存</span>
          )}
        </div>

        {testResult && (
          <div
            className="mt-4 rounded-lg px-4 py-3 text-xs"
            style={{
              background: testOk ? '#f0fdf4' : '#fef2f2',
              color: testOk ? '#16a34a' : '#dc2626',
            }}
          >
            {testResult}
          </div>
        )}

        <div className="mt-6 rounded-lg px-4 py-3 text-xs" style={{ background: '#f9fafb', color: '#9ca3af' }}>
          <p className="font-medium mb-1" style={{ color: '#6b7280' }}>支持的模型</p>
          <p>所有兼容 OpenAI Chat Completions API 的模型均可使用，包括 Kimi (Moonshot)、OpenAI、DeepSeek、通义千问等。</p>
        </div>
      </div>

      {/* 导出模板配置 */}
      <div className="card p-6 mt-6" style={{ maxWidth: 640 }}>
        <h2 className="text-base font-medium mb-5" style={{ color: '#18181b' }}>导出模板</h2>
        <p className="text-xs mb-4" style={{ color: '#9ca3af' }}>
          上传 Word 模板用于合并导出。模板中可使用 Jinja2 占位符（{'{{'} article.title {'}}'} 等）。
        </p>

        {template?.exists ? (
          <div className="space-y-3">
            <div className="flex items-center gap-3 text-sm" style={{ color: '#18181b' }}>
              <span className="badge-green">已上传</span>
              <span>{template.filename}</span>
              {template.uploaded_at && (
                <span className="text-xs" style={{ color: '#9ca3af' }}>
                  {new Date(template.uploaded_at).toLocaleString()}
                </span>
              )}
            </div>
            <div className="flex items-center gap-3">
              <label className="btn-secondary text-sm cursor-pointer">
                {uploading ? '上传中…' : '替换模板'}
                <input
                  type="file"
                  accept=".docx"
                  className="hidden"
                  onChange={handleTemplateUpload}
                  disabled={uploading}
                />
              </label>
              <button
                onClick={handleDeleteTemplate}
                className="rounded-[20px] px-4 py-1.5 text-sm font-medium transition-all"
                style={{ background: '#ef4444', color: '#fcfcfc' }}
              >
                删除模板
              </button>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-sm" style={{ color: '#9ca3af' }}>尚未上传模板</p>
            <label className="btn-secondary text-sm cursor-pointer">
              {uploading ? '上传中…' : '上传模板'}
              <input
                type="file"
                accept=".docx"
                className="hidden"
                onChange={handleTemplateUpload}
                disabled={uploading}
              />
            </label>
          </div>
        )}
      </div>

      {/* 分类标签配置 */}
      <div className="card p-6 mt-6" style={{ maxWidth: 640 }}>
        <h2 className="text-base font-medium mb-5" style={{ color: '#18181b' }}>分类标签</h2>
        <p className="text-xs mb-4" style={{ color: '#9ca3af' }}>
          AI 文章分类使用的标签列表，修改后对新分析的文章生效。
        </p>

        <div className="flex flex-wrap gap-2 mb-4">
          {categoryLabels.map((label, idx) => (
            <span
              key={idx}
              className="inline-flex items-center gap-1 px-3 py-1 text-sm rounded-lg"
              style={{ background: '#f3f4f6', color: '#374151' }}
            >
              {label}
              <button
                onClick={() => handleRemoveCategory(idx)}
                className="text-xs leading-none"
                style={{ color: '#9ca3af' }}
                title="删除"
              >
                ×
              </button>
            </span>
          ))}
        </div>

        <div className="flex items-center gap-2 mb-4">
          <input
            type="text"
            value={categoryInput}
            onChange={(e) => setCategoryInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleAddCategory(); }}
            className="input flex-1 text-sm"
            placeholder="输入新标签，按回车添加"
          />
          <button onClick={handleAddCategory} className="btn-secondary text-sm">
            添加
          </button>
        </div>

        <button
          onClick={handleSaveCategoryLabels}
          disabled={savingCategories}
          className="btn-primary text-sm"
        >
          {savingCategories ? '保存中…' : '保存标签'}
        </button>
      </div>
    </main>
  );
}
