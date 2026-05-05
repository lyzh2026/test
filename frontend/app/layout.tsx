import './globals.css';
import type { Metadata } from 'next';
import type { ReactNode } from 'react';
import { Noto_Sans_SC } from 'next/font/google';
import { PageShell } from '@/components/layout/PageShell';

const notoSansSC = Noto_Sans_SC({
  subsets: ['latin'],
  weight: ['300', '400', '500', '700'],
  display: 'swap',
});

export const metadata: Metadata = {
  title: '拾讯 · 智能内容采集分发平台',
  description: '拾讯：自动化抓取、AI 分类与摘要、看板分发',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-CN">
      <body className={notoSansSC.className}>
        <PageShell>{children}</PageShell>
      </body>
    </html>
  );
}
