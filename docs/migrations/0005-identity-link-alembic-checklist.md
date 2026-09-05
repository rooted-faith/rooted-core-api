# Human Alembic checklist — Identity link + Auth credential (#12 / ADR 0005)

Agents must **not** add, modify, or delete files under `alembic/versions/` during ordinary feature work. Revision `94a54cea8e8f` was added under the dedicated human migration ticket (#14).

## Status

**Done in revision `94a54cea8e8f`** (`identity_link_and_auth_credential`, revises `5786a69aae71`).

Applied successfully on a clean local `rooted-core` with bible head + pre-ADR-0005 `auth.user` / `auth.user_third_party` baseline. Smoke: null-email rows removed; `password_hash=NULL` credential insert; Identity link row against seeded `google` / `apple`.

## Goals

1. Adjust `auth.user` (Auth credential).
2. Replace `auth.user_third_party` with `auth.identity_provider` + `auth.identity_link`.
3. Seed Identity providers `google` and `apple` only (not `microsoft`).

## Suggested steps (historical)

1. **Backup / note local data:** any rows with null `email` or phone-only identifiers must be cleaned before `email` becomes `NOT NULL`. Empty production user base is assumed; local DBs may still need a one-off fix. The revision deletes null-email rows before the `NOT NULL` alter.
2. **Autogenerate** (or hand-write) a revision after ORM changes are on the branch:
   - `uv run alembic revision --autogenerate -m "identity_link_and_auth_credential"`
3. **Review the revision** for at least:
   - `auth.user.email` → `NOT NULL` (and unique retained)
   - Drop `auth.user.phone_number` (column + unique index/constraint)
   - Create `auth.identity_provider` (`code` PK, `name`, `is_active`, `requires_tenant`) — **no** UUID `id`, **no** soft-delete
   - Create `auth.identity_link` with FK `user_id` → `auth.user`, FK `provider` → `auth.identity_provider.code`, nullable `provider_tenant`, `provider_subject`, optional `additional_data` JSONB, soft-delete + audit columns
   - **No** OAuth `access_token` / `refresh_token` / `token_expires_at` on Identity link
   - Partial unique indexes on **active** rows only (`is_deleted IS false`):
     - `(provider, provider_tenant, provider_subject)` with `NULLS NOT DISTINCT` (or equivalent)
     - `(user_id, provider)`
   - Drop `auth.user_third_party` (or equivalent NewLife table) if present
4. **Seed catalog** (migration `INSERT … ON CONFLICT DO NOTHING` **or** CLI after upgrade):
   - `google` — name `Google`, `is_active=true`, `requires_tenant=false`
   - `apple` — name `Apple`, `is_active=true`, `requires_tenant=false`
   - Do **not** seed `microsoft`
   - CLI alternative after tables exist: `uv run python -m portal.cli.main seed-identity-providers`
5. **Apply locally:** `uv run alembic upgrade head`
6. **Smoke:** Admin password create/login still works; `create_credential` with `password_hash=None` inserts; Identity link upsert/lookup against seeded providers.

## Prerequisite

This revision **requires** `auth.user` to already exist (platform auth baseline / prior `create_all`). It raises if the table is missing.

## Out of scope for this migration

- Magic-link Redis/token tables
- Apple/Google OAuth client config
- Account-merge / pending-link tables
- Full auth/RBAC baseline create (still outside Alembic history except this delta)
