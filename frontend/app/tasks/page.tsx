import Link from 'next/link';
import { serverFetch } from '@/lib/server-fetch';
import { TaskTable } from '@/components/tasks/TaskTable';

type Task = {
  id: string;
  task_name: string | null;
  target_date: string;
  date_to: string | null;
  total_urls: number;
  completed_urls: number;
  failed_urls: number;
  status: string;
  created_at: string;
};

type TaskListResp = { items: Task[]; limit: number; offset: number };

export default async function TasksPage() {
  let resp: TaskListResp | null = null;
  let errorMsg: string | null = null;
  try {
    resp = await serverFetch<TaskListResp>('/api/v1/crawler/tasks?limit=50');
  } catch (e) {
    errorMsg = (e as Error).message;
  }
  const items = resp?.items || [];

  return (
    <main className="min-h-screen p-8 animate-fade-in">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold" style={{ color: '#e8e9ed' }}>任务列表</h1>
          <p className="mt-1.5 text-sm" style={{ color: '#6b6d7b' }}>管理与监控采集任务</p>
        </div>
        <Link href="/tasks/new" className="btn-primary">
          + 新建任务
        </Link>
      </div>

      {errorMsg && (
        <div className="mb-6 rounded-[12px] px-4 py-2.5 text-sm" style={{ background: 'rgba(228, 90, 90, 0.08)', color: '#e45a5a', border: '1px solid rgba(228, 90, 90, 0.15)' }}>
          加载失败：{errorMsg}
        </div>
      )}

      <TaskTable items={items} />
    </main>
  );
}
