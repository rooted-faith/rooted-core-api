# ADR 0003 — Auth strategy: Admin password + Google; app End users passwordless (magic link)

## Status

Accepted (Phase 0, 2026-08-27); **updated** (2026-09-05) for app passwordless; **updated** (2026-09-05) for Admin Google via ADR 0006.

Supersedes the earlier “app password + optional magic link” wording in this ADR. Durable Identity storage is ADR 0005. **Admin Google ID-token HTTP flow** is authorized by **ADR 0006** (not by this ADR alone). End-user Apple/Google HTTP flows still need a future ADR. Microsoft Entra remains out of scope.

## Context

Rooted requires account-backed sync and fellowship (`rooted-docs` PRD §9.4, API spec §2). The codebase inherits JWT, password hashing, and admin RBAC patterns from the portal/NewLife lineage.

Product direction for **End users** is **passwordless**: magic-link email login now; Apple/Google Identity links later (schema in ADR 0005; HTTP in a future ADR). **Admin Users** sign in on the shared **Auth credential** with **email + password** and, per ADR 0006, optional **Google** ID-token exchange on the admin console. NewLife’s Microsoft Entra ID token exchange serves church staff SSO — not Rooted’s audience — and remains out of scope.

## Decision

1. **Shared infrastructure:** JWT access + refresh tokens, password hashing providers, and refresh rotation/blacklist as enabled — same plumbing for Admin and (when issued) member tokens.
2. **Admin Users** authenticate via `/admin/api/v1/auth` with **email + password** and/or **Google** (ADR 0006), then RBAC. **No** Microsoft/Entra login. **No** Apple on the admin console.
3. **App End users** authenticate via **magic link only** (request + verify) until a future ADR adds Apple/Google. Do **not** expose app password register/login as the product path. Magic-link verify may create an Auth credential with `password_hash` null plus End user + Preferences.
4. **Auth credential:** required email; optional password (required for Admin password create/login; Google-linked admins may still keep a password). Zero or more Identity links (ADR 0005). Phone is not a credential identifier.
5. **Explicitly out of scope here:** Microsoft Entra / Azure AD token exchange, NewLife-style `MicrosoftAuthService`, Admin Apple, and End-user Apple/Google HTTP (future ADR). Generic “port all NewLife OIDC” is not authorized.
6. **Token policy:** follow product ranges (access ~15–60 minutes, refresh ~7–30 days) via configuration; clients send `Authorization: Bearer`.
7. **Anonymous access:** allow unauthenticated reads where the API spec marks devotion/bible as client-first; fellowship and journal require member JWT.

## Consequences

- Admin Google needs Google Client ID allowlist configuration (ADR 0006); Microsoft/Entra app registration stays out.
- Agents must not reintroduce app password register/login as the primary End-user path.
- Admin password create/login must keep working on the same `auth.user` rows End users use (shared credential; ADR 0004).
- Magic-link token storage is ephemeral (e.g. Redis TTL), not on Identity link rows.
- Enterprise Microsoft SSO, if ever required, demands a new ADR — it is not a silent port from `newlife-core-api`.
- See ADR 0006 for Admin Google link/provisioning rules and portal contract-test implications.
