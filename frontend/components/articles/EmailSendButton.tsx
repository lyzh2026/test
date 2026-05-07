'use client';

import { useState, useEffect } from 'react';
import { api, ApiError } from '@/lib/api';
import { useToast } from '@/components/ui/Toast';

type DistConfig = {
  id: string;
  channel_type: string;
  name: string;
  config: { to_addrs?: string[]; url?: string };
};

const CHANNEL_LABELS: Record<string, string> = {
  email: '邮件',
  webhook: '飞书',
};

export function EmailSendButton({ articleId, compact, onDone }: { articleId: string; compact?: boolean; onDone?: () => void }) {
  const [configs, setConfigs] = useState<DistConfig[]>([]);
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [showPicker, setShowPicker] = useState(false);
  const { toast } = useToast();

  useEffect(() => {
    api.get<{ items: DistConfig[] }>('/api/v1/distribution/configs/enabled')
      .then(d => setConfigs(d.items))
      .catch(() => {});
  }, []);

  async function handleSend(cfg: DistConfig) {
    setSending(true);
    try {
      await api.post(`/api/v1/distribution/send-article/${articleId}`, { config_id: cfg.id });
      setShowPicker(false);
      const target = cfg.channel_type === 'email'
        ? `邮件至 ${cfg.config.to_addrs?.join(', ') || cfg.name}`
        : '飞书';
      toast(`已发送至${target}`, 'success');
      onDone?.();
    } catch (e: unknown) {
      toast(e instanceof ApiError ? e.message : '发送失败', 'error');
    } finally {
      setSending(false);
    }
  }

  return (
    <>
      <button onClick={() => setShowPicker(true)} disabled={loading || configs.length === 0} className={compact ? 'text-sm transition-colors' : 'btn-secondary'} style={compact ? { color: '#3b82f6' } : undefined}>
        {loading ? '加载中…' : '通道发送'}
      </button>

      {showPicker && (
        <div className="fixed inset-0 z-50 flex items-center justify-center animate-fade-in" style={{ background: 'rgba(0,0,0,0.6)' }} onClick={() => setShowPicker(false)}>
          <div className="w-96 card p-6 animate-slide-up" style={{ background: '#fcfcfc' }} onClick={e => e.stopPropagation()}>
            <h2 className="mb-1 text-base font-medium" style={{ color: '#18181b' }}>选择发送通道</h2>
            <p className="mb-5 text-xs" style={{ color: '#9ca3af' }}>选择要通过哪个通道发送此文章</p>
            <div className="space-y-2">
              {configs.map(cfg => (
                <button
                  key={cfg.id}
                  onClick={() => handleSend(cfg)}
                  disabled={sending}
                  className="w-full rounded-[12px] p-4 text-left transition-all hover:bg-surface-50"
                  style={{ background: '#f9fafb', border: '1px solid #e5e7eb' }}
                >
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium" style={{ color: '#18181b' }}>{cfg.name}</span>
                    <span className="text-xs px-2 py-0.5 rounded-full" style={{
                      background: cfg.channel_type === 'email' ? '#dbeafe' : '#dcfce7',
                      color: cfg.channel_type === 'email' ? '#1d4ed8' : '#166534',
                    }}>
                      {CHANNEL_LABELS[cfg.channel_type] || cfg.channel_type}
                    </span>
                  </div>
                  <div className="mt-1 text-xs" style={{ color: '#9ca3af' }}>
                    {cfg.channel_type === 'email'
                      ? `发送至：${cfg.config.to_addrs?.join(', ') || '未配置收件人'}`
                      : `飞书 Webhook`}
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
