# Bible publisher names: import retention and metadata-only backfill

How content operators keep source `publisher_name` values on Bible versions, and how to fill already-imported versions without touching Scripture. Schema prerequisite: [0137 checklist](../migrations/0137-bible-version-publisher-name-checklist.md) / ROO-100.

## Prerequisites

1. The nullable `bible.versions.publisher_name` column is present (Alembic head includes `add_bible_version_publisher_name`).
2. Local metadata exists under `bible_data/{youversion_bible_id}/meta/bible.json` (from `dump-bible`, including `--meta-only`).
3. The target database already has the matching `bible.versions` rows (matched by immutable YouVersion Bible ID).

Source availability varies. NIV `111` includes `"publisher_name": "Biblica, Inc."`. Inspected dumps for `113`, `1392`, and `36` have no usable publisher name — those stay `NULL`.

Do **not** derive a name from `copyright`, `publisher_url`, or `organization_id`.

## Future imports

`import-bible` retains `publisher_name` on insert and upsert when the source supplies a non-blank value. Blank or missing source names store as `NULL`.

```bash
uv run python -m portal.cli.main import-bible --bible-id 111
```

## Metadata-only backfill

Use this for versions imported before the column existed. It does **not** import books or verses, does **not** call YouVersion, and does **not** clear a stored name when the source lacks one.

```bash
# All bible_data/*/meta/bible.json that have a non-blank publisher_name
uv run python -m portal.cli.main backfill-bible-publisher-names

# One YouVersion id
uv run python -m portal.cli.main backfill-bible-publisher-names --bible-id 111

# Alternate data directory
uv run python -m portal.cli.main backfill-bible-publisher-names --data-dir /path/to/bible_data
```

### Observable results

- Console lines such as `111: publisher_name='Biblica, Inc.'` for updates.
- `skipped (no publisher_name in source)` when the dump has no usable name (existing DB value unchanged).
- `skipped (version not in database)` when no row matches the YouVersion id (no insert).
- Summary: `Backfill complete: updated=… skipped=… missing=…`.
- Repeat with the same inputs is stable: same stored names, no duplicate versions, Scripture untouched.

### Verify in PostgreSQL

```sql
SELECT youversion_bible_id, publisher_name, copyright, publisher_url
FROM bible.versions
ORDER BY youversion_bible_id;
```

Expect `111` → `Biblica, Inc.` when that dump is present; versions without a source name remain `NULL`. Confirm book/verse identities, `lines`, and `search_text` are unchanged for a sample chapter before and after.

## Out of scope

Member and admin catalog APIs do not expose `publisherName`. There is no selector UI for publisher names.
