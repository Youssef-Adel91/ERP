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

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

/** Persists the auth token + active tenant for subsequent requests. */
export function saveSession(accessToken: string, tenantId: string, refreshToken?: string) {
  if (typeof window === "undefined") return;
  localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
  localStorage.setItem(TENANT_ID_KEY, tenantId);
  if (refreshToken) localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
}

/** Clears all locally-stored auth state. */
export function clearSessionStorage() {
  if (typeof window === "undefined") return;
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
  localStorage.removeItem(TENANT_ID_KEY);
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

  try {
    const { data } = await axios.post(`${API_BASE_URL}/auth/refresh`, {
      refresh_token: refreshToken,
    });
    saveSession(data.access_token, localStorage.getItem(TENANT_ID_KEY) ?? "", data.refresh_token);
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
  const detail = (error.response.data as { detail?: string } | undefined)?.detail;
  return typeof detail === "string" && detail.length > 0 ? detail : fallback;
}
