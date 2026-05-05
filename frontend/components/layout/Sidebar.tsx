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
  { href: '/tasks/new', label: '新建任务', icon: '⊕' },
  { href: '/admin/distribution', label: '分发配置', icon: '⇶' },
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
        className="pointer-events-none fixed left-[66px] z-50 rounded-[20px] px-3 py-1.5 text-xs font-medium whitespace-nowrap"
        style={{
          background: '#181b25',
          color: '#e8e9ed',
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
      className="fixed left-0 top-0 z-40 flex h-full flex-col items-center py-4 border-r"
      style={{
        width: '60px',
        background: '#0f1117',
        borderColor: '#262933',
      }}
    >
      {/* Logo */}
      <div className="relative mb-6 flex items-center justify-center">
        <div
          className="flex h-8 w-8 items-center justify-center rounded-[10px] text-xs font-bold"
          style={{ background: '#6b8cff', color: '#0f1117' }}
        >
          SX
        </div>
      </div>

      {/* Nav Items */}
      <nav className="flex flex-1 flex-col items-center gap-1">
        {navItems.map((item) => {
          const active = isActive(item.href);
          return (
            <div key={item.href} className="relative flex items-center justify-center">
              {active && (
                <div
                  className="absolute left-[-1px] top-1/2 h-5 w-[2px] -translate-y-1/2 rounded-r-full"
                  style={{ background: '#6b8cff' }}
                />
              )}
              <Link
                href={item.href}
                className="flex h-9 w-9 items-center justify-center rounded-[10px] text-base leading-none transition-all duration-150"
                style={{
                  background: active ? 'rgba(107, 140, 255, 0.12)' : 'transparent',
                  color: active ? '#e8e9ed' : '#33364a',
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
          className="flex h-9 w-9 items-center justify-center rounded-[10px] text-base leading-none transition-all duration-150"
          style={{ color: '#33364a' }}
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
