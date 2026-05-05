'use client';

import { useState, useCallback } from 'react';

type TemplateInfo = { key: string; label: string };

const TEMPLATES: TemplateInfo[] = [
  { key: 'green-simple', label: '绿色简洁' },
  { key: 'clean-white', label: '洁白素雅' },
];

interface Props {
  articleId: string;
  articleTitle: string;
  initialHtml: string;
  initialTemplate: string;
}

export default function WeChatPreview({
  articleId,
  articleTitle,
  initialHtml,
  initialTemplate,
}: Props) {
  const [selectedTemplate, setSelectedTemplate] = useState(initialTemplate);
  const [html, setHtml] = useState(initialHtml);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState('');

  const switchTemplate = useCallback(
    async (key: string) => {
      if (key === selectedTemplate) return;
      setSelectedTemplate(key);
      setLoading(true);
      setError('');
      try {
        const res = await fetch(`/api/proxy/api/v1/wechat/format/${articleId}?template=${key}`);
        const body = await res.json();
        if (body.code !== 0) {
          throw new Error(body.message || '请求失败');
        }
        setHtml(body.data.html);
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : '切换模板失败';
        setError(msg);
        setSelectedTemplate(selectedTemplate); // revert
      } finally {
        setLoading(false);
      }
    },
    [articleId, selectedTemplate],
  );

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(html);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      const textarea = document.createElement('textarea');
      textarea.value = html;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }, [html]);

  return (
    <div>
      {/* Template selector */}
      <div className="mb-6 flex items-center gap-3">
        <span className="text-sm text-text-secondary">排版模板：</span>
        <div className="flex gap-2">
          {TEMPLATES.map((t) => (
            <button
              key={t.key}
              onClick={() => switchTemplate(t.key)}
              disabled={loading}
              className={selectedTemplate === t.key ? 'btn-primary text-xs' : 'btn-secondary text-xs'}
            >
              {t.label}
            </button>
          ))}
        </div>
        {loading && <span className="text-xs text-text-muted">AI 生成中...</span>}
      </div>

      {error && (
        <div className="mb-4 rounded-md px-4 py-2 text-sm" style={{ background: 'rgba(228, 90, 90, 0.08)', color: '#e45a5a' }}>
          {error}
        </div>
      )}

      {/* Phone frame */}
      <div className="flex justify-center">
        <div className="w-[375px] overflow-hidden rounded-[40px] shadow-elevated" style={{ border: '4px solid #2f2f35' }}>
          {/* Notch */}
          <div className="flex h-9 items-center justify-center" style={{ background: '#1a1a1e' }}>
            <div className="h-2.5 w-24 rounded-full" style={{ background: '#2f2f35' }} />
          </div>
          {/* Screen content */}
          <div className="h-[600px] overflow-y-auto bg-white px-4 py-4" style={{ scrollbarWidth: 'thin' }}>
            <div className="max-w-full" dangerouslySetInnerHTML={{ __html: html }} />
          </div>
          {/* Home indicator */}
          <div className="flex h-6 items-center justify-center" style={{ background: '#1a1a1e' }}>
            <div className="h-1 w-32 rounded-full" style={{ background: '#2f2f35' }} />
          </div>
        </div>
      </div>

      {/* Action buttons */}
      <div className="mt-6 flex items-center justify-center gap-4">
        <button onClick={handleCopy} className="btn-primary">
          {copied ? '已复制' : '复制 HTML'}
        </button>
        <a
          href={`/api/proxy/api/v1/wechat/export/html/${articleId}?template=${selectedTemplate}`}
          download
          className="btn-secondary"
        >
          下载 HTML
        </a>
      </div>
    </div>
  );
}
