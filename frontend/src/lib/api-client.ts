/**
 * API Client for Trust Core ERP
 * Reads NEXT_PUBLIC_API_URL from env and attaches Authorization + X-Tenant-ID.
 * Surfaces FastAPI `detail` field as the thrown error message.
 */

const getBaseUrl = () =>
  process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';

const getAuthHeaders = (): Record<string, string> => {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };

  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('access_token');
    const tenantId = localStorage.getItem('tenant_id');

    if (token) headers['Authorization'] = `Bearer ${token}`;
    if (tenantId) headers['X-Tenant-ID'] = tenantId;
  }

  return headers;
};

/** Extracts a human-readable message from a FastAPI error response. */
async function extractError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body?.detail === 'string') return body.detail;
    if (Array.isArray(body?.detail)) {
      // Pydantic validation errors: [{loc, msg, type}]
      return body.detail.map((e: { msg: string }) => e.msg).join(' | ');
    }
  } catch {
    // ignore JSON parse failures
  }
  return res.statusText || `HTTP ${res.status}`;
}

export const apiClient = {
  get: async <T>(url: string): Promise<T> => {
    const fullUrl = url.startsWith('http') ? url : `${getBaseUrl()}${url}`;
    const res = await fetch(fullUrl, { method: 'GET', headers: getAuthHeaders() });
    if (!res.ok) throw new Error(await extractError(res));
    return res.json() as Promise<T>;
  },

  post: async <T>(url: string, data: unknown): Promise<T> => {
    const fullUrl = url.startsWith('http') ? url : `${getBaseUrl()}${url}`;
    const res = await fetch(fullUrl, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error(await extractError(res));
    return res.json() as Promise<T>;
  },

  patch: async <T>(url: string, data: unknown): Promise<T> => {
    const fullUrl = url.startsWith('http') ? url : `${getBaseUrl()}${url}`;
    const res = await fetch(fullUrl, {
      method: 'PATCH',
      headers: getAuthHeaders(),
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error(await extractError(res));
    return res.json() as Promise<T>;
  },

  delete: async <T>(url: string): Promise<T> => {
    const fullUrl = url.startsWith('http') ? url : `${getBaseUrl()}${url}`;
    const res = await fetch(fullUrl, { method: 'DELETE', headers: getAuthHeaders() });
    if (!res.ok) throw new Error(await extractError(res));
    return res.json() as Promise<T>;
  },
};

// ── Auth helpers ──────────────────────────────────────────────────────────────

export function saveSession(accessToken: string, tenantId: string) {
  localStorage.setItem('access_token', accessToken);
  localStorage.setItem('tenant_id', tenantId);
}

export function clearSession() {
  localStorage.removeItem('access_token');
  localStorage.removeItem('tenant_id');
  localStorage.removeItem('refresh_token');
}

export function getStoredToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('access_token');
}
