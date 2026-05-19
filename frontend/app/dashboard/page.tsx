import { serverFetch } from '@/lib/server-fetch';

export const dynamic = 'force-dynamic'; // force rebuild v2

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

  const maxSource = Math.max(1, ...sources.map((s) => s.count));
  const categoryTotal = categories.reduce((s, c) => s + c.count, 0);

  return (
    <main className="min-h-screen p-8 animate-fade-in">
      <div className="mb-8">
        <h1 style={{ fontSize: '1.5rem', fontWeight: 600, color: '#111827' }}>看板</h1>
        <p style={{ marginTop: '6px', fontSize: '0.875rem', color: '#9ca3af' }}>数据概览与趋势</p>
      </div>

      {errorMsg && (
        <div style={{ marginBottom: '1.5rem', borderRadius: '12px', padding: '10px 16px', fontSize: '0.875rem', background: '#fef2f2', color: '#ef4444', border: '1px solid #fecaca' }}>
          数据加载失败：{errorMsg}
        </div>
      )}

      {/* Stats Cards */}
      <div style={{ marginBottom: '2rem', display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem' }}>
        <Stat label="近 14 天采集" value={totalAll} color="#18181b" />
        <Stat label="AI 已处理" value={processedAll} color="#10b981" />
        <Stat label="失败" value={failedAll} color="#ef4444" />
        <Stat label="分类数" value={categories.length} color="#3b82f6" />
      </div>

      {/* Charts */}
      <div style={{ marginBottom: '2rem', display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '1.5rem' }}>
        {/* 每日采集量 */}
        <section className="card" style={{ padding: '1.5rem' }}>
          <h2 style={{ marginBottom: '1rem', fontSize: '0.875rem', fontWeight: 500, color: '#111827' }}>每日采集量</h2>
          {daily.length === 0 ? (
            <p style={{ fontSize: '0.875rem', color: '#9ca3af' }}>暂无数据</p>
          ) : (() => {
            const yMax = 5;
            const chartH = 200;
            return (
              <div style={{ display: 'flex' }}>
                {/* Y 轴 */}
                <div style={{ position: 'relative', width: '28px', height: chartH, marginRight: '8px', borderRight: '1px solid #e5e7eb', borderBottom: '1px solid #e5e7eb' }}>
                  {[0, 1, 2, 3, 4, 5].map((t) => (
                    <span key={t} style={{ position: 'absolute', right: '6px', bottom: `${(t / yMax) * 100}%`, fontSize: '10px', color: '#9ca3af', lineHeight: 1 }}>{t}</span>
                  ))}
                </div>
                {/* 柱状图区域 */}
                <div style={{ flex: 1, display: 'flex', height: chartH, alignItems: 'flex-end', gap: '6px' }}>
                  {daily.map((d) => {
                    const pct = Math.min(d.total, yMax) / yMax * 100;
                    return (
                      <div key={d.date} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'flex-end', height: '100%', position: 'relative' }} title={`${d.date} : ${d.total}`}>
                        {d.total > 0 && (
                          <span style={{ position: 'absolute', bottom: `${pct}%`, fontSize: '10px', fontWeight: 600, color: '#3b82f6', marginBottom: '2px' }}>{d.total}</span>
                        )}
                        <div style={{ width: '100%', height: `${Math.max(d.total > 0 ? 4 : 1, pct)}%`, background: d.total > 0 ? '#3b82f6' : '#e5e7eb', borderRadius: '2px 2px 0 0' }} />
                        <span style={{ marginTop: '6px', fontSize: '10px', color: '#9ca3af' }}>{d.date.slice(5)}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })()}
        </section>

        {/* 分类分布 */}
        <section className="card" style={{ padding: '1.5rem' }}>
          <h2 style={{ marginBottom: '1rem', fontSize: '0.875rem', fontWeight: 500, color: '#111827' }}>分类分布</h2>
          {categories.length === 0 ? (
            <p style={{ fontSize: '0.875rem', color: '#9ca3af' }}>暂无数据</p>
          ) : (
            <div style={{ display: 'flex', alignItems: 'center', gap: '1.5rem' }}>
              <div style={{ position: 'relative', width: 140, height: 140, flexShrink: 0 }}>
                <svg viewBox="0 0 100 100" style={{ width: '100%', height: '100%', transform: 'rotate(-90deg)' }}>
                  {(() => {
                    const r = 40;
                    const C = 2 * Math.PI * r;
                    let offset = 0;
                    return categories.map((c, i) => {
                      const pct = categoryTotal > 0 ? c.count / categoryTotal : 0;
                      const len = pct * C;
                      const el = (
                        <circle key={c.label} cx="50" cy="50" r={r} fill="none" stroke={PIE_COLORS[i % PIE_COLORS.length]} strokeWidth="20" strokeDasharray={`${len} ${C - len}`} strokeDashoffset={-offset} />
                      );
                      offset += len;
                      return el;
                    });
                  })()}
                </svg>
                <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
                  <span style={{ fontSize: '1.125rem', fontWeight: 600, color: '#111827' }}>{categoryTotal}</span>
                  <span style={{ fontSize: '10px', color: '#9ca3af' }}>总计</span>
                </div>
              </div>
              <div style={{ flex: 1 }}>
                {categories.map((c, i) => (
                  <div key={c.label} style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.875rem', marginBottom: '8px' }}>
                    <span style={{ width: 12, height: 12, borderRadius: '50%', background: PIE_COLORS[i % PIE_COLORS.length], flexShrink: 0 }} />
                    <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: '#4b5563' }}>{c.label}</span>
                    <span style={{ fontSize: '0.75rem', color: '#9ca3af' }}>{c.count}</span>
                    <span style={{ fontSize: '0.75rem', color: '#d1d5db', width: 40, textAlign: 'right' }}>
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
      <section className="card" style={{ padding: '1.5rem' }}>
        <h2 style={{ marginBottom: '1rem', fontSize: '0.875rem', fontWeight: 500, color: '#111827' }}>来源排行 Top 10</h2>
        {sources.length === 0 ? (
          <p style={{ fontSize: '0.875rem', color: '#9ca3af' }}>暂无数据</p>
        ) : (
          <div>
            {sources.map((s) => {
              const w = Math.round((s.count / maxSource) * 100);
              return (
                <div key={s.source} style={{ display: 'flex', alignItems: 'center', gap: '12px', fontSize: '0.875rem', marginBottom: '12px' }}>
                  <span style={{ width: 128, flexShrink: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', textAlign: 'right', color: '#6b7280' }} title={s.source}>{s.source}</span>
                  <div style={{ flex: 1, borderRadius: 9999, overflow: 'hidden', background: '#f3f4f6', height: 6 }}>
                    <div style={{ height: '100%', borderRadius: 9999, background: '#10b981', width: `${Math.max(4, w)}%` }} />
                  </div>
                  <span style={{ width: 32, flexShrink: 0, textAlign: 'right', color: '#9ca3af', fontSize: '0.75rem' }}>{s.count}</span>
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
    <div className="card card-hover" style={{ padding: '1.25rem' }}>
      <div style={{ fontSize: '0.75rem', color: '#9ca3af' }}>{label}</div>
      <div style={{ marginTop: '8px', fontSize: '1.5rem', fontWeight: 600, color: color || '#18181b' }}>{value}</div>
    </div>
  );
}
