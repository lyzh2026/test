import Link from 'next/link';

export default function NotFound() {
  return (
    <main className="min-h-screen flex items-center justify-center">
      <div className="text-center">
        <p className="text-6xl font-semibold" style={{ color: '#e5e7eb' }}>404</p>
        <h1 className="mt-4 text-lg font-medium" style={{ color: '#18181b' }}>页面不存在</h1>
        <p className="mt-2 text-sm" style={{ color: '#9ca3af' }}>你访问的页面已被移除或从未存在</p>
        <Link
          href="/"
          className="mt-6 inline-block rounded-lg px-4 py-2 text-sm font-medium transition-colors"
          style={{ background: '#18181b', color: '#fff' }}
        >
          返回首页
        </Link>
      </div>
    </main>
  );
}
