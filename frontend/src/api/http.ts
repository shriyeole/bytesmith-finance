/**
 * Single fetch wrapper for the API. Same-origin `/api/v1` (Vite proxy in dev,
 * Firebase Hosting rewrite in production) and a Bearer token on every call.
 */

export const API_BASE = '/api/v1';

export class ClientError extends Error {
  status: number;
  details?: unknown;

  constructor(status: number, message: string, details?: unknown) {
    super(message);
    this.name = 'ClientError';
    this.status = status;
    this.details = details;
  }
}

type TokenGetter = () => Promise<string | null>;
let tokenGetter: TokenGetter = async () => null;

/** Called once by the app shell so every request carries the signed-in user's token. */
export function setTokenGetter(getter: TokenGetter): void {
  tokenGetter = getter;
}

function messageFrom(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object' && typeof (detail as { message?: unknown }).message === 'string') {
    return (detail as { message: string }).message;
  }
  if (Array.isArray(detail)) {
    return detail
      .map((item: { loc?: (string | number)[]; msg?: string }) => {
        const field = item.loc ? item.loc.filter((p) => p !== 'body').join('.') : '';
        return field ? `${field}: ${item.msg}` : item.msg;
      })
      .filter(Boolean)
      .join('; ');
  }
  return `Request failed with status ${status}`;
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = await tokenGetter();
  const headers: Record<string, string> = {
    Accept: 'application/json',
    ...(init.body ? { 'Content-Type': 'application/json' } : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(init.headers as Record<string, string> | undefined),
  };

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  } catch (err) {
    throw new ClientError(0, `Cannot reach the API server. Is the backend running? (${err instanceof Error ? err.message : 'network error'})`);
  }

  if (response.status === 204) return undefined as T;
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    /* empty or non-JSON body */
  }
  if (!response.ok) throw new ClientError(response.status, messageFrom(body, response.status), body);
  return body as T;
}

/** Like apiFetch but resolves to null on 404 (resource not created yet). */
export async function apiFetchOrNull<T>(path: string, init: RequestInit = {}): Promise<T | null> {
  try {
    return await apiFetch<T>(path, init);
  } catch (err) {
    if (err instanceof ClientError && err.status === 404) return null;
    throw err;
  }
}
