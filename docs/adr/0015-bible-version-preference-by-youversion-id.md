# ADR 0015 — Bible version preferences use YouVersion Bible IDs

## Status

Accepted (2026-10-03).

## Context

`app.user_preferences.bible_version` was a non-null soft key such as
`cuv1919`, while the Bible catalog and reader use Rooted database UUIDs.
Those UUIDs are internal to a deployment and cannot identify the configured
language defaults across environments. The original values also included the
retired `bilingual` mode.

Rooted needs a non-null preference on first End-user provisioning, but UI
language is device-specific and is intentionally not stored on the account
(ADR 0009).

## Decision

1. `bible_version` stores the immutable YouVersion Bible ID of an active,
   licensed Bible version. Rooted's `bible.versions.id` UUID remains internal.
2. The member Bible version catalog exposes `youversionBibleId`; clients use
   it for saved preferences and resolve the matching catalog UUID only when
   requesting books or chapters.
3. The Flutter app sends its resolved system language as `Accept-Language` on
   API requests. On first End-user provisioning, Core API writes the mapped
   default: NIV `113` for English, missing, or unsupported language; CCBT
   `1392` for Traditional Chinese; and CCB `36` for Simplified Chinese.
4. A user may change the reader translation only to an active, licensed
   catalog entry. The API rejects any other Bible ID. If an already-selected
   version becomes unavailable, the client first resolves a same-language
   active fallback and writes it back only after it loads successfully.
5. Existing preference values (`cuv1919`, `web`, and `bilingual`) are
   operationally migrated to NIV `113` by the Human Owner before rollout.
6. The reader's last successful location is the canonical `bookCode` and
   chapter. It is a device-local value, restored after the first Bible visit,
   and cleared on sign-out; it is never an account preference.
7. The public Bible version catalog includes `copyright` and `publisherUrl`
   for required attribution. It does not expose promotional content.
8. If first provisioning cannot resolve an active, licensed configured version
   or same-language fallback, it fails closed with a retryable service error;
   it never creates invalid Preferences or silently crosses languages.

## Consequences

- The Profile screen no longer exposes a Bible-version setting; the Bible
  reader is the sole selection entry point, while the preference remains
  account-synchronised.
- The old side-by-side preference and any `secondaryVersionId` client state
  are removed. The reader renders one translation at a time.
- On a translation switch, the reader keeps the canonical location when that
  translation offers it, otherwise it opens that translation's first readable
  chapter.
- Operations must import and activate NIV `113`, CCBT `1392`, and CCB `36`
  before enabling this behaviour. An unavailable language default must never
  create an invalid preference.
- Migration files remain human-managed under `alembic/versions/`.
