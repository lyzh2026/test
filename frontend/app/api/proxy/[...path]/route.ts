import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';
import http from 'http';
import https from 'https';

// API_BASE 读取环境变量，支持两种场景：
//   Docker:    API_BASE_URL=http://fastapi:8000    (docker-compose 已设)
//   直接启动:  不设则默认 http://localhost:8000
//   裸机:      docker-compose 中已通过 extra_hosts 注入 host.docker.internal
const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000';

const HOP_BY_HOP = new Set([
  'connection',
  'keep-alive',
  'proxy-authenticate',
  'proxy-authorization',
  'te',
  'trailers',
  'transfer-encoding',
  'upgrade',
  'host',
  'content-length',
]);

async function fetchWithHttp(target: string, init: { method: string; headers: Record<string, string>; body?: string }): Promise<{ status: number; statusText: string; headers: Record<string, string | string[]>; body: string }> {
  return new Promise((resolve, reject) => {
    const u = new URL(target);
    const mod = u.protocol === 'https:' ? https : http;
    const body = init.body || '';

    const req = mod.request(
      {
        hostname: u.hostname,
        port: parseInt(u.port || (u.protocol === 'https:' ? '443' : '80')),
        path: u.pathname + u.search,
        method: init.method,
        headers: { ...init.headers, 'content-length': Buffer.byteLength(body).toString() },
      },
      (res) => {
        const chunks: Buffer[] = [];
        res.on('data', (c: Buffer) => chunks.push(c));
        res.on('end', () => {
          resolve({
            status: res.statusCode || 502,
            statusText: res.statusMessage || '',
            headers: res.headers as Record<string, string | string[]>,
            body: Buffer.concat(chunks).toString('utf-8'),
          });
        });
      },
    );
    req.on('error', reject);
    if (body) req.write(body);
    req.end();
  });
}

async function handle(req: NextRequest, ctx: { params: { path: string[] } }) {
  const subPath = (ctx.params.path || []).join('/');
  const search = req.nextUrl.searchParams.toString();
  const target = `${API_BASE}/${subPath}${search ? `?${search}` : ''}`;

  const headers: Record<string, string> = {};
  req.headers.forEach((v, k) => {
    if (!HOP_BY_HOP.has(k.toLowerCase()) && typeof v === 'string') headers[k] = v;
  });

  let bodyText = '';
  if (!['GET', 'HEAD'].includes(req.method)) {
    bodyText = await req.text();
  }

  try {
    const upstream = await fetchWithHttp(target, { method: req.method, headers, body: bodyText });

    const respHeaders = new Headers();
    for (const [k, v] of Object.entries(upstream.headers)) {
      if (!HOP_BY_HOP.has(k.toLowerCase()) && v) {
        respHeaders.set(k, Array.isArray(v) ? v.join(', ') : v);
      }
    }

    return new NextResponse(upstream.body, {
      status: upstream.status,
      headers: respHeaders,
    });
  } catch (e) {
    return NextResponse.json(
      { code: 5002, message: `上游不可达：${(e as Error).message}`, data: { target }, request_id: null },
      { status: 502 },
    );
  }
}

export const GET = handle;
export const POST = handle;
export const PUT = handle;
export const PATCH = handle;
export const DELETE = handle;
export const OPTIONS = handle;
