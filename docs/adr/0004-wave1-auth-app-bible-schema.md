# ADR 0004 — Wave 1 schema: auth credentials ≠ End user, bible schema, drop NewLife domains

## Status

Accepted (2026-09-03)

## Context

`rooted-core-api` still carries NewLife facility/org/member ORM alongside a Rooted bible slice living in `public.bible_*`. The app client (`rooted-app`) needs real accounts and preferences, while admin RBAC must keep using the existing `auth.user` stack. Docs proposed a single product `users` table and a `bible_passages` model that does not match the migrated verse-level bible data.

We need a first migration wave that is small enough to ship, but hard enough to reverse that the boundaries must be explicit.

## Decision

### 1. Credentials and End user stay separate

- **`auth.user`** remains the shared credential row for **Admin User** and **End user** (a person may hold both capacities on one credential).
- **`app.user`** is the product **End user** identity: its own UUID, `auth_user_id` → `auth.user`, created only when someone registers/uses the app as an End user (pure Admin accounts need not have `app.user`).
- **`app.user_preferences`** (1:1 with `app.user`) holds presentation/settings: display name, locale, theme, font scale, bible version, stage, reminder fields.
- **`auth.user_profile`** stays for Admin-oriented profile fields; it is not the Rooted prefs store.
- Future product FKs (journal, groups, …) reference **`app.user.id`**, not `auth.user.id`.
- Retain **`auth.user_third_party`** for future multi-provider sign-in. This does **not** revive Microsoft Entra / OIDC in v1 (see ADR 0003); enabling a new provider requires its own ADR.

### 2. Bible moves to `bible` schema; keep verse storage

- Relocate catalog text to **`bible.versions`**, **`bible.books`**, **`bible.verses`** (verse-per-row).
- Do **not** introduce a `bible_passages` table; passages remain a read/addressing concept over verses.
- Drop the NewLife-era `auth.user.person_id` link when removing `member.person`.

### 3. Drop NewLife product domains in the same wave

- Drop schemas/tables for **`facility.*`**, **`org.*`**, and **`member.person`** (and ORM/repos that only serve them), aligning with ADR 0001 “explicitly not ported.”
- Keep platform pieces Rooted admin still needs: auth/RBAC, locale, settings, audit, content.

### 4. Explicitly deferred (later waves)

Devotion/journal/fellowship tables, series/lessons CMS, sync resource persistence, and bookmark/walk sync schema are **out of this wave**.

## Considered options

| Topic | Rejected | Why |
| ----- | -------- | --- |
| Merge End user into `auth.user` only | Single-table identity | Mixes admin RBAC with product FKs; prefs and soft-delete semantics blur |
| Same UUID for `auth.user` and `app.user` | 1:1 shared PK | Blocks credential rotation / multi-provider evolution; false “sameness” |
| Docs `bible_passages` + string version PKs | Replace verse model | Throws away working import/migration; conflicts with UUID `ModelBase` practice |
| Leave bible in `public` | No schema move | Keeps an inconsistent “exception” once `app` / `bible` contexts exist |
| Also drop `content` / `audit` / `user_third_party` | Broader purge | Breaks admin platform or future app login providers |

## Consequences

- Alembic (human-owned) must: create `app` + `bible` schemas/tables, move bible data, drop facility/org/member, remove `person_id`.
- App auth/register paths create `auth.user` + `app.user` + preferences; admin-only users skip `app.user`.
- Agents must not reintroduce facility/org models or treat `auth.user` as the product member FK target.
- `rooted-docs` database-design.md should be updated to match this ADR (string/`bible_passages`/`users`-only shape is superseded for Wave 1).
- Multi-provider login is a future product ADR; table retention alone is not an implementation green light for OIDC.
