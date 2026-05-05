'use client';

import { useState, useEffect } from 'react';
import { api, ApiError } from '@/lib/api';

type DistConfig = {
  id: string;
  name: string;
  config: { to_addrs?: string[] };
};

export function EmailSendButton({ articleId, compact, onDone }: { articleId: string; compact?: boolean; onDone?: () => void }) {
  const [configs, setConfigs] = useState<DistConfig[]>([]);
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [showPicker, setShowPicker] = useState(false);

  useEffect(() => {
    api.get<{ items: DistConfig[] }>('/api/v1/distribution/configs/email-enabled')
      .then(d => setConfigs(d.items))
      .catch(() => {});
  }, []);

  async function handleSend(cfg: DistConfig) {
    setSending(true);
    try {
      await api.post(`/api/v1/distribution/send-article/${articleId}`, { config_id: cfg.id });
      setShowPicker(false);
      alert(`已发送至 ${cfg.config.to_addrs?.join(', ') || cfg.name}`);
      onDone?.();
    } catch (e: unknown) {
      alert(e instanceof ApiError ? e.message : '发送失败');
    } finally {
      setSending(false);
    }
  }

  return (
    <>
      <button onClick={() => setShowPicker(true)} disabled={loading || configs.length === 0} className={compact ? 'text-sm transition-colors' : 'btn-secondary'} style={compact ? { color: '#6b8cff' } : undefined}>
        {loading ? '加载中…' : '邮件发送'}
      </button>

      {showPicker && (
        <div className="fixed inset-0 z-50 flex items-center justify-center animate-fade-in" style={{ background: 'rgba(0,0,0,0.6)' }} onClick={() => setShowPicker(false)}>
          <div className="w-96 card p-6 animate-slide-up" style={{ background: '#0f1117' }} onClick={e => e.stopPropagation()}>
            <h2 className="mb-1 text-base font-medium" style={{ color: '#e8e9ed' }}>选择发送通道</h2>
            <p className="mb-5 text-xs" style={{ color: '#6b6d7b' }}>选择要通过哪个邮件通道发送此文章</p>
            <div className="space-y-2">
              {configs.map(cfg => (
                <button
                  key={cfg.id}
                  onClick={() => handleSend(cfg)}
                  disabled={sending}
                  className="w-full rounded-[12px] p-4 text-left transition-all hover:bg-surface-50"
                  style={{ background: '#181b25', border: '1px solid #262933' }}
                >
                  <div className="text-sm font-medium" style={{ color: '#e8e9ed' }}>{cfg.name}</div>
                  <div className="mt-1 text-xs" style={{ color: '#6b6d7b' }}>
                    发送至：{cfg.config.to_addrs?.join(', ') || '未配置收件人'}
                  </div>
                </button>
              ))}
            </div>
            <div className="mt-4 flex justify-end">
              <button onClick={() => setShowPicker(false)} className="btn-secondary text-sm" disabled={sending}>取消</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
