'use client';

import { useState, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';

export const dynamic = 'force-dynamic';

function LoginForm() {
  const router = useRouter();
  const search = useSearchParams();
  const next = search.get('next') || '/dashboard';
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/proxy/api/v1/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ username, password }),
      });
      const body = await res.json();
      if (body.code !== 0) throw new Error(body.message || '登录失败');
      router.push(next);
      router.refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-6" style={{ background: '#0f1117' }}>
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="mb-10 flex flex-col items-center">
          <div
            className="mb-4 flex h-12 w-12 items-center justify-center rounded-[14px] text-sm font-bold"
            style={{ background: '#6b8cff', color: '#0f1117' }}
          >
            SX
          </div>
          <h1 className="text-xl font-semibold" style={{ color: '#e8e9ed' }}>拾讯</h1>
          <p className="mt-1.5 text-sm" style={{ color: '#6b6d7b' }}>智能内容采集与分发平台</p>
        </div>

        <form
          onSubmit={onSubmit}
          className="p-8 space-y-6 animate-fade-in"
          style={{
            background: '#0f1117',
            border: '1px solid #262933',
            borderRadius: '16px',
          }}
        >
          <div>
            <label className="mb-2 block text-xs font-medium" style={{ color: '#a8abb8' }}>用户名</label>
            <input
              className="input"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              required
            />
          </div>

          <div>
            <label className="mb-2 block text-xs font-medium" style={{ color: '#a8abb8' }}>密码</label>
            <input
              className="input"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </div>

          {error && (
            <div
              className="rounded-[12px] px-4 py-2.5 text-sm"
              style={{ background: 'rgba(228, 90, 90, 0.08)', color: '#e45a5a', border: '1px solid rgba(228, 90, 90, 0.15)' }}
            >
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="btn-primary w-full py-2.5 disabled:opacity-50"
          >
            {loading ? '登录中…' : '登录'}
          </button>

          <p className="text-xs text-center" style={{ color: '#6b6d7b' }}>
            默认账户 admin / admin123
          </p>
        </form>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={
      <div className="flex min-h-screen items-center justify-center" style={{ background: '#0f1117' }}>
        <p className="text-sm" style={{ color: '#6b6d7b' }}>正在加载...</p>
      </div>
    }>
      <LoginForm />
    </Suspense>
  );
}
