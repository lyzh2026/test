import Link from 'next/link';
import WeChatPreview from '@/components/wechat/WeChatPreview';
import { serverFetch, ServerApiError } from '@/lib/server-fetch';

export const dynamic = 'force-dynamic';

export default async function WeChatPage({ params }: { params: { id: string } }) {
  let data: { article_id: string; title: string; html: string; template: string } | null = null;
  let errorMsg = '';

  try {
    data = await serverFetch(`/api/v1/wechat/format/${params.id}?template=green-simple`);
  } catch (e: unknown) {
    if (e instanceof ServerApiError) {
      errorMsg = e.message;
    } else {
      errorMsg = '加载失败，请稍后重试';
    }
  }

  return (
    <main className="min-h-screen p-8 animate-fade-in">
      <div className="mb-6">
        <Link href={`/articles/${params.id}`} className="text-sm text-text-secondary hover:text-text-primary transition-colors">
          ← 返回文章详情
        </Link>
      </div>

      <h1 className="mb-6 text-lg font-semibold text-text-primary">
        AI 微信推文
      </h1>

      {errorMsg ? (
        <div className="card p-8 text-center" style={{ background: 'rgba(239, 68, 68, 0.05)' }}>
          <p style={{ color: '#e45a5a' }}>{errorMsg}</p>
          <Link href={`/articles/${params.id}`} className="mt-4 inline-block text-sm text-text-secondary hover:text-text-primary transition-colors">
            ← 返回文章详情
          </Link>
        </div>
      ) : data ? (
        <WeChatPreview
          articleId={params.id}
          articleTitle={data.title}
          initialHtml={data.html}
          initialTemplate={data.template}
        />
      ) : null}
    </main>
  );
}
