# ADR 0005 — Identity link + Identity provider catalog (replace `user_third_party`)

## Status

Accepted (2026-09-04)

Supersedes ADR 0004’s retention of NewLife-shaped `auth.user_third_party` as the forward model. Does **not** supersede ADR 0003. This decision only reshapes durable identity storage. **Admin Google** HTTP is ADR 0006; **End-user** Apple/Google HTTP still need a future ADR.

## Context

PRD schedules Apple / Google sign-in for v2. The ORM still mirrors NewLife: `auth.user_third_party` with required UUID `provider_tenant_id`, optional OAuth `access_token` / `refresh_token`, and a unique key of `(user_id, provider, provider_uid)` that does not globally uniquify a provider subject. That shape fits Microsoft Entra and token caching — not consumer IdPs and not an **Identity link**.

We need a table design that can hold most third-party sign-in bindings before those flows are implemented, without reviving Microsoft OIDC in Rooted.

## Decision

1. **Ubiquitous language** (see `CONTEXT.md`): **Identity provider** (catalog entry) and **Identity link** (binding to an **Auth credential**). Links hang on `auth.user`, not `app.user`.

2. **Replace** `auth.user_third_party` / `AuthUserThirdParty` with:
   - **`auth.identity_provider`**: `code` (string PK, e.g. `google`, `apple`), English `name`, `is_active`, `requires_tenant`. No soft-delete; deactivate with `is_active`. Seed **`google`** and **`apple`** only (not `microsoft`).
   - **`auth.identity_link`**: `user_id` → `auth.user`, `provider` → `identity_provider.code`, nullable string `provider_tenant`, `provider_subject`, optional `additional_data` (JSONB snapshot only), soft-delete + audit. **No** provider OAuth access/refresh token columns.

3. **Cardinality / uniqueness** (active rows only, partial unique indexes; `NULL` tenants compare equal, e.g. `UNIQUE NULLS NOT DISTINCT` or equivalent):
   - Global: `(provider, provider_tenant, provider_subject)` → at most one credential.
   - Per credential: `(user_id, provider)` → many providers allowed; the same provider must not repeat.

4. **Auth credential shape**: `email` is **NOT NULL**; drop `phone_number`. No email-less `auth.user` rows. Account-merge when the same email arrives via a new IdP is **out of scope** (no pending-merge table); decide in a future sign-in ADR.

5. **Out of scope here**: OAuth/OIDC HTTP flows, token exchange, auto-link-by-email product rules, and Microsoft / church SSO. Admin Google HTTP + auto-link-by-email for admin is **ADR 0006**; End-user IdP HTTP remains a future ADR.

## Considered options

| Topic | Rejected | Why |
| ----- | -------- | --- |
| Keep NewLife `user_third_party` + UUID tenant | Minimal diff | Blocks Apple/Google; wrong uniqueness; implies Entra |
| Store OAuth tokens on the link row | Convenient for Graph APIs | Not the purpose of an Identity link; `String(255)` unfit; use a later token store if needed |
| Provider as app enum only (no catalog) | Lighter schema | Rejected in favor of an explicit catalog for active flags and `requires_tenant` |
| Soft-delete providers | Consistency with other auth tables | Stable codes + FK; `is_active` is enough |
| Seed `microsoft` in the catalog | Symmetry with NewLife | Contradicts ADR 0003 signal; add only when SSO is approved |
| Pending account-merge table now | Forward-looking | No users yet; merge policy undecided |

## Consequences

- ORM and human-owned Alembic should introduce `identity_provider` / `identity_link` and adjust `auth.user` (`email` NOT NULL, drop `phone_number`); remove or stop using `user_third_party` and token columns.
- Repository ports that upsert by `provider_uid` / UUID tenant must move to `provider_subject` + nullable `provider_tenant`.
- `ThirdPartyProvider` / Microsoft leftovers stay dead until a sign-in ADR; catalog codes are the source of truth for allowed providers.
- Implementing sign-in HTTP must not be inferred from this schema alone: Admin Google → ADR 0006; End-user Apple/Google → future ADR.
- Human Alembic steps: see `docs/migrations/0005-identity-link-alembic-checklist.md`.
