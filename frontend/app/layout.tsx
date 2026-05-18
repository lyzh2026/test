import './globals.css';
import type { Metadata } from 'next';
import type { ReactNode } from 'react';
import { PageShell } from '@/components/layout/PageShell';
import { ToastProvider } from '@/components/ui/Toast';

export const metadata: Metadata = {
  title: '拾讯 · 智能内容采集分发平台',
  description: '拾讯：自动化抓取、AI 分类与摘要、看板分发',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-CN">
      <body style={{ fontFamily: 'system-ui, -apple-system, "Segoe UI", Roboto, "Noto Sans SC", sans-serif' }}>
        <ToastProvider><PageShell>{children}</PageShell></ToastProvider>
      </body>
    </html>
  );
}
