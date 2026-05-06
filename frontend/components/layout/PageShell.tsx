'use client';

import { usePathname } from 'next/navigation';
import { useState, useEffect } from 'react';
import { Sidebar } from './Sidebar';

export function PageShell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const isLogin = path === '/login';
  const [collapsed, setCollapsed] = useState(false);
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    function check() {
      const mobile = window.innerWidth < 768;
      setIsMobile(mobile);
      if (mobile) setCollapsed(true);
    }
    check();
    window.addEventListener('resize', check);
    return () => window.removeEventListener('resize', check);
  }, []);

  if (isLogin) {
    return <>{children}</>;
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar collapsed={collapsed} onToggle={() => setCollapsed(c => !c)} />
      <div
        className="flex-1 min-h-screen transition-all duration-200"
        style={{ marginLeft: isMobile ? 0 : '72px' }}
      >
        {children}
      </div>
    </div>
  );
}
