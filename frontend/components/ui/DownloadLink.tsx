'use client';

import { downloadWithPicker } from '@/lib/download';

export function DownloadLink({ href, filename, children, className, style }: {
  href: string;
  filename: string;
  children: React.ReactNode;
  className?: string;
  style?: React.CSSProperties;
}) {
  async function handleClick(e: React.MouseEvent) {
    e.preventDefault();
    await downloadWithPicker(href, filename);
  }

  return (
    <button onClick={handleClick} className={className} style={style}>
      {children}
    </button>
  );
}
