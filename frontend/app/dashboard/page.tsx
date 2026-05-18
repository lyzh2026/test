import { serverFetch } from '@/lib/server-fetch';

type DailyItem = { date: string; total: number; raw?: number; analyzing?: number; processed?: number; failed_retryable?: number; failed_permanent?: number };
type StatsResp = { daily: DailyItem[]; from: string; to: string };
type CategoryItem = { label: string; count: number };
type SourceItem = { source: string; count: number };

const PIE_COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#14b8a6', '#f97316'];

export default async function DashboardPage() {
  let stats: StatsResp | null = null;
  let categories: CategoryItem[] = [];
  let sources: SourceItem[] = [];
  let errorMsg: string | null = null;
  try {
    const [s, c, sr] = await Promise.all([
      serverFetch<StatsResp>('/api/v1/stats/daily?days=14'),
      serverFetch<{ items: CategoryItem[] }>('/api/v1/stats/categories'),
      serverFetch<{ items: SourceItem[] }>('/api/v1/stats/sources'),
    ]);
    stats = s;
    categories = c?.items || [];
    sources = sr?.items || [];
  } catch (e) {
    errorMsg = (e as Error).message;
  }

  const daily = stats?.daily || [];
  const max = Math.max(1, ...daily.map((d) => d.total));
  const totalAll = daily.reduce((s, d) => s + d.total, 0);
  const processedAll = daily.reduce((s, d) => s + (d.processed || 0), 0);
  const failedAll = daily.reduce((s, d) => s + (d.failed_permanent || 0) + (d.failed_retryable || 0), 0);

  const maxCategory = Math.max(1, ...categories.map((c) => c.count));
  const maxSource = Math.max(1, ...sources.map((s) => s.count));
  const categoryTotal = categories.reduce((s, c) => s + c.count, 0);

  return (
    <main className="min-h-screen p-8 animate-fade-in">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-gray-900">看板</h1>
        <p className="mt-1.5 text-sm text-gray-400">数据概览与趋势</p>
      </div>

      {errorMsg && (
        <div className="mb-6 rounded-[12px] px-4 py-2.5 text-sm bg-red-50 text-red-500 border border-red-100">
          数据加载失败：{errorMsg}
        </div>
      )}

      {/* Stats Cards */}
      <div className="mb-8 grid grid-cols-1 gap-4 md:grid-cols-4">
        <Stat label="近 14 天采集" value={totalAll} color="#18181b" />
        <Stat label="AI 已处理" value={processedAll} color="#10b981" />
        <Stat label="失败" value={failedAll} color="#ef4444" />
        <Stat label="分类数" value={categories.length} color="#3b82f6" />
      </div>

      {/* Charts */}
      <div className="mb-8 grid grid-cols-1 gap-6 lg:grid-cols-2">
        <section className="card p-6">
          <h2 className="mb-4 text-sm font-medium text-gray-900">每日采集量</h2>
          {daily.length === 0 ? (
            <p className="text-sm text-gray-400">暂无数据</p>
          ) : (
            <div className="flex h-56 items-end gap-1.5">
              {daily.map((d) => {
                const h = max > 0 ? Math.round((d.total / max) * 100) : 0;
                return (
                  <div key={d.date} className="flex flex-1 h-full flex-col items-center justify-end group" title={`${d.date} : ${d.total}`}>
                    <div
                      className="w-full rounded-t transition-all duration-200 group-hover:opacity-80 bg-blue-500"
                      style={{ height: `${d.total > 0 ? Math.max(4, h) : 0}%`, borderRadius: '2px 2px 0 0' }}
                    />
                    <span className="mt-1.5 text-[10px] text-gray-400">{d.date.slice(5)}</span>
                  </div>
                );
              })}
            </div>
          )}
        </section>

        <section className="card p-6">
          <h2 className="mb-4 text-sm font-medium text-gray-900">分类分布</h2>
          {categories.length === 0 ? (
            <p className="text-sm text-gray-400">暂无数据</p>
          ) : (
            <div className="flex items-center gap-6">
              {/* Pie Chart */}
              <div className="relative flex-shrink-0" style={{ width: 140, height: 140 }}>
                <svg viewBox="0 0 100 100" className="w-full h-full -rotate-90">
                  {(() => {
                    let offset = 0;
                    return categories.map((c, i) => {
                      const pct = categoryTotal > 0 ? c.count / categoryTotal : 0;
                      const dashArray = `${pct * 100} ${100 - pct * 100}`;
                      const el = (
                        <circle
                          key={c.label}
                          cx="50"
                          cy="50"
                          r="40"
                          fill="none"
                          stroke={PIE_COLORS[i % PIE_COLORS.length]}
                          strokeWidth="20"
                          strokeDasharray={dashArray}
                          strokeDashoffset={-offset}
                        />
                      );
                      offset += pct * 100;
                      return el;
                    });
                  })()}
                </svg>
                <div className="absolute inset-0 flex flex-col items-center justify-center">
                  <span className="text-lg font-semibold text-gray-900">{categoryTotal}</span>
                  <span className="text-[10px] text-gray-400">总计</span>
                </div>
              </div>
              {/* Legend */}
              <div className="flex-1 space-y-2">
                {categories.map((c, i) => (
                  <div key={c.label} className="flex items-center gap-2 text-sm">
                    <span className="w-3 h-3 rounded-full flex-shrink-0" style={{ background: PIE_COLORS[i % PIE_COLORS.length] }} />
                    <span className="flex-1 truncate text-gray-600">{c.label}</span>
                    <span className="text-xs text-gray-400">{c.count}</span>
                    <span className="text-xs text-gray-300 w-10 text-right">
                      {categoryTotal > 0 ? Math.round((c.count / categoryTotal) * 100) : 0}%
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>
      </div>

      {/* Source Ranking */}
      <section className="card p-6">
        <h2 className="mb-4 text-sm font-medium text-gray-900">来源排行 Top 10</h2>
        {sources.length === 0 ? (
          <p className="text-sm text-gray-400">暂无数据</p>
        ) : (
          <div className="space-y-3">
            {sources.map((s) => {
              const w = Math.round((s.count / maxSource) * 100);
              return (
                <div key={s.source} className="flex items-center gap-3 text-sm">
                  <span className="w-32 flex-shrink-0 truncate text-right text-gray-500" title={s.source}>{s.source}</span>
                  <div className="flex-1 rounded-full overflow-hidden bg-gray-100" style={{ height: '6px' }}>
                    <div className="h-full rounded-full transition-all duration-300 bg-green-500" style={{ width: `${Math.max(4, w)}%` }} />
                  </div>
                  <span className="w-8 flex-shrink-0 text-right text-gray-400 text-xs">{s.count}</span>
                </div>
              );
            })}
          </div>
        )}
      </section>
    </main>
  );
}

function Stat({ label, value, color }: { label: string; value: number; color?: string }) {
  return (
    <div className="card p-5 transition-all duration-200 card-hover">
      <div className="text-xs text-gray-400">{label}</div>
      <div className="mt-2 text-2xl font-semibold" style={{ color: color || '#18181b' }}>{value}</div>
    </div>
  );
}
