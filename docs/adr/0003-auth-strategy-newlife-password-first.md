# ADR 0003 — Auth strategy: Admin password-first; app End users passwordless (magic link)

## Status

Accepted (Phase 0, 2026-08-27); **updated** (2026-09-05) for app passwordless.

Supersedes the earlier “app password + optional magic link” wording in this ADR. Durable Identity storage for future Apple/Google is ADR 0005 — this ADR does **not** authorize OIDC HTTP flows.

## Context

Rooted requires account-backed sync and fellowship (`rooted-docs` PRD §9.4, API spec §2). The codebase inherits JWT, password hashing, and admin RBAC patterns from the portal/NewLife lineage.

Product direction for **End users** is **passwordless**: magic-link email login now; Apple/Google Identity links later (schema in ADR 0005). **Admin Users** still need email + password on the shared **Auth credential** table. NewLife’s Microsoft Entra ID token exchange serves church staff SSO — not Rooted’s consumer audience — and remains out of scope.

## Decision

1. **Shared infrastructure:** JWT access + refresh tokens, password hashing providers, and refresh rotation/blacklist as enabled — same plumbing for Admin and (when issued) member tokens.
2. **Admin Users** authenticate via `/admin/api/v1/auth` with **email + password** and RBAC. No Microsoft/OIDC login for Rooted admin.
3. **App End users** authenticate via **magic link only** (request + verify). Do **not** expose app password register/login as the product path. Magic-link verify may create an Auth credential with `password_hash` null plus End user + Preferences.
4. **Auth credential:** required email; optional password (required for Admin create/login); zero or more Identity links (ADR 0005). Phone is not a credential identifier.
5. **Explicitly out of scope:** Microsoft Entra / Azure AD token exchange, generic OIDC social login, and NewLife-style `MicrosoftAuthService`. Enabling Apple/Google HTTP flows requires a future ADR on top of ADR 0005 storage.
6. **Token policy:** follow product ranges (access ~15–60 minutes, refresh ~7–30 days) via configuration; clients send `Authorization: Bearer`.
7. **Anonymous access:** allow unauthenticated reads where the API spec marks devotion/bible as client-first; fellowship and journal require member JWT.

## Consequences

- No OIDC client secrets or Entra app registration in Rooted deployments.
- Agents must not reintroduce app password register/login as the primary End-user path.
- Admin password create/login must keep working on the same `auth.user` rows End users use (shared credential; ADR 0004).
- Magic-link token storage is ephemeral (e.g. Redis TTL), not on Identity link rows.
- If enterprise SSO is ever required, it demands a new ADR — it is not a silent port from `newlife-core-api`.
