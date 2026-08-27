# ADR 0003 — Auth strategy: NewLife-style password-first JWT (no Microsoft OIDC)

## Status

Accepted (Phase 0, 2026-08-27)

## Context

Rooted v1 requires account-backed sync and fellowship (`rooted-docs` PRD §9.4, API spec §2). The codebase inherits JWT, password hashing, and admin RBAC patterns from the portal/NewLife lineage.

Product spec also describes **magic link** email login for end users. NewLife admin adds **Microsoft Entra ID** token exchange — that flow serves church staff SSO, not Rooted’s consumer devotional audience, and would add OIDC configuration and user-provisioning rules we do not need.

## Decision

1. **Primary credential model (shared infrastructure):** email + **password** with JWT access and refresh tokens, implemented using the same provider patterns as NewLife (password hash, `JWTProvider`, refresh rotation/blacklist as enabled).
2. **Admin operators** authenticate via admin login endpoints under `/admin/api/v1/auth` with RBAC — password-first; no Microsoft/OIDC login for Rooted admin in v1.
3. **App end users** expose password registration/login **and** magic-link endpoints per `rooted-docs/docs/backend/api-specification.md`; magic link is an additional factorless channel, not a separate auth stack.
4. **Explicitly out of scope:** Microsoft Entra ID / Azure AD token exchange, generic OIDC social login, and NewLife-style `MicrosoftAuthService`.
5. **Token policy:** follow product ranges (access ~15–60 minutes, refresh ~7–30 days) via configuration; clients send `Authorization: Bearer`.
6. **Anonymous access:** allow unauthenticated reads where the API spec marks devotion/bible as client-first; fellowship and journal require member JWT.

## Consequences

- No OIDC client secrets or Entra app registration in Rooted deployments.
- Auth application services live under `portal/application/auth/` as migration proceeds; legacy middleware remains until routers delegate to services.
- Magic link implementation must reuse the same user records and JWT issuance as password login.
- If enterprise SSO is ever required, it demands a new ADR — it is not a silent port from `newlife-core-api`.
