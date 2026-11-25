# Bible paragraph boundaries: response contract and chapter refill

How clients read publisher paragraph boundaries, and how an operator upgrades chapters filled before they were stored. Background: [ADR 0014](../adr/0014-bible-index-and-read-time-fill.md).

## Response contract

Every entry in a verse's `lines` may carry one additional boolean, `continues`. It appears wherever `lines` is served: chapter reads, Passage reads, Today, and the Admin chapter read.

| `continues` | Meaning |
| --- | --- |
| `false` | First line of a publisher block: a paragraph, a poetry line, or a **Heading** |
| `true` | Continues the block of the previous line, across a verse boundary |
| absent | Legacy line, filled before boundaries were stored. Nothing is known about its paragraph |

```json
{
  "verses": [
    {
      "passageId": "REV.21.8", "verse": 8, "verseEnd": null,
      "lines": [{ "type": "line", "style": "p", "continues": true, "fragments": [] }]
    },
    {
      "passageId": "REV.21.9", "verse": 9, "verseEnd": null,
      "lines": [
        { "type": "heading", "style": "s1", "continues": false, "fragments": [] },
        { "type": "line", "style": "p", "continues": false, "fragments": [] }
      ]
    }
  ]
}
```

(`fragments` left empty for brevity.)

Rules for clients:

- Start a new block where `continues` is `false`; decide by this key, never on `style`, punctuation, or verse rows. Two adjacent paragraphs often share a style.
- A verse with several non-heading lines holds a break inside the verse. Show its number once.
- A chapter is filled in one write, so its lines either all carry the key or all lack it. A Passage spanning chapters can mix the two.
- A Passage can begin in the middle of a paragraph. Its first line is then `true`; start a block anyway.
- For legacy lines, keep the verse-by-verse layout.
- Clients that ignore the key keep working. The key does not change `type`, `style`, `fragments`, `verse`, or `verseEnd`.

Filled together with the key:

- **Headings** come before the Scripture they introduce. A Heading between verses 8 and 9 is in verse 9. A Heading in the middle of a verse stays between that verse's lines.
- **Word separation** is kept in fragment text. Concatenate fragments as they are, without adding or trimming spaces. A line that continues into another verse may end with a space. Legacy English text lost these spaces.

Filled later than the key (ROO-87), so `continues` does not imply them. Chapters filled before then lack superscriptions and have Footnote text joined into the Heading until a forced refill:

- **Psalm superscriptions** are Headings. Any block before the chapter's first verse marker becomes a Heading line of the first verse, in publisher order, with its Scripture style (`d`) and inline fragments. The same style on or after a verse marker stays a Scripture line.
- **Footnotes in a Heading** are `footnote` fragments of the Heading line, in the same shape as in Scripture lines. They are not part of the Heading's text, so skip them when you join a Heading's fragments. Neither is in `search_text`.
- **Generated Footnote labels** number a chapter's Footnotes in document order, Heading Footnotes included. A refill can shift the labels of later Footnotes that have no publisher label.

## Upgrade old chapters

Filled bodies are never fetched again on read, so a legacy chapter stays legacy until an operator refills it. Both commands work on one active Bible version, named by its YouVersion id.

1. List the legacy chapters. This reads the database only.

   ```bash
   uv run python -m portal.cli.main list-legacy-bible-chapters --bible-id 1392 --book REV
   ```

2. Choose chapters from the list and refill them. `YVP_APP_KEY` must be set.

   ```bash
   uv run python -m portal.cli.main refill-bible-chapters --bible-id 1392 --chapter REV.21 --chapter REV.22
   ```

3. List again. Refilled chapters are gone from the list.

To give an upgraded chapter a later parser fix, such as Psalm superscriptions and Heading Footnotes (ROO-87), name it with `--force`. Such chapters are not in the legacy list; choose them yourself.

```bash
uv run python -m portal.cli.main refill-bible-chapters --bible-id 1392 --chapter PSA.3 --force
```

There is no option for a whole book or version. Each named chapter costs one YouVersion request.

| Result | Meaning |
| --- | --- |
| `upgraded` | Old bodies replaced, committed |
| `already_upgraded` | Nothing fetched or written. Repeating the command is safe. Never reported with `--force`, which fetches and replaces each time |
| `unfilled` | No stored bodies, also with `--force`. The next read fills it with boundaries |
| `failed (...)` | Rolled back. The old bodies are still served. The command exits with 1 after trying the other chapters |

A refill fetches and validates before it writes, and each chapter is one transaction. Readers see the old chapter or the new one. Only `lines`, `search_text`, and `verse_end` change; book ids, verse rows, and Passage addresses stay, so bookmarks and Daily lessons are unaffected.

Do not use `import-bible` to upgrade content. It clears every body in the version.
