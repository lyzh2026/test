'use client';

import { useEffect, useState, useCallback } from 'react';
import { api, ApiError } from '@/lib/api';
import { useToast } from '@/components/ui/Toast';

type DistConfig = {
  id: string;
  channel_type: string;
  name: string;
  config: Record<string, unknown>;
  enabled: boolean;
  created_at: string | null;
  updated_at: string | null;
};

const CHANNEL_LABELS: Record<string, string> = {
  email: '邮件',
  webhook: 'Webhook（飞书）',
};

export default function DistributionPage() {
  const [items, setItems] = useState<DistConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [formOpen, setFormOpen] = useState(false);

  const [sending, setSending] = useState(false);
  const { toast, confirm } = useToast();

  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewType, setPreviewType] = useState('email');
  const [previewContent, setPreviewContent] = useState<string | null>(null);
  const [editId, setEditId] = useState<string | null>(null);
  const [formType, setFormType] = useState('email');
  const [formName, setFormName] = useState('');
  const [formEnabled, setFormEnabled] = useState(true);

  const [smtpHost, setSmtpHost] = useState('');
  const [smtpPort, setSmtpPort] = useState('465');
  const [smtpUser, setSmtpUser] = useState('');
  const [smtpPass, setSmtpPass] = useState('');
  const [fromAddr, setFromAddr] = useState('');
  const [toAddrs, setToAddrs] = useState('');

  const [webhookUrl, setWebhookUrl] = useState('');

  const fetchList = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.get<{ items: DistConfig[] }>('/api/v1/distribution/configs');
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
    setFormType('email');
    setFormName('');
    setFormEnabled(true);
    setSmtpHost('');
    setSmtpPort('465');
    setSmtpUser('');
    setSmtpPass('');
    setFromAddr('');
    setToAddrs('');
    setWebhookUrl('');
    setFormOpen(true);
  }

  function openEdit(item: DistConfig) {
    setEditId(item.id);
    setFormType(item.channel_type);
    setFormName(item.name);
    setFormEnabled(item.enabled);
    const c = item.config;
    setSmtpHost(String(c.smtp_host || ''));
    setSmtpPort(String(c.smtp_port || '465'));
    setSmtpUser(String(c.smtp_user || ''));
    setSmtpPass('');
    setFromAddr(String(c.from_addr || ''));
    setToAddrs(Array.isArray(c.to_addrs) ? c.to_addrs.join(', ') : '');
    setWebhookUrl(String(c.url || ''));
    setFormOpen(true);
  }

  function buildConfig(): Record<string, unknown> {
    if (formType === 'email') {
      return {
        smtp_host: smtpHost,
        smtp_port: parseInt(smtpPort, 10) || 465,
        smtp_user: smtpUser,
        smtp_pass: smtpPass,
        from_addr: fromAddr || smtpUser,
        to_addrs: toAddrs.split(',').map(s => s.trim()).filter(Boolean),
        use_tls: true,
      };
    }
    return { url: webhookUrl, platform: 'feishu' };
  }

  async function handleSave() {
    if (!formName.trim()) return;
    if (formType === 'webhook' && !webhookUrl.trim()) return;
    if (formType === 'email' && !smtpHost.trim()) return;
    try {
      const payload = {
        channel_type: formType,
        name: formName.trim(),
        config: buildConfig(),
        enabled: formEnabled,
      };
      if (editId) {
        await api.put(`/api/v1/distribution/configs/${editId}`, payload);
      } else {
        await api.post('/api/v1/distribution/configs', payload);
      }
      setFormOpen(false);
      fetchList();
    } catch (e: unknown) {
      toast(e instanceof ApiError ? e.message : '保存失败', 'error');
    }
  }

  async function handleToggle(id: string) {
    try {
      await api.patch(`/api/v1/distribution/configs/${id}/toggle`);
      fetchList();
    } catch (e: unknown) {
      toast(e instanceof ApiError ? e.message : '操作失败', 'error');
    }
  }

  async function handleDelete(id: string) {
    if (!await confirm('确认删除此分发配置？')) return;
    try {
      await api.delete(`/api/v1/distribution/configs/${id}`);
      fetchList();
    } catch (e: unknown) {
      toast(e instanceof ApiError ? e.message : '删除失败', 'error');
    }
  }

  async function handlePreview(channelType: string) {
    setPreviewLoading(true);
    setPreviewOpen(true);
    setPreviewType(channelType);
    setPreviewContent(null);
    try {
      const data = await api.get<{ content: string }>(`/api/v1/distribution/preview?channel_type=${channelType}`);
      setPreviewContent(typeof data.content === 'string' ? data.content : JSON.stringify(data.content, null, 2));
    } catch (e: unknown) {
      setPreviewContent(null);
      toast(e instanceof ApiError ? e.message : '预览加载失败', 'error');
    } finally {
      setPreviewLoading(false);
    }
  }

  return (
    <main className="min-h-screen p-8 animate-fade-in">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold" style={{ color: '#18181b' }}>分发配置</h1>
          <p className="mt-1.5 text-sm" style={{ color: '#9ca3af' }}>管理邮件与 Webhook 分发通道</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={async () => {
              const msg = '确认立即发送本周周报？\n\n点击"确定"正常发送（已成功的通道会跳过）。\n如需强制补发所有通道，请取消后点击"强制发送"。';
              if (!await confirm(msg)) return;
              setSending(true);
              try {
                await api.post('/api/v1/distribution/trigger');
                toast('周报分发已触发（已成功的通道已跳过）', 'success');
              } catch (e: unknown) {
                toast(e instanceof ApiError ? e.message : '发送失败', 'error');
              } finally {
                setSending(false);
              }
            }}
            disabled={sending}
            className="btn-secondary"
          >
            {sending ? '发送中…' : '立即发送'}
          </button>
          <button
            onClick={async () => {
              if (!await confirm('确认强制补发本周周报？\n将忽略幂等检查，所有通道都会重新发送。')) return;
              setSending(true);
              try {
                await api.post('/api/v1/distribution/trigger?force=true');
                toast('周报强制补发已触发', 'success');
              } catch (e: unknown) {
                toast(e instanceof ApiError ? e.message : '发送失败', 'error');
              } finally {
                setSending(false);
              }
            }}
            disabled={sending}
            className="btn-secondary"
            style={{ color: '#ef4444' }}
          >
            强制发送
          </button>
          <button onClick={openNew} className="btn-primary">
            新增通道
          </button>
        </div>
      </div>

      {loading ? (
        <p className="text-sm" style={{ color: '#9ca3af' }}>加载中…</p>
      ) : items.length === 0 ? (
        <div className="card p-8 text-center text-sm" style={{ color: '#9ca3af' }}>暂未配置分发通道</div>
      ) : (
        <div className="card overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr style={{ borderBottom: '1px solid #e5e7eb' }}>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider" style={{ color: '#9ca3af' }}>通道名称</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider" style={{ color: '#9ca3af' }}>类型</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider" style={{ color: '#9ca3af' }}>状态</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider" style={{ color: '#9ca3af' }}>创建时间</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider" style={{ color: '#9ca3af' }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id} className="transition-colors duration-150 hover:bg-surface-50" style={{ borderBottom: '1px solid #e5e7eb' }}>
                  <td className="px-4 py-3" style={{ color: '#18181b' }}>{item.name}</td>
                  <td className="px-4 py-3 text-xs" style={{ color: '#6b7280' }}>
                    {CHANNEL_LABELS[item.channel_type] || item.channel_type}
                  </td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => handleToggle(item.id)}
                      className={item.enabled ? 'badge-green cursor-pointer' : 'badge-gray cursor-pointer'}
                    >
                      {item.enabled ? '已启用' : '已禁用'}
                    </button>
                  </td>
                  <td className="px-4 py-3 text-xs" style={{ color: '#9ca3af' }}>
                    {item.created_at ? new Date(item.created_at).toLocaleString('zh-CN') : '-'}
                  </td>
                  <td className="px-4 py-3">
                    <button onClick={() => handlePreview(item.channel_type)} className="text-xs transition-colors mr-3" style={{ color: '#6b7280' }}>预览</button>
                    <button onClick={() => openEdit(item)} className="text-xs transition-colors mr-3" style={{ color: '#6b7280' }}>编辑</button>
                    <button onClick={() => handleDelete(item.id)} className="text-xs" style={{ color: '#ef4444' }}>删除</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Form Modal */}
      {formOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center animate-fade-in" style={{ background: 'rgba(0,0,0,0.6)' }}>
          <div className="w-full max-w-lg card p-6 animate-slide-up" style={{ background: '#fcfcfc' }}>
            <h2 className="mb-5 text-base font-medium" style={{ color: '#18181b' }}>
              {editId ? '编辑' : '新增'}分发通道
            </h2>
            <div className="space-y-4">
              <div>
                <label className="block text-xs mb-1" style={{ color: '#9ca3af' }}>通道类型</label>
                <select value={formType} onChange={e => setFormType(e.target.value)} className="input" disabled={!!editId}>
                  <option value="email">邮件</option>
                  <option value="webhook">Webhook（飞书）</option>
                </select>
              </div>
              <div>
                <label className="block text-xs mb-1" style={{ color: '#9ca3af' }}>通道名称</label>
                <input value={formName} onChange={e => setFormName(e.target.value)} className="input" placeholder="如：研发团队邮件组" />
              </div>

              {formType === 'email' && (
                <>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs mb-1" style={{ color: '#9ca3af' }}>SMTP 地址</label>
                      <input value={smtpHost} onChange={e => setSmtpHost(e.target.value)} className="input" placeholder="smtp.qq.com" />
                    </div>
                    <div>
                      <label className="block text-xs mb-1" style={{ color: '#9ca3af' }}>端口</label>
                      <input value={smtpPort} onChange={e => setSmtpPort(e.target.value)} className="input" placeholder="465" />
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs mb-1" style={{ color: '#9ca3af' }}>SMTP 用户名</label>
                    <input value={smtpUser} onChange={e => setSmtpUser(e.target.value)} className="input" placeholder="xxx@qq.com" />
                  </div>
                  <div>
                    <label className="block text-xs mb-1" style={{ color: '#9ca3af' }}>SMTP 密码/授权码</label>
                    <input type="password" value={smtpPass} onChange={e => setSmtpPass(e.target.value)} className="input" placeholder={editId ? '留空则不修改' : ''} />
                  </div>
                  <div>
                    <label className="block text-xs mb-1" style={{ color: '#9ca3af' }}>发件人地址</label>
                    <input value={fromAddr} onChange={e => setFromAddr(e.target.value)} className="input" placeholder="可选，默认同用户名" />
                  </div>
                  <div>
                    <label className="block text-xs mb-1" style={{ color: '#9ca3af' }}>收件人（多个用逗号分隔）</label>
                    <input value={toAddrs} onChange={e => setToAddrs(e.target.value)} className="input" placeholder="a@company.com, b@company.com" />
                  </div>
                </>
              )}

              {formType === 'webhook' && (
                <div>
                  <label className="block text-xs mb-1" style={{ color: '#9ca3af' }}>Webhook URL</label>
                  <input value={webhookUrl} onChange={e => setWebhookUrl(e.target.value)} className="input" placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/..." />
                </div>
              )}

              <label className="flex items-center gap-2 text-sm cursor-pointer" style={{ color: '#6b7280' }}>
                <input type="checkbox" checked={formEnabled} onChange={e => setFormEnabled(e.target.checked)}
                  className="h-4 w-4 rounded" style={{ accentColor: '#3b82f6' }} />
                启用
              </label>
            </div>
            <div className="mt-6 flex justify-end gap-3">
              <button onClick={() => setFormOpen(false)} className="btn-secondary">取消</button>
              <button onClick={handleSave} className="btn-primary">保存</button>
            </div>
          </div>
        </div>
      )}

      {/* Preview Modal */}
      {previewOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center animate-fade-in" style={{ background: 'rgba(0,0,0,0.6)' }}>
          <div className="flex max-h-[80vh] w-full max-w-3xl flex-col card" style={{ background: '#fcfcfc' }}>
            <div className="flex items-center justify-between px-6 py-4" style={{ borderBottom: '1px solid #e5e7eb' }}>
              <h2 className="text-sm font-medium" style={{ color: '#18181b' }}>
                周报预览 ({previewType === 'email' ? '邮件' : '飞书卡片'})
              </h2>
              <button onClick={() => setPreviewOpen(false)} className="text-lg leading-none" style={{ color: '#9ca3af' }}>&times;</button>
            </div>
            <div className="flex-1 overflow-auto p-6">
              {previewLoading ? (
                <p className="text-sm" style={{ color: '#9ca3af' }}>加载中…</p>
              ) : previewType === 'email' ? (
                <iframe srcDoc={previewContent || ''} className="h-[60vh] w-full border-0 rounded" title="周报预览" />
              ) : (
                <pre className="whitespace-pre-wrap break-all rounded p-4 text-xs font-mono" style={{ background: '#f9fafb', color: '#6b7280' }}>
                  {previewContent}
                </pre>
              )}
            </div>
            <div className="flex justify-end px-6 py-3" style={{ borderTop: '1px solid #e5e7eb' }}>
              <button onClick={() => setPreviewOpen(false)} className="btn-secondary">关闭</button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
