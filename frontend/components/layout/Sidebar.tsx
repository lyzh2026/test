'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useState } from 'react';

const NAV_MAIN = [
  { href: '/dashboard', label: '看板', icon: '◈' },
  { href: '/articles', label: '文章', icon: '⊞' },
  { href: '/tasks', label: '任务', icon: '◉' },
];

const NAV_SECONDARY = [
  { href: '/admin/distribution', label: '分发配置', icon: '⇶' },
  { href: '/admin/settings', label: '设置', icon: '⚙' },
];

export function Sidebar() {
  const path = usePathname();
  const router = useRouter();
  const [hoveredItem, setHoveredItem] = useState<string | null>(null);

  async function logout() {
    try {
      await fetch('/api/proxy/api/v1/auth/logout', { method: 'POST', credentials: 'include' });
    } catch {
      // ignore
    }
    router.push('/login');
    router.refresh();
  }

  function isActive(href: string) {
    if (href === '/dashboard') return path === href;
    return path?.startsWith(href);
  }

  function Tooltip({ label }: { label: string }) {
    return (
      <div
        className="pointer-events-none fixed left-[78px] z-50 rounded-[12px] px-3 py-1.5 text-xs font-medium whitespace-nowrap"
        style={{
          background: '#18181b',
          color: '#ffffff',
          transform: 'translateY(-50%)',
        }}
      >
        {label}
      </div>
    );
  }

  const navItems = [...NAV_MAIN, ...NAV_SECONDARY];

  return (
    <aside
      className="fixed left-0 top-0 z-40 flex h-full flex-col items-center py-6 border-r"
      style={{
        width: '72px',
        background: '#ffffff',
        borderColor: '#f0f0f0',
      }}
    >
      {/* Logo */}
      <div className="relative mb-8 flex items-center justify-center">
        <div
          className="flex h-10 w-10 items-center justify-center rounded-xl text-lg font-bold"
          style={{ background: '#18181b', color: '#ffffff' }}
        >
          拾
        </div>
      </div>

      {/* Nav Items */}
      <nav className="flex flex-1 flex-col items-center gap-3">
        {navItems.map((item) => {
          const active = isActive(item.href);
          return (
            <div key={item.href} className="relative flex items-center justify-center">
              {active && (
                <div
                  className="absolute left-[-1px] top-1/2 h-5 w-[2px] -translate-y-1/2 rounded-r-full"
                  style={{ background: '#3b82f6' }}
                />
              )}
              <Link
                href={item.href}
                className="flex h-12 w-12 items-center justify-center rounded-[12px] text-base leading-none transition-all duration-200"
                style={{
                  background: active ? '#EEF2FF' : 'transparent',
                  color: active ? '#3b82f6' : '#8E9AAF',
                }}
                onMouseEnter={() => setHoveredItem(item.href)}
                onMouseLeave={() => setHoveredItem(null)}
              >
                <span className="flex items-center justify-center">{item.icon}</span>
              </Link>
              {hoveredItem === item.href && <Tooltip label={item.label} />}
            </div>
          );
        })}
      </nav>

      {/* Logout */}
      <div className="relative flex items-center justify-center">
        <button
          onClick={logout}
          className="flex h-12 w-12 items-center justify-center rounded-[12px] text-base leading-none transition-all duration-200"
          style={{ color: '#8E9AAF' }}
          onMouseEnter={() => setHoveredItem('__logout')}
          onMouseLeave={() => setHoveredItem(null)}
        >
          <span>↩</span>
        </button>
        {hoveredItem === '__logout' && <Tooltip label="退出登录" />}
      </div>
    </aside>
  );
}
