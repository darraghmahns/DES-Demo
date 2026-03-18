/** Base HTTP client for D.E.S. API calls. */

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000';

let _getAuthToken: (() => Promise<string | null>) | null = null;

export function setAuthTokenProvider(getter: () => Promise<string | null>) {
  _getAuthToken = getter;
}

export { _getAuthToken };

async function authHeaders(): Promise<Record<string, string>> {
  if (!_getAuthToken) return {};
  const token = await _getAuthToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function apiFetch<T = unknown>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const auth = await authHeaders();
  const extra = (options.headers as Record<string, string>) || {};
  const headers: Record<string, string> = { ...auth, ...extra };

  // Don't set Content-Type for FormData (browser sets boundary)
  if (!(options.body instanceof FormData) && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (!res.ok) {
    const body = await res.text();
    let detail = body;
    try {
      const parsed = JSON.parse(body);
      if (typeof parsed.detail === 'string') {
        detail = parsed.detail;
      } else if (parsed.detail !== undefined) {
        detail = JSON.stringify(parsed.detail);
      } else {
        detail = body;
      }
    } catch { /* ignore */ }
    throw new Error(detail);
  }

  const text = await res.text();
  if (!text) return undefined as T;
  return JSON.parse(text) as T;
}

export function apiSSE(
  path: string,
  onEvent: (event: { type: string; data: unknown }) => void,
): () => void {
  let cancelled = false;

  (async () => {
    const headers = await authHeaders();
    const res = await fetch(`${API_BASE}${path}`, { headers });

    if (!res.ok || !res.body) return;

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (!cancelled) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed || trimmed.startsWith(':')) continue;
        if (trimmed.startsWith('data: ')) {
          try {
            const parsed = JSON.parse(trimmed.slice(6));
            onEvent(parsed);
          } catch { /* ignore parse errors */ }
        }
      }
    }
  })();

  return () => { cancelled = true; };
}

export { API_BASE };
