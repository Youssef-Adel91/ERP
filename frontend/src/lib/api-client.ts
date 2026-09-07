/**
 * apiClient — axios instance wired to the real Omni ERP FastAPI backend.
 *
 * - Base URL comes from NEXT_PUBLIC_API_URL (defaults to http://localhost:8000/api/v1).
 * - Every request gets `Authorization: Bearer <access_token>` from localStorage.
 * - On a 401, we try exactly once to exchange the refresh token for a new
 *   access token (POST /auth/refresh) and replay the original request.
 *   If that fails too, the session is cleared and the user is sent to /login.
 */
import axios, { AxiosError, type InternalAxiosRequestConfig } from "axios";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: { "Content-Type": "application/json" },
});

const ACCESS_TOKEN_KEY = "access_token";
const REFRESH_TOKEN_KEY = "refresh_token";
const TENANT_ID_KEY = "tenant_id";

/**
 * Storage abstraction for the three auth keys (access token, refresh token,
 * tenant id). "remember me" checked -> persisted in localStorage (survives
 * browser restarts). Unchecked -> sessionStorage only (cleared when the tab/
 * browser closes). Every read/write/clear for these keys MUST go through
 * these helpers so persist=true and persist=false sessions can never end up
 * inconsistent (e.g. a read that only checks localStorage while a
 * session-only login wrote to sessionStorage).
 */
function readKey(key: string): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(key) ?? sessionStorage.getItem(key);
}

function writeKey(key: string, value: string, persist: boolean) {
  if (typeof window === "undefined") return;
  if (persist) {
    localStorage.setItem(key, value);
    sessionStorage.removeItem(key); // no stale duplicate in the other storage
  } else {
    sessionStorage.setItem(key, value);
    localStorage.removeItem(key); // don't leave a persisted token behind either
  }
}

function removeKeyBoth(key: string) {
  if (typeof window === "undefined") return;
  localStorage.removeItem(key);
  sessionStorage.removeItem(key);
}

export function getAccessToken(): string | null {
  return readKey(ACCESS_TOKEN_KEY);
}

export function getRefreshToken(): string | null {
  return readKey(REFRESH_TOKEN_KEY);
}

export function getTenantId(): string | null {
  return readKey(TENANT_ID_KEY);
}

/**
 * Persists the auth token + active tenant for subsequent requests.
 * `persist` mirrors the login page's "remember me" checkbox: true (default)
 * writes to localStorage so the session survives a browser restart; false
 * writes to sessionStorage only, so it's cleared when the tab/browser closes.
 */
export function saveSession(
  accessToken: string,
  tenantId: string,
  refreshToken?: string,
  persist = true,
) {
  if (typeof window === "undefined") return;
  writeKey(ACCESS_TOKEN_KEY, accessToken, persist);
  writeKey(TENANT_ID_KEY, tenantId, persist);
  if (refreshToken) writeKey(REFRESH_TOKEN_KEY, refreshToken, persist);
}

/** Clears all locally-stored auth state, from both localStorage and sessionStorage. */
export function clearSessionStorage() {
  if (typeof window === "undefined") return;
  removeKeyBoth(ACCESS_TOKEN_KEY);
  removeKeyBoth(REFRESH_TOKEN_KEY);
  removeKeyBoth(TENANT_ID_KEY);
}

apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = getAccessToken();
  if (token) {
    config.headers.set("Authorization", `Bearer ${token}`);
  }
  return config;
});

let refreshPromise: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return null;

  // Preserve whichever persistence mode the original login used: if the
  // current access token lives in localStorage, the refreshed one should
  // too (and vice versa for a session-only login).
  const persist = typeof window !== "undefined" && localStorage.getItem(ACCESS_TOKEN_KEY) !== null;

  try {
    const { data } = await axios.post(`${API_BASE_URL}/auth/refresh`, {
      refresh_token: refreshToken,
    });
    saveSession(data.access_token, getTenantId() ?? "", data.refresh_token, persist);
    return data.access_token as string;
  } catch {
    return null;
  }
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as (InternalAxiosRequestConfig & { _retry?: boolean }) | undefined;

    if (error.response?.status === 401 && original && !original._retry) {
      original._retry = true;

      refreshPromise ??= refreshAccessToken().finally(() => {
        refreshPromise = null;
      });
      const newToken = await refreshPromise;

      if (newToken) {
        original.headers.set("Authorization", `Bearer ${newToken}`);
        return apiClient(original);
      }

      clearSessionStorage();
      if (typeof window !== "undefined") {
        window.location.href = "/login";
      }
    }

    return Promise.reject(error);
  },
);

