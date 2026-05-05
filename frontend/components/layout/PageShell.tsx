'use client';

import { usePathname } from 'next/navigation';
import { Sidebar } from './Sidebar';

export function PageShell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const isLogin = path === '/login';

  if (isLogin) {
    return <>{children}</>;
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <div className="flex-1 ml-[60px] min-h-screen">
        {children}
      </div>
    </div>
  );
}
