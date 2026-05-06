import Link from 'next/link';
import { notFound } from 'next/navigation';
import { BookmarkButton } from '@/components/articles/BookmarkButton';
import { CategoryEditor } from '@/components/articles/CategoryEditor';
import { ReanalyzeButton } from '@/components/articles/ReanalyzeButton';
import { DeleteArticleButton } from '@/components/articles/DeleteArticleButton';
import { EmailSendButton } from '@/components/articles/EmailSendButton';
import { ExportDocButton } from '@/components/articles/ExportDocButton';
import { DownloadLink } from '@/components/ui/DownloadLink';
import { serverFetch, ServerApiError } from '@/lib/server-fetch';
import { formatDate } from '@/lib/utils';

type Category = { label: string; confidence: number };
type Article = {
  id: string;
  task_id: string | null;
  original_title: string;
  source_unit: string | null;
  original_link: string;
  publish_date: string | null;
  status: string;
  failed_reason: string | null;
  raw_content: string | null;
  bookmarked: boolean;
  ai: {
    categories: Category[];
    summary: string;
    keywords: string[];
    model_used: string | null;
    processing_time_ms: number | null;
  };
  created_at: string;
  updated_at: string;
};

export const dynamic = 'force-dynamic';

export default async function ArticleDetailPage({ params }: { params: { id: string } }) {
  let article: Article | null = null;
  try {
    article = await serverFetch<Article>(`/api/v1/articles/${params.id}`);
  } catch (e) {
    if (e instanceof ServerApiError && e.status === 404) notFound();
    throw e;
  }
  if (!article) notFound();

  return (
    <main className="min-h-screen p-8 animate-fade-in">
      <div className="mb-6">
        <Link href="/articles" className="text-sm transition-colors" style={{ color: '#6b7280' }}>
          ← 返回文章列表
        </Link>
      </div>

      <article className="card p-8">
        <div className="mb-4 flex items-start gap-3">
          <h1 className="text-xl font-semibold flex-1" style={{ color: '#18181b' }}>{article.original_title}</h1>
          <BookmarkButton articleId={article.id} initialBookmarked={article.bookmarked} />
        </div>

        <div className="mb-5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs" style={{ color: '#9ca3af' }}>
          <span>{article.publish_date || '日期未识别'}</span>
          <span className="opacity-30">·</span>
          <span>{article.source_unit || '来源未识别'}</span>
          <span className="opacity-30">·</span>
          <span>状态：{article.status}</span>
          <ReanalyzeButton articleId={article.id} status={article.status} />
          {article.ai.model_used && (
            <>
              <span className="opacity-30">·</span>
              <span>模型：{article.ai.model_used}</span>
            </>
          )}
          {article.ai.processing_time_ms != null && (
            <>
              <span className="opacity-30">·</span>
              <span>分析耗时：{article.ai.processing_time_ms} ms</span>
            </>
          )}
        </div>

        <div className="mb-5">
          <CategoryEditor articleId={article.id} initialCategories={article.ai.categories} />
        </div>

        {article.ai.summary && (
          <section className="mb-6 rounded-[12px] p-5" style={{ background: '#f9fafb' }}>
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider" style={{ color: '#9ca3af' }}>AI 摘要</h2>
            <p className="text-sm leading-7" style={{ color: '#6b7280' }}>{article.ai.summary}</p>
            {article.ai.keywords.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2">
                {article.ai.keywords.map((k) => (
                  <span key={k} className="badge-gray">#{k}</span>
                ))}
              </div>
            )}
          </section>
        )}

        {article.failed_reason && (
          <div className="mb-5 rounded-[12px] px-4 py-2.5 text-sm" style={{ background: 'rgba(239, 68, 68, 0.08)', color: '#ef4444', border: '1px solid rgba(239, 68, 68, 0.15)' }}>
            失败原因：{article.failed_reason}
          </div>
        )}

        <div className="mb-6 flex items-center gap-4 text-sm">
          <a href={article.original_link} target="_blank" rel="noreferrer" className="transition-colors" style={{ color: '#3b82f6' }}>
            查看原文 ↗
          </a>
          <ExportDocButton articleId={article.id} />
          <EmailSendButton articleId={article.id} />
          <Link href={`/articles/${article.id}/wechat`} className="btn-primary">
            微信推文 →
          </Link>
          <DownloadLink
            href={`/api/proxy/api/v1/wechat/export/markdown/${article.id}`}
            filename={`${article.original_title || '文章'}.md`}
            className="btn-secondary"
          >
            下载 Markdown
          </DownloadLink>
          <DownloadLink
            href={`/api/proxy/api/v1/wechat/export/html/${article.id}`}
            filename={`${article.original_title || '文章'}.html`}
            className="btn-secondary"
          >
            下载 HTML
          </DownloadLink>
          <span className="ml-auto"><DeleteArticleButton articleId={article.id} /></span>
        </div>

        {article.raw_content && (
          <section>
            <h2 className="mb-3 text-sm font-medium" style={{ color: '#18181b' }}>原始正文</h2>
            <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap rounded-[12px] p-4 text-sm leading-7 font-mono" style={{ background: '#f9fafb', color: '#6b7280', boxShadow: 'inset 0 0 0 1px #e5e7eb' }}>
              {article.raw_content}
            </pre>
          </section>
        )}

        <div className="mt-6 flex justify-between text-xs" style={{ color: '#9ca3af' }}>
          <span>创建于 {formatDate(article.created_at)}</span>
          <span>更新于 {formatDate(article.updated_at)}</span>
        </div>
      </article>
    </main>
  );
}