/**
 * getApiErrorMessage — the single place that turns an axios error into a
 * user-facing Arabic message.
 *
 * Before this, every dashboard page had its own `catch { setError("تعذر
 * تحميل ... تحقق من اتصال الخادم.") }`, so a 401 (session expired), a real
 * network outage, and a 500 from the server all produced the exact same
 * "check your connection" message — which is wrong for two of the three
 * cases and unhelpful for debugging.
 *
 * Usage in a page:
 *   } catch (err) {
 *     setError(getApiErrorMessage(err, "تعذر تحميل البيانات."));
 *   }
 *
 * Note: 401 is already handled globally by the response interceptor above
 * (token refresh, then redirect to /login on failure), so callers rarely
 * see a 401 reach their own catch block — this branch exists as a safety
 * net for the brief window before that redirect completes.
 */
export function getApiErrorMessage(error: unknown, fallback = "حدث خطأ غير متوقع."): string {
  if (!axios.isAxiosError(error)) {
    return fallback;
  }

  if (error.code === "ERR_NETWORK" || !error.response) {
    return "تعذر الاتصال بالخادم، تأكد من اتصالك بالإنترنت.";
  }

  const status = error.response.status;

  if (status === 401) {
    return "انتهت صلاحية جلستك، يتم تحويلك لتسجيل الدخول...";
  }

  if (status === 403) {
    return "ليس لديك صلاحية للقيام بهذا الإجراء.";
  }

  if (status === 404) {
    return "العنصر المطلوب غير موجود.";
  }

  if (status >= 500) {
    return "حدث خطأ في الخادم، حاول مرة أخرى.";
  }

  // 4xx other than the above: prefer the server's own detail message if
  // present (these are usually intentional, user-facing validation errors),
  // otherwise fall back to the caller-provided message.
  return extractDetailString(error.response.data) ?? fallback;
}

/**
 * extractDetailString — safely turns a FastAPI error body's `detail` field
 * into a displayable string, whatever shape it happens to be.
 *
 * `detail` is a string for `HTTPException(detail="...")` (the common case
 * every page was written against), but FastAPI's *own* validation layer
 * (Pydantic, on a 422) returns `detail` as an ARRAY of objects instead:
 * `[{type, loc, msg, input, ctx}, ...]`. Every page in this app that did
 * `err.response?.data?.detail || "fallback"` and rendered the result
 * directly as `{errorMsg}` was one malformed request away from crashing
 * with "Objects are not valid as a React child" — reproduced live via
 * `/register` (a too-short/invalid password trips backend validation
 * before the frontend's zod check ever gets a chance to catch it).
 */
function extractDetailString(data: unknown): string | undefined {
  const detail = (data as { detail?: unknown } | undefined)?.detail;

  if (typeof detail === "string" && detail.length > 0) {
    return detail;
  }

  if (Array.isArray(detail) && detail.length > 0) {
    const messages = detail
      .map((item) => (item && typeof item === "object" && "msg" in item ? String((item as { msg: unknown }).msg) : null))
      .filter((msg): msg is string => !!msg);
    if (messages.length > 0) {
      return messages.join("، ");
    }
  }

  return undefined;
}

/**
 * pickDetail — drop-in replacement for the unsafe
 * `err.response?.data?.detail || "fallback"` pattern used throughout the
 * dashboard's mutation `onError` handlers. Accepts the raw error (not
 * `.response.data.detail` — the whole error object), same as
 * `getApiErrorMessage`, but does NOT override with generic 401/403/500
 * copy — callers using this pattern want the server's specific validation
 * message when there is one, falling back to their own copy otherwise.
 */
export function pickDetail(error: unknown, fallback: string): string {
  if (!axios.isAxiosError(error)) return fallback;
  return extractDetailString(error.response?.data) ?? fallback;
}
