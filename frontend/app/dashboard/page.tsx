import { serverFetch } from '@/lib/server-fetch';

type DailyItem = { date: string; total: number; raw?: number; analyzing?: number; processed?: number; failed_retryable?: number; failed_permanent?: number };
type StatsResp = { daily: DailyItem[]; from: string; to: string };
type CategoryItem = { label: string; count: number };
type SourceItem = { source: string; count: number };

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
    categories = c.items || [];
    sources = sr.items || [];
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

  return (
    <main className="min-h-screen p-8 animate-fade-in">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold" style={{ color: '#e8e9ed' }}>看板</h1>
        <p className="mt-1.5 text-sm" style={{ color: '#6b6d7b' }}>数据概览与趋势</p>
      </div>

      {errorMsg && (
        <div className="mb-6 rounded-[12px] px-4 py-2.5 text-sm" style={{ background: 'rgba(228, 90, 90, 0.08)', color: '#e45a5a', border: '1px solid rgba(228, 90, 90, 0.15)' }}>
          数据加载失败：{errorMsg}
        </div>
      )}

      {/* Stats Cards */}
      <div className="mb-8 grid grid-cols-1 gap-4 md:grid-cols-4">
        <Stat label="近 14 天采集" value={totalAll} color="#e8e9ed" />
        <Stat label="AI 已处理" value={processedAll} color="#4ec89e" />
        <Stat label="失败" value={failedAll} color="#e45a5a" />
        <Stat label="分类数" value={categories.length} color="#6b8cff" />
      </div>

      {/* Charts */}
      <div className="mb-8 grid grid-cols-1 gap-6 lg:grid-cols-2">
        <section className="card p-6">
          <h2 className="mb-4 text-sm font-medium" style={{ color: '#e8e9ed' }}>每日采集量</h2>
          {daily.length === 0 ? (
            <p className="text-sm" style={{ color: '#6b6d7b' }}>暂无数据</p>
          ) : (
            <div className="flex h-56 items-end gap-1.5">
              {daily.map((d) => {
                const h = Math.round((d.total / max) * 100);
                return (
                  <div key={d.date} className="flex flex-1 flex-col items-center justify-end group" title={`${d.date} : ${d.total}`}>
                    <div
                      className="w-full rounded-t transition-all duration-200 group-hover:opacity-80"
                      style={{ height: `${Math.max(4, h)}%`, background: '#6b8cff', borderRadius: '2px 2px 0 0' }}
                    />
                    <span className="mt-1.5 text-[10px]" style={{ color: '#6b6d7b' }}>{d.date.slice(5)}</span>
                  </div>
                );
              })}
            </div>
          )}
        </section>

        <section className="card p-6">
          <h2 className="mb-4 text-sm font-medium" style={{ color: '#e8e9ed' }}>分类分布</h2>
          {categories.length === 0 ? (
            <p className="text-sm" style={{ color: '#6b6d7b' }}>暂无数据</p>
          ) : (
            <div className="space-y-3">
              {categories.map((c) => {
                const w = Math.round((c.count / maxCategory) * 100);
                return (
                  <div key={c.label} className="flex items-center gap-3 text-sm">
                    <span className="w-16 flex-shrink-0 text-right" style={{ color: '#a8abb8' }}>{c.label}</span>
                    <div className="flex-1 rounded-full overflow-hidden" style={{ background: '#262933', height: '6px' }}>
                      <div className="h-full rounded-full transition-all duration-300" style={{ width: `${Math.max(4, w)}%`, background: '#6b8cff' }} />
                    </div>
                    <span className="w-8 flex-shrink-0 text-right text-xs" style={{ color: '#6b6d7b' }}>{c.count}</span>
                  </div>
                );
              })}
            </div>
          )}
        </section>
      </div>

      {/* Source Ranking */}
      <section className="card p-6">
        <h2 className="mb-4 text-sm font-medium" style={{ color: '#e8e9ed' }}>来源排行 Top 10</h2>
        {sources.length === 0 ? (
          <p className="text-sm text-text-muted">暂无数据</p>
        ) : (
          <div className="space-y-3">
            {sources.map((s) => {
              const w = Math.round((s.count / maxSource) * 100);
              return (
                <div key={s.source} className="flex items-center gap-3 text-sm">
                  <span className="w-32 flex-shrink-0 truncate text-right" style={{ color: '#a8abb8' }} title={s.source}>{s.source}</span>
                  <div className="flex-1 rounded-full overflow-hidden" style={{ background: '#262933', height: '6px' }}>
                    <div className="h-full rounded-full transition-all duration-300" style={{ width: `${Math.max(4, w)}%`, background: '#4ec89e' }} />
                  </div>
                  <span className="w-8 flex-shrink-0 text-right text-text-muted text-xs">{s.count}</span>
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
      <div className="text-xs" style={{ color: '#6b6d7b' }}>{label}</div>
      <div className="mt-2 text-2xl font-semibold" style={{ color: color || '#e8e9ed' }}>{value}</div>
    </div>
  );
}
