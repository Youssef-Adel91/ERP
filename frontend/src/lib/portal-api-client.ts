/**
 * portalApiClient — separate axios instance for the customer-facing Client
 * Portal (OTP login, invoice list/pay).
 *
 * This is intentionally NOT the same `apiClient` used by the staff
 * dashboard (see `@/lib/api-client`):
 *   - Portal tokens are a distinct JWT type (`type: "portal_access"`, see
 *     backend `app/modules/portal/api/auth.py`'s `get_portal_contact`)
 *     that the staff API's own auth explicitly rejects, and vice versa —
 *     sharing one axios instance/token store between the two surfaces
 *     would let a stray token from one silently break the other.
 *   - There is no `/portal/auth/refresh` endpoint. The portal token is a
 *     single 24h-lived JWT with no refresh flow, so — unlike `apiClient`
 *     — this client does not attempt a refresh-and-retry on 401; it just
 *     clears the session and sends the customer back to /portal/login.
 *   - Storage keys are namespaced ("portal_...") so a customer and a
 *     staff member can never collide/share a session in the same browser
 *     (e.g. a merchant testing their own portal link while logged into
 *     the dashboard in another tab).
 */
import axios, { AxiosError, type InternalAxiosRequestConfig } from "axios";

export const PORTAL_API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export const portalApiClient = axios.create({
  baseURL: PORTAL_API_BASE_URL,
  headers: { "Content-Type": "application/json" },
});

const PORTAL_TOKEN_KEY = "portal_access_token";
const PORTAL_TENANT_KEY = "portal_tenant_id";
const PORTAL_PHONE_KEY = "portal_phone_e164";

/**
 * The access token itself lives only in sessionStorage (cleared when the
 * tab/browser closes) — deliberately more conservative than the staff
 * dashboard's "remember me" option, since this is a bearer credential for
 * the customer's own billing data with no refresh flow to quietly
 * re-issue it if it leaks. The tenant id and phone number are
 * convenience-only (not secrets, needed again for a future OTP request)
 * and are kept in localStorage so a returning customer doesn't have to
 * retype them.
 */
export function getPortalToken(): string | null {
  if (typeof window === "undefined") return null;
  return sessionStorage.getItem(PORTAL_TOKEN_KEY);
}

export function getPortalTenantId(): string | null {
  if (typeof window === "undefined") return null;
  return sessionStorage.getItem(PORTAL_TENANT_KEY) ?? localStorage.getItem(PORTAL_TENANT_KEY);
}

export function getPortalPhone(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(PORTAL_PHONE_KEY);
}

export function savePortalContact(tenantId: string, phoneE164: string) {
  if (typeof window === "undefined") return;
  localStorage.setItem(PORTAL_TENANT_KEY, tenantId);
  localStorage.setItem(PORTAL_PHONE_KEY, phoneE164);
}

export function savePortalSession(token: string, tenantId: string, phoneE164: string) {
  if (typeof window === "undefined") return;
  sessionStorage.setItem(PORTAL_TOKEN_KEY, token);
  sessionStorage.setItem(PORTAL_TENANT_KEY, tenantId);
  savePortalContact(tenantId, phoneE164);
}

export function clearPortalSession() {
  if (typeof window === "undefined") return;
  sessionStorage.removeItem(PORTAL_TOKEN_KEY);
  sessionStorage.removeItem(PORTAL_TENANT_KEY);
}

portalApiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = getPortalToken();
  if (token) {
    config.headers.set("Authorization", `Bearer ${token}`);
  }
  return config;
});

portalApiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    if (error.response?.status === 401) {
      clearPortalSession();
      if (typeof window !== "undefined" && !window.location.pathname.startsWith("/portal/login")) {
        window.location.href = "/portal/login";
      }
    }
    return Promise.reject(error);
  },
);
