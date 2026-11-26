# NIV 111 default and NIVUK 113 removal

Status: accepted design (2026-11-25); implementation and manual database operations are pending. This document does not indicate that a deployment or database change has occurred.

## Decision

Use YouVersion `111` (NIV) for English, missing, and unsupported request languages. `113` is NIVUK (Anglicised), a separate edition with different quotation conventions and spellings. Traditional Chinese `1392` and Simplified Chinese `36` remain unchanged. Preserve source text, including quotation marks and apostrophes.

The Human Owner will change existing `113` preferences to `111`, update the actual database column default, and physically remove `113` and its related content. Other valid preferences remain unchanged. This change adds no automatic preference migration or `113` to `111` fallback in Bible or Today. It does not implement the general unavailable-version fallback policy in ADR 0015.

References: [ADR 0015](../adr/0015-bible-version-preference-by-youversion-id.md), [YouVersion NIV 111](https://www.bible.com/bible/111/REV.21.NIV), [YouVersion NIVUK 113](https://www.bible.com/bible/113/REV.21.NIVUK).

## Implementation scope

| Repository | Required change |
| --- | --- |
| `rooted-core-api` | Change `_DEFAULT_BIBLE_VERSION_ID` in `portal/application/app/end_user_provisioning_service.py` to `"111"`; align `UserPreferences.bible_version` in `portal/domain/app/entities.py` and the ORM `server_default` in `portal/models/app/user.py`. Update default-related tests and active-catalog test fixtures. |
| `rooted_flutter` | Change the missing-field `bibleVersion` JSON fallback in `lib/features/profile/domain/profile.dart` to `'111'`; update relevant fallback tests. Keep the existing version selection and source-text rendering behavior. |
| `rooted-docs` | Align API examples, version tables, schema defaults, PRD, and rollout prerequisites with `111`; identify historical `113` examples as NIVUK. |

Agents must not add, modify, or delete `alembic/versions/**`. The Human Owner owns the database migration/manual SQL. Changing the ORM `server_default` does not alter an existing database column default. Do not rewrite the `113` catalog ID to `111`: import a separate version and use its own book and version UUIDs.

## Rollout

1. In each target environment, confirm the configured YouVersion key can access `111`, then download its metadata/index and import it:

   ```bash
   uv run python -m portal.cli.main dump-bible --bible-id 111 --meta-only
   uv run python -m portal.cli.main import-bible --bible-id 111
   ```

   Import activates the version and creates empty verse shells. Re-importing an existing `111` clears that version's stored verse bodies. Chapter text is fetched on first read; downloading every passage in advance is unnecessary.

2. Verify `GET /api/v1/bible/versions` contains active `111` with upstream title, language, and attribution metadata. Resolve its Rooted version UUID, fetch its books, and read `REV.21` using that version's Revelation book UUID. Confirm read-time fill succeeds and text matches NIV `111`, including quotation nesting and the spellings `practice` and `sulfur`.
3. Deploy the backend defaults and updated Flutter fallback. Verify new English/missing/unsupported-language users receive `111`; Chinese defaults are unchanged. Ensure old backend instances cannot continue creating `113` preferences before retiring that version.
4. The Human Owner changes the actual default on `app.user_preferences.bible_version` to `'111'` and manually changes rows whose `bible_version = '113'` to `'111'`. Inspect any remaining legacy values (`cuv1919`, `web`, `bilingual`) under ADR 0015. Confirm no preferences still reference `113`.
5. The Human Owner physically deletes the `113` version and related content. The ORM declares cascading deletion from versions to books and from books to verses; confirm the deployed schema matches before executing the deletion. Check other deployed references to those version/book/verse UUIDs. Preference values are soft keys and will not be repaired by a catalog deletion.
6. Refresh account preferences and the version catalog in existing App sessions; sign out and back in if necessary. Verify Bible and Today use `111` and that `113` is absent from the version selector. Existing in-memory `113` selections must be refreshed; this change adds no automatic fallback for them.

Keep `113` available until `111` is readable and preferences have been updated. If any prerequisite fails, stop before deleting `113`, resolve it, and recheck. Physical deletion removes stored content; restoration requires re-importing the version and fetching chapters again, rather than merely toggling `is_active`.

## Validation for implementation

- Backend tests cover `en-US`, missing language, and an unsupported language resolving to `111`; `zh-Hant`/`zh-HK` resolve to `1392`, and `zh-Hans-CN`/`zh-CN` to `36`.
- An unavailable configured `111` still causes provisioning to return the existing retryable `503`, without creating invalid preferences. Normal preference validation still rejects unavailable catalog entries.
- Domain defaults and Flutter's missing-field JSON fallback use `111`. An explicit valid preference remains authoritative; the JSON fallback must not overwrite a supplied value.
- Run the affected backend tests and Ruff checks, and the affected Flutter tests and analyzer checks. This document-only change does not require running application tests.
- After the manual database work, verify the actual column default is `'111'`, no preferences contain `113`, and catalog `113` plus its books/verses are absent. Smoke-test both an updated existing account and a new account in Bible and Today, including Chinese defaults and successful `111` passage reads.

Record deployment, test, and database-operation results separately when performed. Acceptance of this plan is not evidence that those checks have passed.
