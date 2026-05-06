'use client';

import { createContext, useContext, useState, useCallback, useRef, ReactNode } from 'react';

type ToastType = 'success' | 'error' | 'info';

interface ToastItem {
  id: number;
  message: string;
  type: ToastType;
}

interface ConfirmState {
  message: string;
  resolve: (value: boolean) => void;
}

const ToastContext = createContext<{
  toast: (message: string, type?: ToastType) => void;
  confirm: (message: string) => Promise<boolean>;
} | null>(null);

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used within ToastProvider');
  return ctx;
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const [confirmState, setConfirmState] = useState<ConfirmState | null>(null);
  const nextId = useRef(0);

  const toast = useCallback((message: string, type: ToastType = 'info') => {
    const id = nextId.current++;
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 3000);
  }, []);

  const confirm = useCallback((message: string) => {
    return new Promise<boolean>((resolve) => {
      setConfirmState({ message, resolve });
    });
  }, []);

  function handleConfirm(result: boolean) {
    if (confirmState) {
      confirmState.resolve(result);
      setConfirmState(null);
    }
  }

  return (
    <ToastContext.Provider value={{ toast, confirm }}>
      {children}

      {/* Toast 列表 */}
      <div className="fixed top-4 right-4 z-[9999] flex flex-col gap-2 pointer-events-none">
        {toasts.map((t) => (
          <div
            key={t.id}
            className="pointer-events-auto rounded-lg px-4 py-3 text-sm shadow-lg animate-slide-in-right"
            style={{
              background: t.type === 'success' ? '#f0fdf4' : t.type === 'error' ? '#fef2f2' : '#eff6ff',
              color: t.type === 'success' ? '#16a34a' : t.type === 'error' ? '#dc2626' : '#2563eb',
              border: `1px solid ${t.type === 'success' ? '#bbf7d0' : t.type === 'error' ? '#fecaca' : '#bfdbfe'}`,
              maxWidth: 360,
              animation: 'slide-in-right 0.2s ease-out',
            }}
          >
            {t.message}
          </div>
        ))}
      </div>

      {/* 确认弹窗 */}
      {confirmState && (
        <div className="fixed inset-0 z-[9998] flex items-center justify-center" style={{ background: 'rgba(0,0,0,0.3)' }}>
          <div
            className="card p-6 animate-fade-in"
            style={{ maxWidth: 400, width: '90%' }}
          >
            <p className="text-sm mb-6" style={{ color: '#18181b' }}>{confirmState.message}</p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => handleConfirm(false)}
                className="btn-secondary text-xs"
              >
                取消
              </button>
              <button
                onClick={() => handleConfirm(true)}
                className="btn-primary text-xs"
              >
                确认
              </button>
            </div>
          </div>
        </div>
      )}
    </ToastContext.Provider>
  );
}
