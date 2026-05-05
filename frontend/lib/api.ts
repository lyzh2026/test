'use client';

export type ApiEnvelope<T = unknown> = {
  code: number;
  message: string;
  data: T | null;
  request_id?: string;
};

export class ApiError extends Error {
  code: number;
  constructor(code: number, message: string) {
    super(message);
    this.code = code;
  }
}

async function apiRequest<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const url = path.startsWith('/') ? `/api/proxy${path}` : `/api/proxy/${path}`;
  const res = await fetch(url, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init.headers || {}),
    },
    cache: 'no-store',
    credentials: 'include',
  });
  let body: ApiEnvelope<T>;
  try {
    body = (await res.json()) as ApiEnvelope<T>;
  } catch {
    throw new ApiError(res.status, res.statusText || 'invalid response');
  }
  if (!body || typeof body.code !== 'number') {
    throw new ApiError(res.status, 'unexpected response');
  }
  if (body.code !== 0) {
    throw new ApiError(body.code, body.message || 'error');
  }
  return body.data as T;
}

export const api = {
  get: <T>(p: string) => apiRequest<T>(p, { method: 'GET' }),
  post: <T>(p: string, payload?: unknown) =>
    apiRequest<T>(p, { method: 'POST', body: payload ? JSON.stringify(payload) : undefined }),
  put: <T>(p: string, payload?: unknown) =>
    apiRequest<T>(p, { method: 'PUT', body: payload ? JSON.stringify(payload) : undefined }),
  patch: <T>(p: string, payload?: unknown) =>
    apiRequest<T>(p, { method: 'PATCH', body: payload ? JSON.stringify(payload) : undefined }),
  delete: <T>(p: string) => apiRequest<T>(p, { method: 'DELETE' }),
};
