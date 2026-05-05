import { cookies } from 'next/headers';

const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000';

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

  const res = await fetch(`${API_BASE}${path}`, {
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
