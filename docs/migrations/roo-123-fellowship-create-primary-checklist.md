# Human Alembic checklist — Fellowship create / membership / Primary preference (ROO-123)

Agents must **not** add, modify, or delete files under `alembic/versions/`. The ORM and seed changes are on the feature branch; this delta still needs a human-authored revision and a seed run.

## Status

**Pending human migration.** Application code and insert-if-missing system setting seeds land with ROO-123; schema rollout is blocked on this checklist.

## Goal

Persist Fellowships, memberships (with explicit Covenant timestamps and a single Owner), and an account-synced Primary Fellowship preference. Declare capacity via system settings (Fellowship 50 / Group 15).

## Schema changes (ORM already on branch)

1. **Schema** `fellowship` (new).
2. **Table** `fellowship.fellowship`
   - `id` UUID PK (`uuidv7()` server default)
   - `name` `String(100)` NOT NULL
   - `discoverability` `String(16)` NOT NULL, server default `'private'`, CHECK `public|private`
   - Audit + soft-delete mixins (`created_at/by`, `updated_at/by`, `is_deleted`, `delete_reason`)
3. **Table** `fellowship.membership`
   - `id` UUID PK
   - `fellowship_id` UUID NOT NULL FK → `fellowship.fellowship.id` ON DELETE CASCADE
   - `user_id` UUID NOT NULL FK → `app.user.id` ON DELETE CASCADE
   - `role` `String(32)` NOT NULL, CHECK `owner|admin|group_leader|member`
   - `covenant_accepted_at` timestamptz NULL (null until explicitly accepted)
   - Partial unique index: one active membership per user per Fellowship  
     `UNIQUE (fellowship_id, user_id) WHERE is_deleted = false`
   - Partial unique index: one active Owner per Fellowship  
     `UNIQUE (fellowship_id) WHERE role = 'owner' AND is_deleted = false`
   - Audit + soft-delete mixins
4. **Column** `app.user_preferences.primary_fellowship_id`
   - UUID NULL FK → `fellowship.fellowship.id` ON DELETE SET NULL
   - Index recommended

## System settings (no Alembic; CLI seed)

`seed_system_settings` insert-if-missing rows (see `portal/cli/datas/system_setting_seed_data.py`):

| namespace     | setting_key          | value_type | value |
|--------------|----------------------|------------|-------|
| `fellowship` | `max_active_members` | number     | 50    |
| `fellowship` | `max_group_members`  | number     | 15    |

Run after migrate: `uv run python -m portal.cli.main seed-system-settings` (or via `init-all` path that includes system settings).

## Suggested steps

1. **Autogenerate** after ORM is on the branch:
   - `uv run alembic revision --autogenerate -m "add_fellowship_membership_and_primary_preference"`
2. **Review the revision** for the objects above; drop unrelated noise.
3. **Apply to an isolated validation database:** `uv run alembic upgrade head`
4. **Seed capacity settings** (insert-if-missing).
5. **Smoke:**
   - `POST /api/v1/fellowships` with `{ "name", "discoverability", "covenant_accepted": true }` as an authenticated End user
   - `GET /api/v1/fellowships` and `PUT /api/v1/fellowships/primary`
   - Confirm `covenant_accepted: false` returns 400 with `FELLOWSHIP_COVENANT_REQUIRED`

## Deployment order

1. Apply this migration **before** deploying application code. Preferences reads select `primary_fellowship_id`; deploying without the column breaks `/users/me`.
2. Deploy ROO-123 application code.
3. Run system-setting seed if settings are missing.
4. Do not claim invitation, Group administration, or search discoverability are live (later tickets).

## Out of scope

- Editing `alembic/versions/**` in an agent PR
- Invitation / approval admission HTTP (ROO-125)
- Group tables and Group capacity enforcement beyond declaring the setting
- Public content publication and search
