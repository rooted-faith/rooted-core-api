# ADR 0014 — Bible index first; fill verse bodies on read from YouVersion

Rooted keeps verse-per-row addressing (ADR 0004) but stops pre-crawling Scripture text. The catalog stores a **Bible version** and its **Bible index** (book / chapter / verse ids with empty bodies). When an End user opens Today or a chapter, the backend fetches that chapter's HTML from YouVersion, parses it into lines and inline fragments, and writes the chapter in one shot. Same-chapter concurrent misses share one upstream request. A YouVersion id is treated as immutable; refresh is deleting filled bodies, not a year check. Verse bodies live in JSONB (`lines`); a sibling `search_text` column holds concatenated Scripture only (no Heading, no Footnote) so local search can be added later without scraping JSON. Keyword search itself is not shipped in this change. This supersedes ADR 0004 decision 2 only for *when* and *in what shape* verse bodies exist — not the `bible` schema, verse-per-row layout, or the ban on a `bible_passages` table.

## Status

Accepted (2026-09-10). Supersedes ADR 0004 decision 2 insofar as it implied pre-imported `bible.verses.content`.

## Considered options

| Option | Rejected | Why |
| ------ | -------- | --- |
| Keep `dump-bible` / `import-bible` of all verse text | Whole-Bible crawl | Rate limits, stale HTML-less strings, no Heading / Footnote |
| Postgres as a TTL cache of YouVersion | Not our catalog | Q1 was to own filled chapters; a given YouVersion id does not get a daily re-fetch |
| Store raw YouVersion HTML or a chapter JSON document | App coupled to YV DOM; weak Passage lookup | Daily lesson and bookmarks address verses |
| Re-fetch when a "Bible year" changes | No year field on the API | New editions are a new bible id; in-place refresh is an explicit body wipe |
| Normalize lines/fragments into child tables | Extra joins on every chapter read | Hot path is read/fill a chapter; JSONB is one row per verse. Search uses `search_text`, not JSON paths or fragment joins |

## Consequences

- CLI imports metadata and index only (`dump-bible --meta-only`); runtime uses `YVP_APP_KEY` on the miss path.
- `bible.verses.content` is replaced by nullable `lines` (JSONB) and nullable `search_text` (plain Scripture). Unfilled means both null. Existing imported plain text must be cleared before this ships.
- `search_text` is written in the same fill as `lines`: fragment types `text`, `nd`, `wj`, `pn` in order; skip Heading lines and Footnote fragments. No tsvector / GIN until search ships.
- Fill failure fails the whole Today or chapter request (no Scripture-less 200).
- Human-authored Alembic; agents do not add revisions.
- Local verse search is not implemented yet; the column is the seam.
