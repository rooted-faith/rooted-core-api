# YouVersion: How to Retrieve More Complete Bible Content

Date: 2026-09-10
Status: research note (not an ADR)

## Question

The existing `dump-bible` only stores plain text verse by verse. Compared with the [YouVersion Platform API](https://developers.youversion.com/api/bibles) and the local dump, what changes would allow us to retrieve more complete content? Is the user-provided [data-exchange](https://developers.youversion.com/api/data-exchange) relevant?

## Short answer

**Data-exchange is unrelated to Bible text content.** Those endpoints are for short-lived tokens + browser authorization, and the only permission currently available is `highlights` (user highlights), not Bible text.

More complete Bible content comes from the same passages API, but three things need to change:

1. Change the retrieval unit from a **single verse** to a **whole chapter** (USFM `GEN.1`, not `GEN.1.1`)
2. Use `format=html` instead of `text`
3. Explicitly pass `include_headings=true` and `include_notes=true`

The CLI already has these flags; the 1392 dump simply did not use them.

## Current dump (1392 CCBT)

Source: `bible_data/1392/` + `portal/cli/bible.py`.

| Item | Current state |
| --- | --- |
| API | `GET https://api.youversion.com/v1/bibles/{id}/passages/{passage_id}` |
| Auth | `X-YVP-App-Key` ← env `YVP_APP_KEY` |
| Unit | Each verse's `passage_id` from the index (e.g. `GEN.1.1`) |
| Query | `format=text`, `include_headings=false`, `include_notes=false` |
| Count | 30,961 verses; 1,189 chapters in the index; all 66 book `intro` values are `null` |
| Stored JSON | Three fields: `{ id, content, reference }` |
| Import | Only writes `content` into `bible.verses.content` (ADR 0004 verse-per-row) |

Sample (`GEN.1.1`):
```json
{"id": "GEN.1.1", "content": "太初，上帝創造了天地。", "reference": "創世記 1:1"}
```

The missing data is not caused by "failing to fetch a few verses." **Paragraph structure, poetic formatting, headings, footnotes, and book introductions** are inherently unavailable when using single-verse + plain-text mode.

## What data-exchange actually is

Primary: [data-exchange](https://developers.youversion.com/api/data-exchange)

| Endpoint | Role |
| --- | --- |
| `POST /data-exchange/token` | Requires a user Bearer token; the `requested_permissions` body currently has only one enum value: `highlights` |
| `GET /data-exchange?token=` | Browser approval page |
| `POST /data-exchange` | Redirects back to the app callback (`granted` / `cancelled` / `error`) |

This is for "authorizing our app to access the user's YouVersion highlights," not for downloading Bible translations. Do not use it to supplement Bible text.

## Passages API: the completeness knobs

Primary: [bibles / Get a passage](https://developers.youversion.com/api/bibles), [JS SDK `getPassage`](https://developers.youversion.com/sdks/javascript/index), [schema `Passage`](https://developers.youversion.com/api/~schemas)

```text
GET /v1/bibles/{bible_id}/passages/{passage_id}
  ?format=text|html          # default text
  &include_headings=true|false
  &include_notes=true|false
```

According to the official documentation:

- `include_headings` / `include_notes` default to **false**, but if the reference is a **whole chapter or introduction** (`GEN.1`, `GEN.INTRO1`), they default to **true**.
- `format=text`: no markup; suitable for any environment.
- `format=html`: includes YouVersion CSS classes for paragraphs, poetry, tables, verse markers, headings, and footnotes. The SDK explicitly recommends this format for "preserving paragraph and table formatting."
- USFM can represent a single verse `JHN.3.16`, a range `GEN.1.1-5`, or a whole chapter `GEN.1`. The React SDK also mentions multi-chapter references such as `GEN.1-2`.
- The response schema only contains `id` / `content` / `reference`. Headings and notes are **embedded inside the `content` string** rather than returned as separate JSON arrays.

Common HTML classes ([YVDom reference](https://gist.github.com/de-taylor/ec93a9529cea67f75732ccc9dcefd6d9), unofficial but consistent with the SDK examples):

| Class | Meaning |
| --- | --- |
| `p` / `m` / poetry classes | Paragraphs and poetic lines |
| `yv-v` | Verse milestone (`v="16"`) |
| `yv-vlbl` | Displayed verse number |
| `yv-h` | Heading |
| `yv-n` | Footnote / cross-reference |

The official React [`BibleTextView`](https://developers.youversion.com/sdks/react/components) component uses the same HTML format; `renderNotes` defaults to true. This is a reference implementation for the "complete reader experience," not a separate data source.

## Metadata endpoints (no verse text)

These endpoints **do not contain Bible text**; they only provide structure. The existing dump already uses the Bible metadata + index, so the others are redundant:

| Endpoint | Content |
| --- | --- |
| `GET /v1/bibles/{id}` | Translation metadata (already dumped to `meta/bible.json`) |
| `GET /v1/bibles/{id}/index` | Book/chapter/verse tree (already dumped to `meta/index.json`) |
| `GET /v1/bibles/{id}/books/...` | Structural information overlapping with the index |
| `GET /v1/bibles/{id}/books/{book}/chapters/{ch}/verses/{v}` | Only contains `passage_id`, **no text** |

Search endpoints (`search_verses`, etc.) also return only USFM references; another passages request is required to retrieve the actual Bible text.

## Intros

The index schema gives each book an `intro: { passage_id: "GEN.INTRO", ... }`. In translation 1392, **all `intro` values are `null`**, so the absence of book introductions in the CCBT dump is because the translation itself does not provide them, not because the crawler failed to retrieve them.

For other translations where `intro` is not null, call the passages API once more using `book.intro.passage_id` with `format=html`.

## Licenses vs more versions

Primary: [licenses](https://developers.youversion.com/api/licenses), [bibles collection `all_available`](https://developers.youversion.com/api/bibles)

- `GET /v1/bibles` returns only the translations **licensed for the current App Key** by default.
- `all_available=true` can list translations that have not yet been licensed. Accessing their Bible text still requires accepting the corresponding license on [platform.youversion.com](https://platform.youversion.com).
- `GET /v1/licenses?bible_id=1392` can retrieve the translation's license terms HTML / URI.
- When displaying Bible text, the copyright notice must be included; the SDK Quick Start explicitly requires this. `bible.json` already contains `copyright`.

If "more complete" means **more Bible translations**, that is a licensing issue rather than a passages API parameter issue.

## Rate / request cost

| Strategy | Approximate request count (1392) |
| --- | --- |
| Current: verse by verse | ~30,961 + 2 metadata requests |
| Change to chapter-by-chapter `BOOK.N` | ~1,189 + 2 metadata requests |
| Chapter-by-chapter + available intros | 1,189 + number of intros |

According to the official [quick-reference](https://developers.youversion.com/quick-reference), when receiving a 429 response, use `Retry-After`, and caching is recommended.

The current crawler stops when it encounters a 429 and resumes using `state.json`; `--daily-limit` **is not actually enforced**.

## Storage conflict with ADR 0004

[ADR 0004](../adr/0004-wave1-auth-app-bible-schema.md) chose a **verse-per-row** model and explicitly avoided a `bible_passages` table. Headings and footnotes are chapter-level or cross-verse structures, so placing them inside `bible.verses.content` would either duplicate or split that structure incorrectly.

Possible approaches (decision still pending):

| Option | Approach | Trade-off |
| --- | --- | --- |
| A. Only improve the dump | Re-run `dump-bible --format html --include-headings --include-notes`, still verse by verse | Headings/notes are incomplete in single-verse HTML; request volume remains unchanged |
| B. Fetch whole-chapter HTML | Use each chapter `passage_id` with passages; store it separately in SQLite `chapters`; derive plain-text verses from HTML using `yv-v` markers | Import / reader / schema must support chapter-level HTML |
| C. Do not maintain an offline dump | Call YouVersion at app runtime (or use the official `BibleTextView`) | Depends on a third party, licensing, and network access; conflicts with the "self-owned catalog" approach |

If the product needs a "complete reading experience" with paragraphs, poetry formatting, and footnotes, only B or C properly matches the official model. A will retrieve almost no useful headings.

## How to re-run dump with current CLI (no code change)

The flags already exist in `portal/cli/main.py`:

```bash
uv run python -m portal.cli.main dump-bible \
  --bible-id 1392 \
  --out bible_data \
  --format html \
  --include-headings \
  --include-notes
```

This still retrieves **single-verse** HTML. To retrieve whole-chapter content, `YouVersionDumper.dump_passages_by_chapter_from_index` must be changed to call passages using `chapter.passage_id` (`GEN.1`) instead of each individual `verse.passage_id`.

`import-bible` currently only ingests the `data.content` string. If the import process is not changed, an HTML dump will write the entire markup string directly into `bible.verses.content`.

## Recommended next change (if we implement)

1. Dump **chapter HTML** (`format=html`, with headings/notes enabled) alongside the existing plain-text verses used for search / devotional references.
2. If `book.intro` exists, fetch its intro passage as well.
3. Do not integrate data-exchange to supplement Bible text.
4. If adding a second translation, first call `GET /v1/licenses?bible_id=` and accept the license through the portal, then dump it.

## Sources

- [YouVersion data-exchange](https://developers.youversion.com/api/data-exchange)
- [YouVersion bibles API](https://developers.youversion.com/api/bibles)
- [YouVersion API usage](https://developers.youversion.com/api-usage)
- [YouVersion JS SDK — getPassage](https://developers.youversion.com/sdks/javascript/index)
- [YouVersion React BibleTextView](https://developers.youversion.com/sdks/react/components)
- [YouVersion licenses](https://developers.youversion.com/api/licenses)
- [YouVersion schemas (Passage)](https://developers.youversion.com/api/~schemas)
- [YouVersion quick reference / 429](https://developers.youversion.com/quick-reference)
- Local: `portal/cli/bible.py`, `bible_data/1392/`, ADR 0004

