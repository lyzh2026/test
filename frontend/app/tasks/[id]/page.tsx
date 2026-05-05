import Link from 'next/link';
import { notFound } from 'next/navigation';
import { DeleteButton } from '@/components/tasks/DeleteButton';
import { RetryButton } from '@/components/tasks/RetryButton';
import { CancelButton } from '@/components/tasks/CancelButton';
import { TaskProgress } from '@/components/tasks/TaskProgress';
import { serverFetch, ServerApiError } from '@/lib/server-fetch';
import { formatDate } from '@/lib/utils';

type Task = {
  id: string;
  task_name: string | null;
  target_date: string;
  date_to: string | null;
  url_list: string[];
  total_urls: number;
  completed_urls: number;
  failed_urls: number;
  failed_details: { url: string; code: number; reason: string; stage?: string }[];
  status: string;
  priority: number;
  callback_url: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
};

const STATUS_BADGE: Record<string, string> = {
  pending: 'badge-gray',
  running: 'badge-amber',
  completed: 'badge-green',
  partial_failed: 'badge-amber',
  failed: 'badge-red',
  cancelled: 'badge-gray',
};

const STATUS_LABEL: Record<string, string> = {
  pending: '等待中',
  running: '运行中',
  completed: '已完成',
  partial_failed: '部分失败',
  failed: '失败',
  cancelled: '已取消',
};

const STAGE_BADGE: Record<string, string> = {
  render: 'badge-red',
  extract: 'badge-amber',
  validate: 'badge-gray',
  date_filter: 'badge-blue',
  dedup: 'badge-green',
};

export const dynamic = 'force-dynamic';

export default async function TaskDetailPage({ params }: { params: { id: string } }) {
  const id = params.id;
  if (!/^[a-f0-9-]+$/i.test(id)) notFound();

  let task: Task | null = null;
  try {
    task = await serverFetch<Task>(`/api/v1/crawler/tasks/${id}`);
  } catch (e) {
    if (e instanceof ServerApiError && e.status === 404) notFound();
    throw e;
  }
  if (!task) notFound();

  return (
    <main className="min-h-screen p-8 animate-fade-in">
      <div className="mb-6">
        <Link href="/tasks" className="text-sm transition-colors" style={{ color: '#6b7280' }}>
          ← 返回任务列表
        </Link>
      </div>

      <div className="card p-6 mb-6">
        <div className="flex items-start justify-between mb-6">
          <div>
            <h1 className="text-lg font-semibold" style={{ color: '#18181b' }}>{task.task_name || task.id}</h1>
            <p className="mt-1 text-sm" style={{ color: '#9ca3af' }}>{task.date_to ? `${task.target_date} ~ ${task.date_to}` : task.target_date} · 优先级 {task.priority}</p>
          </div>
          <div className="flex items-center gap-3">
            <span className={STATUS_BADGE[task.status] || 'badge-gray'}>
              {STATUS_LABEL[task.status] || task.status}
            </span>
            <CancelButton taskId={task.id} status={task.status} />
            <RetryButton taskId={task.id} status={task.status} />
            <DeleteButton taskId={task.id} />
          </div>
        </div>

        <TaskProgress
          taskId={task.id}
          initialCompleted={task.completed_urls}
          initialFailed={task.failed_urls}
          initialTotal={task.total_urls}
          initialStatus={task.status}
        />

        <div className="mt-5 grid grid-cols-2 gap-4 text-xs md:grid-cols-4" style={{ color: '#9ca3af' }}>
          <Field label="日期范围" value={task.date_to ? `${task.target_date} ~ ${task.date_to}` : task.target_date} />
          <Field label="开始时间" value={formatDate(task.started_at)} />
          <Field label="完成时间" value={formatDate(task.completed_at)} />
          <Field label="回调 URL" value={task.callback_url || '-'} />
        </div>
      </div>

      {task.failed_details.length > 0 && (
        <section className="card p-6 mb-6">
          <h2 className="mb-4 text-sm font-medium" style={{ color: '#18181b' }}>失败详情</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs" style={{ color: '#9ca3af' }}>
                <tr style={{ borderBottom: '1px solid #e5e7eb' }}>
                  <th className="pb-2 pr-4">URL</th>
                  <th className="pb-2 pr-4 w-20">code</th>
                  <th className="pb-2 pr-4 w-20">阶段</th>
                  <th className="pb-2">原因</th>
                </tr>
              </thead>
              <tbody>
                {task.failed_details.map((d, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid #e5e7eb' }}>
                    <td className="break-all py-2 pr-2 text-xs" style={{ color: '#6b7280' }}>{d.url}</td>
                    <td className="py-2 pr-4" style={{ color: '#ef4444' }}>{d.code}</td>
                    <td className="py-2 pr-4">{d.stage ? <span className={STAGE_BADGE[d.stage] || 'badge-gray'}>{d.stage}</span> : '-'}</td>
                    <td className="py-2 text-xs" style={{ color: '#6b7280' }}>{d.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section className="card p-6">
        <h2 className="mb-4 text-sm font-medium" style={{ color: '#18181b' }}>URL 清单（{task.url_list.length}）</h2>
        <ul className="max-h-96 space-y-1 overflow-y-auto text-xs">
          {task.url_list.map((u, i) => (
            <li key={i} className="break-all" style={{ color: '#6b7280' }}>
              <a href={u} target="_blank" rel="noreferrer" className="transition-colors" style={{ color: '#6b7280' }}>
                {u}
              </a>
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="mb-0.5" style={{ color: '#9ca3af' }}>{label}</div>
      <div className="break-all" style={{ color: '#6b7280' }}>{value}</div>
    </div>
  );
}
