import { cookies, headers as nextHeaders } from 'next/headers';

/** 服务端组件中通过 Next.js 自己的代理转发请求，
 *  避免对 Docker 内部主机名 (fastapi) 的硬编码依赖。 */
async function getProxyBase(): Promise<string> {
  // 优先使用环境变量指定的代理基址（用于自定义部署场景）
  const cfg = process.env.SERVER_PROXY_BASE;
  if (cfg) return cfg.replace(/\/+$/, '');
  // 自动探测：从请求头获取当前主机地址
  try {
    const h = nextHeaders();
    const host = h.get('host') || 'localhost:3000';
    // 判断是否 HTTPS
    const proto = h.get('x-forwarded-proto') || 'http';
    return `${proto}://${host}`;
  } catch {
    return 'http://localhost:3000';
  }
}

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

  const base = await getProxyBase();
  // 走 Next.js 代理路由，而非直连后端
  const proxyPath = path.startsWith('/') ? `/api/proxy${path}` : `/api/proxy/${path}`;
  const url = `${base}${proxyPath}`;

  const res = await fetch(url, {
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
