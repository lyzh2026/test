'use client';

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main className="min-h-screen flex items-center justify-center">
      <div className="text-center">
        <p className="text-6xl font-semibold" style={{ color: '#e5e7eb' }}>500</p>
        <h1 className="mt-4 text-lg font-medium" style={{ color: '#18181b' }}>出了点问题</h1>
        <p className="mt-2 text-sm max-w-md mx-auto" style={{ color: '#9ca3af' }}>
          {error.message || '服务器遇到了意外错误，请稍后重试'}
        </p>
        <button
          onClick={reset}
          className="mt-6 inline-block rounded-lg px-4 py-2 text-sm font-medium transition-colors"
          style={{ background: '#18181b', color: '#fff' }}
        >
          重试
        </button>
      </div>
    </main>
  );
}
