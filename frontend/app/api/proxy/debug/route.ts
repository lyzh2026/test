import { NextResponse } from 'next/server';
import { execSync } from 'child_process';

export async function GET() {
  const results: Record<string, unknown> = {};

  // Test 1: execSync getent
  try {
    const out = execSync('getent hosts fastapi 2>&1', { timeout: 5000, encoding: 'utf-8' });
    results.getent = out.trim();
  } catch (e) {
    results.getent = 'EXEC_ERROR: ' + (e as Error).message;
  }

  // Test 2: execSync cat /etc/hosts
  try {
    const out = execSync('cat /etc/hosts 2>&1', { timeout: 5000, encoding: 'utf-8' });
    results.hosts = out;
  } catch (e) {
    results.hosts = 'EXEC_ERROR: ' + (e as Error).message;
  }

  // Test 3: URL parsing
  try {
    const u = new URL('http://fastapi:8000');
    results.urlHostname = u.hostname;
    results.urlPort = u.port;
    results.urlProtocol = u.protocol;
  } catch (e) {
    results.urlParse = (e as Error).message;
  }

  // Test 4: process.env
  results.apiBaseUrl = process.env.API_BASE_URL || '(not set)';

  return NextResponse.json(results);
}
