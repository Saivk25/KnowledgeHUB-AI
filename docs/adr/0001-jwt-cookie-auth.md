# ADR-0001: JWT access token delivered via httpOnly cookie

**Status:** Accepted (MVP)

**Decision:** Authenticate users with a JWT (HS256), issued on register/login,
delivered as an httpOnly, SameSite=Lax cookie, and also returned in the
response body for non-browser API clients.

**Alternatives considered:**
- **Server-side sessions (Redis-backed):** simple to revoke, but adds a
  stateful dependency the MVP doesn't otherwise need, and complicates
  horizontal scaling of the API.
- **JWT in `localStorage`, read by JS on every request:** avoids CSRF cookie
  concerns but exposes the token to XSS; httpOnly cookies are the safer
  default for a browser-first product.

**Why this wins for the MVP:** stateless verification means any API replica
can validate a request without a shared session store — the natural setup
for the Docker Compose deployment and for later horizontal scaling. httpOnly
cookies keep the token out of reach of injected scripts, which matters more
than CSRF risk for a same-site SPA + API pair.

**MVP impact:** one `access_token` cookie, one `Authorization: Bearer`
fallback for tooling/tests, 24h expiry, no refresh-token rotation.

**Revisit when:** the product needs immediate token revocation (e.g. "log
out everywhere"), multi-device session management, or SSO/SAML — at which
point a session store or short-lived-token + refresh-token pair replaces
this (Phase 2/enterprise roadmap).
