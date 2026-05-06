import Link from 'next/link';
import { serverFetch } from '@/lib/server-fetch';
import { ArticleListClient } from '@/components/articles/BatchDeleteBar';
import { DateField } from '@/components/ui/DateField';

type Category = { label: string; confidence: number };
type ArticleItem = {
  id: string;
  task_id: string | null;
  original_title: string;
  source_unit: string | null;
  original_link: string;
  publish_date: string | null;
  status: string;
  bookmarked: boolean;
  ai: {
    categories: Category[];
    summary: string;
    keywords: string[];
  };
  created_at: string;
};

type ArticleListResp = { items: ArticleItem[]; total: number; limit: number; offset: number };

export const dynamic = 'force-dynamic';

async function fetchCategories(): Promise<string[]> {
  try {
    const data = await serverFetch<{ labels: string[] }>('/api/v1/articles/category-labels');
    return data.labels || [];
  } catch {
    return [];
  }
}

export default async function ArticlesPage({
  searchParams,
}: {
  searchParams: { date_from?: string; date_to?: string; category?: string; keyword?: string; status?: string; bookmarked?: string; task_id?: string; offset?: string };
}) {
  const offset = parseInt(searchParams.offset || '0', 10) || 0;
  const limit = 30;
  const params = new URLSearchParams();
  params.set('limit', String(limit));
  params.set('offset', String(offset));
  if (searchParams.date_from) params.set('date_from', searchParams.date_from);
  if (searchParams.date_to) params.set('date_to', searchParams.date_to);
  if (searchParams.category) params.set('category', searchParams.category);
  if (searchParams.keyword) params.set('keyword', searchParams.keyword);
  if (searchParams.status) params.set('status', searchParams.status);
  if (searchParams.bookmarked === '1') params.set('bookmarked', 'true');
  if (searchParams.task_id) params.set('task_id', searchParams.task_id);

  let resp: ArticleListResp | null = null;
  let errorMsg: string | null = null;
  try {
    resp = await serverFetch<ArticleListResp>(`/api/v1/articles?${params.toString()}`);
  } catch (e) {
    errorMsg = (e as Error).message;
  }
  const items = resp?.items || [];
  const total = resp?.total || 0;
  const categories = await fetchCategories();

  const mkUrl = (off: number) => {
    const p = new URLSearchParams(params);
    p.set('offset', String(Math.max(0, off)));
    return `/articles?${p.toString()}`;
  };
  const prevHref = mkUrl(offset - limit);
  const nextHref = mkUrl(offset + limit);

  return (
    <main className="min-h-screen p-8 animate-fade-in">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold" style={{ color: '#18181b' }}>文章列表</h1>
        <p className="mt-1.5 text-sm" style={{ color: '#9ca3af' }}>
          {searchParams.task_id ? (
            <span>按任务筛选 · <Link href="/articles" className="underline" style={{ color: '#3b82f6' }}>清除筛选</Link></span>
          ) : (
            '浏览与管理采集的文章'
          )}
        </p>
      </div>

      {/* Filters */}
      <form method="GET" className="card mb-8 p-4">
        <div className="flex flex-wrap items-end gap-4">
          <DateField label="起始日期" name="date_from" defaultValue={searchParams.date_from} />
          <DateField label="结束日期" name="date_to" defaultValue={searchParams.date_to} />
          <Field label="分类">
            <select name="category" defaultValue={searchParams.category || ''} className="input w-32">
              <option value="">全部</option>
              {categories.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </Field>
          <Field label="关键词">
            <input name="keyword" defaultValue={searchParams.keyword} placeholder="标题" className="input w-40" />
          </Field>
          <Field label="状态">
            <select name="status" defaultValue={searchParams.status || ''} className="input w-32">
              <option value="">全部</option>
              <option value="raw">已抓取</option>
              <option value="analyzing">分析中</option>
              <option value="processed">已分析</option>
              <option value="failed_retryable">分析失败可重试</option>
              <option value="failed_permanent">分析失败</option>
            </select>
          </Field>
          <label className="flex items-center gap-2 pb-0.5 text-xs text-text-secondary cursor-pointer">
            <input type="checkbox" name="bookmarked" value="1" defaultChecked={searchParams.bookmarked === '1'}
              className="h-4 w-4 rounded border-gray-300" style={{ accentColor: '#3b82f6' }} />
            仅收藏
          </label>
          <div className="flex gap-2">
            <button type="submit" className="btn-primary">筛选</button>
            <Link href="/articles" className="btn-secondary">重置</Link>
          </div>
        </div>
      </form>

      {errorMsg && (
        <div className="mb-6 rounded-[12px] px-4 py-2.5 text-sm" style={{ background: 'rgba(239, 68, 68, 0.08)', color: '#ef4444', border: '1px solid rgba(239, 68, 68, 0.15)' }}>
          加载失败：{errorMsg}
        </div>
      )}

      <ArticleListClient items={items} total={total} limit={limit} offset={offset} prevHref={prevHref} nextHref={nextHref} />
    </main>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5 text-xs text-text-muted">
      <span>{label}</span>
      {children}
    </label>
  );
}
