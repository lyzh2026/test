import { cookies } from 'next/headers';

// SSR 统一走 Next 自身的代理路由（/api/proxy/*），不再直连后端，避免依赖 Docker 网络名。
// SELF_ORIGIN 为回环地址：容器内由 Next 监听 3000（见 Dockerfile PORT=3000 / package.json start -p 3000）。
const SELF_ORIGIN = process.env.INTERNAL_SELF_ORIGIN || 'http://127.0.0.1:3000';

export type ApiEnvelope<T = unknown> = {
  code: number;
  message: string;
  data: T | null;
  request_id?: string;
};

export class ServerApiError extends Error {
  code: number;
  status: number;
  constructor(code: number, message: string, status: number) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

export async function serverFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const cookieHeader = cookies()
    .getAll()
    .map((c) => `${c.name}=${c.value}`)
    .join('; ');

  const res = await fetch(`${SELF_ORIGIN}/api/proxy${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      cookie: cookieHeader,
      ...(init.headers || {}),
    },
    cache: 'no-store',
  });

  let body: ApiEnvelope<T>;
  try {
    body = (await res.json()) as ApiEnvelope<T>;
  } catch {
    throw new ServerApiError(res.status, res.statusText || 'invalid response', res.status);
  }

  if (!body || typeof body.code !== 'number') {
    throw new ServerApiError(res.status, 'unexpected response', res.status);
  }
  if (body.code !== 0) {
    throw new ServerApiError(body.code, body.message || 'error', res.status);
  }
  return body.data as T;
}
