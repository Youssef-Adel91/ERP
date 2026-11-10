# Trust Core ERP — Security Architecture & Roadmap

This document outlines the security architecture, threat model, authentication token lifecycle, and implementation roadmap for Trust Core ERP.

---

## 1. Current Authentication Architecture

### 1.1 Token Mechanics
- **Access Tokens**: Short-lived JSON Web Tokens (JWT, HS256), expiring in 15 minutes.
  - Claims: `sub` (User UUID), `tenant_id` (Tenant UUID), `roles` (list of UserRole strings), `type` ("access"), `iat`, `exp`.
  - Type isolation: `decode_token` strictly validates `type == "access"`. Portal customer tokens (`type == "portal_access"`) are rejected if supplied to internal staff endpoints.
- **Refresh Tokens**: Opaque random UUID tokens stored server-side in Redis with a 7-day TTL.
  - Refresh rotation: Every call to `POST /api/v1/auth/refresh` revokes the supplied refresh token and issues a new one.
  - Reuse detection: If an already-revoked refresh token is re-submitted, Redis flags token reuse and revokes **all** active refresh tokens for that user immediately.
- **Storage in Current Build**:
  - Frontend stores `access_token` and `refresh_token` in `localStorage` (when "Remember Me" is checked) or `sessionStorage` (for single-session login).

---

## 2. Risk Assessment: `localStorage` vs. `httpOnly` Cookies

### 2.1 The Vulnerability Surface of `localStorage`
- **XSS Exposure**: JavaScript executing in the browser origin can read `localStorage.getItem("access_token")` and `localStorage.getItem("refresh_token")`.
- If an XSS vulnerability exists (e.g. through unsanitized third-party packages or rich text injection), an attacker can exfiltrate tokens and impersonate the user until expiry/revocation.

### 2.2 The Cross-Origin Localhost & Next.js 16 Architectural Challenge
Moving refresh tokens to an `httpOnly` cookie in the current decoupled development architecture (`localhost:3000` frontend, `localhost:8000` backend) introduces significant cross-origin and SSR constraints:
1. **Port Separation & SameSite Policies**:
   - `localhost:3000` and `localhost:8000` are distinct origins.
   - A cookie set by `:8000` with `SameSite=Lax` will **not** be attached to cross-origin asynchronous requests (Axios / Fetch) from `:3000` to `:8000`.
   - Setting `SameSite=None` requires the `Secure` attribute; however, modern Chromium and Safari reject `SameSite=None; Secure` over plain HTTP (`http://localhost`).
2. **Next.js 16 App Router & Hydration Races**:
   - If the access token is kept strictly in-memory (Zustand non-persisted store), every hard reload (F5) or direct URL hit to `/dashboard/*` begins with `null` state.
   - If the client-side app attempts to render protected pages before the asynchronous `/auth/refresh` cookie handshake completes, pages experience hydration mismatches, flicker, or premature redirection to `/login`.
3. **Backend-for-Frontend (BFF) Requirement**:
   - The cleanest, industry-standard pattern for Next.js App Router is a **BFF Proxy**: frontend route handlers (`/api/auth/*`) run on the same origin (`:3000`), receive the backend's cookie, and manage SSR session tokens seamlessly.
   - Attempting a partial, half-implemented cookie setup directly from `:8000` without the BFF layer causes cross-origin session dropping in dev and fragile hydration.

---

## 3. Phased Implementation Plan for httpOnly Cookie Migration

### Phase 1: Backend Cookie Delivery (Ready for BFF)
1. **Login & Refresh Endpoints**:
   - `POST /api/v1/auth/login` and `POST /api/v1/auth/refresh` set the `refresh_token` in an `httpOnly` cookie:
     ```python
     response.set_cookie(
         key="refresh_token",
         value=new_refresh_token,
         httponly=True,
         samesite="lax" if settings.ENVIRONMENT == "development" else "strict",
         secure=settings.ENVIRONMENT == "production",
         path="/api/v1/auth",
         max_age=7 * 24 * 3600,
     )
     ```
   - The response body returns `{ "access_token": "...", "expires_in": 900 }` (refresh token omitted from body).
2. **Logout Endpoint**:
   - `POST /api/v1/auth/logout` revokes the token in Redis and clears the cookie:
     ```python
     response.delete_cookie(key="refresh_token", path="/api/v1/auth")
     ```

### Phase 2: Next.js Backend-for-Frontend (BFF) Proxy
1. **Next.js Route Handlers**:
   - Create `src/app/api/auth/[...path]/route.ts` proxying `/api/auth/*` requests to FastAPI on `http://127.0.0.1:8000/api/v1/auth/*`.
   - Because the browser communicates solely with `localhost:3000/api/auth/*`, requests are **same-origin**.
   - `SameSite=Lax` works reliably across all browsers without requiring HTTPS on dev.
2. **In-Memory Token Store**:
   - `useAppStore` holds `accessToken` in memory only.
   - On initial page load / refresh, an `AuthProvider` initiates `POST /api/auth/refresh` to rehydrate the access token in memory before mounting dashboard routes.
   - Axios request interceptor attaches `Authorization: Bearer ${inMemoryToken}`.
   - Axios response interceptor on 401 triggers token refresh and replays failed requests.

### Phase 3: Production Hardening
1. **CSRF Protection**:
   - When using cookies for state mutation, double-submit CSRF cookie or custom headers (`X-Requested-With`) are enforced on mutating auth endpoints.
2. **Content Security Policy (CSP)**:
   - Configure strict CSP headers in `next.config.ts`:
     - Disallow inline script execution (`unsafe-inline`).
     - Restrict `connect-src` strictly to configured ERP API origins.

---

## 4. Current Mitigations & Safeguards

While migration to Phase 2 is staged, the following controls protect user tokens:
1. **15-Minute Access Token Lifetime**: Stolen access tokens expire automatically in 15 minutes.
2. **Redis Reuse Detection**: Stolen refresh tokens can only be used once; subsequent attempts trigger instant tenant-wide user token invalidation.
3. **Role Gates (`RequireRoleForWrites`)**: State-changing endpoints are strictly guarded against unauthorized roles.
4. **Tenant Isolation**: Schema-level PostgreSQL isolation ensures one tenant's queries can never access or modify another tenant's schema even if an access token is forged or leaked.
