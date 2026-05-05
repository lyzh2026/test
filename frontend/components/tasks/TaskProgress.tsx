'use client';
import { useEffect, useRef, useState } from 'react';

type ProgressData = {
  task_id: string;
  status: string;
  completed: number;
  failed: number;
  total: number;
  current_url: string | null;
  message: string | null;
};

const TERMINAL_STATUSES = ['completed', 'failed', 'partial_failed', 'cancelled'];

export function TaskProgress({
  taskId,
  initialCompleted,
  initialFailed,
  initialTotal,
  initialStatus,
}: {
  taskId: string;
  initialCompleted: number;
  initialFailed: number;
  initialTotal: number;
  initialStatus: string;
}) {
  const [prog, setProg] = useState({
    completed: initialCompleted,
    failed: initialFailed,
    total: initialTotal,
    status: initialStatus,
    currentUrl: null as string | null,
    message: null as string | null,
  });
  const wsRef = useRef<WebSocket | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const statusRef = useRef(initialStatus);

  // keep ref in sync so callbacks always read latest status
  useEffect(() => {
    statusRef.current = prog.status;
  }, [prog.status]);

  useEffect(() => {
    if (TERMINAL_STATUSES.includes(initialStatus)) return;

    function connectWs() {
      const wsBase = (window as any).NEXT_PUBLIC_WS_URL
        || `ws://${window.location.hostname}:8000`;
      const ws = new WebSocket(`${wsBase}/api/v1/crawler/ws/task/${taskId}`);

      ws.onmessage = (e) => {
        try {
          const data: ProgressData = JSON.parse(e.data);
          setProg((prev) => ({
            ...prev,
            completed: data.completed ?? prev.completed,
            failed: data.failed ?? prev.failed,
            total: data.total ?? prev.total,
            status: data.status ?? prev.status,
            currentUrl: data.current_url ?? prev.currentUrl,
            message: data.message ?? prev.message,
          }));
          if (TERMINAL_STATUSES.includes(data.status)) {
            ws.close();
          }
        } catch {
          // ignore malformed messages
        }
      };

      ws.onclose = () => {
        wsRef.current = null;
        if (!TERMINAL_STATUSES.includes(statusRef.current)) startPolling();
      };

      ws.onerror = () => {
        ws.close();
      };

      wsRef.current = ws;
    }

    function startPolling() {
      if (pollRef.current) return;
      pollRef.current = setInterval(async () => {
        try {
          const res = await fetch(`/api/proxy/api/v1/crawler/tasks/${taskId}`);
          const body = await res.json();
          if (body?.data) {
            const d = body.data;
            if (TERMINAL_STATUSES.includes(d.status)) {
              if (pollRef.current) clearInterval(pollRef.current);
              pollRef.current = null;
            }
            setProg((prev) => ({
              ...prev,
              completed: d.completed_urls,
              failed: d.failed_urls,
              total: d.total_urls,
              status: d.status,
            }));
          }
        } catch {
          // ignore
        }
      }, 3000);
    }

    connectWs();

    return () => {
      wsRef.current?.close();
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [taskId, initialStatus]);

  const done = prog.completed + prog.failed;
  const pct = prog.total > 0 ? Math.round((done / prog.total) * 100) : 0;
  const isFinished = TERMINAL_STATUSES.includes(prog.status);

  return (
    <div className="mt-6">
      <div className="mb-2 flex items-center justify-between text-xs" style={{ color: '#9ca3af' }}>
        <span>
          进度 {done} / {prog.total}
          {prog.failed > 0 && <span className="ml-2" style={{ color: '#ef4444' }}>失败 {prog.failed}</span>}
        </span>
        <span>{pct}%</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full" style={{ background: '#e5e7eb' }}>
        <div
          className="h-full rounded-full transition-all duration-300"
          style={{ width: `${pct}%`, background: '#3b82f6' }}
        />
      </div>

      {prog.currentUrl && !isFinished && (
        <p className="mt-2 truncate text-xs" style={{ color: '#9ca3af' }} title={prog.currentUrl}>
          正在抓取：{prog.currentUrl}
        </p>
      )}

      {prog.message && !isFinished && (
        <p className="mt-1 text-xs" style={{ color: '#9ca3af' }}>{prog.message}</p>
      )}
    </div>
  );
}
