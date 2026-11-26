# Human Alembic checklist — add `bible.versions.publisher_name` (#137 / ROO-100)

Agents must **not** add, modify, or delete files under `alembic/versions/`. The ORM change is on the feature branch; this delta still needs a human-authored revision.

## Status

**Pending.** The `BibleVersion` ORM model carries `publisher_name`; the database does not yet. Nothing reads or writes the column until #138 (importer + metadata-only backfill) lands.

## Goal

Give Bible version metadata a place to keep the publisher name the source catalog supplies (for example NIV `111`: `Biblica, Inc.`), so imports stop dropping it. Source availability varies: `113`, `1392` and `36` have no `publisher_name`.

## Suggested steps

1. **Autogenerate** after the ORM change is on the branch:
   - `uv run alembic revision --autogenerate -m "add_bible_version_publisher_name"`
2. **Review the revision** for exactly one change:
   - `op.add_column("versions", sa.Column("publisher_name", sa.String(255), nullable=True, comment="Publisher name from source metadata, e.g., 'Biblica, Inc.'"), schema="bible")`
   - **Nullable, no server default** — existing rows stay `NULL` until the #138 backfill, and versions whose source has no publisher name stay `NULL` for good.
3. **Apply to an isolated validation database:** `uv run alembic upgrade head`
4. **Check existing rows are untouched:**
   - `SELECT count(*), count(publisher_name) FROM bible.versions;` — second number is `0`.
   - Version ids, books and verses are unchanged (the revision only adds a column).
5. **Smoke the catalog API:** `GET /api/v1/bible/versions` and `GET /admin/api/v1/content/bible/versions` still return 200 with no `publisherName` field.

## Deployment order (later rollout)

1. Apply this migration in the target environment.
2. Deploy the #138 application code (import keeps `publisher_name`; backfill CLI).
3. Run the #138 metadata-only backfill and verify stored values.

The migration must run before step 2. The new code selects and writes `publisher_name`, so it fails on a database without the column.

## Out of scope

- Writing `publisher_name` on import, and the backfill itself (#138)
- Any API field or UI that shows the publisher name
