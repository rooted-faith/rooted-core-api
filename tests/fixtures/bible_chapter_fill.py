"""Controlled Bible repository and YouVersion dependencies for chapter-fill tests."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import uuid4

from portal.domain.bible.entities import BibleChapter, BibleVerse
from portal.infrastructure.youversion.youversion_http_client import YouVersionHttpError

BIBLE_DATA = Path(__file__).resolve().parents[1] / "data" / "bible"


def load_passage(name: str) -> dict:
    return json.loads((BIBLE_DATA / f"{name}_html.json").read_text(encoding="utf-8"))


class StubYouVersion:
    def __init__(self, passages: dict[str, dict] | None = None, error: Exception | None = None, delay_sec: float = 0.0):
        self._passages = passages or {}
        self._error = error
        self._delay_sec = delay_sec
        self.calls: list[tuple[str, str]] = []

    async def get_bible_metadata(self, bible_id: str) -> dict:
        raise NotImplementedError

    async def get_bible_index(self, bible_id: str) -> dict:
        raise NotImplementedError

    async def get_chapter_passage(self, bible_id: str, chapter_usfm: str) -> dict:
        self.calls.append((bible_id, chapter_usfm))
        if self._delay_sec:
            await asyncio.sleep(self._delay_sec)
        if self._error is not None:
            raise self._error
        key = f"{bible_id}:{chapter_usfm}"
        if key not in self._passages:
            raise YouVersionHttpError(404, f"/v1/bibles/{bible_id}/passages/{chapter_usfm}")
        return self._passages[key]


class StubBibleRepository:
    def __init__(self, chapter: BibleChapter):
        self._chapter = chapter
        self.write_calls: list[list[dict]] = []
        self.fetch_calls = 0
        self.version_id = chapter.bible_version_id

    async def fetch_active_versions(self, language=None):
        return []

    async def version_is_active(self, bible_version_id):
        return True

    async def find_active_version_id(self, youversion_bible_id):
        return self.version_id if youversion_bible_id == self._chapter.youversion_bible_id else None

    async def find_book_id(self, bible_version_id, book_code):
        return self._chapter.book_id if book_code == self._chapter.book_code else None

    async def fetch_books(self, bible_version_id):
        return []

    async def fetch_chapter(self, book_id, chapter):
        self.fetch_calls += 1
        if self._chapter is None:
            return None
        return BibleChapter(
            bible_version_id=self._chapter.bible_version_id,
            youversion_bible_id=self._chapter.youversion_bible_id,
            bible_title=self._chapter.bible_title,
            book_id=self._chapter.book_id,
            book_code=self._chapter.book_code,
            book_name=self._chapter.book_name,
            chapter=self._chapter.chapter,
            verses=[BibleVerse(passage_id=verse.passage_id, verse=verse.verse, verse_end=verse.verse_end, lines=verse.lines) for verse in self._chapter.verses],
        )

    async def search_verses(self, q, bible_version_id, book_id, limit, offset):
        raise NotImplementedError

    async def write_chapter_fill(self, book_id, chapter, fills: list[dict]) -> None:
        self.write_calls.append(fills)
        by_verse = {item["verse"]: item for item in json.loads(json.dumps(fills))}  # JSONB round trip
        updated = []
        for verse in self._chapter.verses:
            fill = by_verse.get(verse.verse)
            if fill is None:
                updated.append(verse)
                continue
            updated.append(BibleVerse(passage_id=verse.passage_id, verse=verse.verse, verse_end=fill.get("verse_end"), lines=fill["lines"]))
        self._chapter = BibleChapter(
            bible_version_id=self._chapter.bible_version_id,
            youversion_bible_id=self._chapter.youversion_bible_id,
            bible_title=self._chapter.bible_title,
            book_id=self._chapter.book_id,
            book_code=self._chapter.book_code,
            book_name=self._chapter.book_name,
            chapter=self._chapter.chapter,
            verses=updated,
        )


def unfilled_chapter(*, book_code: str, chapter: int, verses: list[int], youversion_bible_id: str = "1392") -> BibleChapter:
    book_id = uuid4()
    return BibleChapter(
        bible_version_id=uuid4(),
        youversion_bible_id=youversion_bible_id,
        bible_title="當代譯本修訂版",
        book_id=book_id,
        book_code=book_code,
        book_name=book_code,
        chapter=chapter,
        verses=[BibleVerse(passage_id=f"{book_code}.{chapter}.{verse}", verse=verse, lines=None) for verse in verses],
    )


def legacy_chapter(*, book_code: str, chapter: int, verses: list[int]) -> BibleChapter:
    """A chapter filled before paragraph boundaries were stored."""
    row = unfilled_chapter(book_code=book_code, chapter=chapter, verses=verses)
    for verse in row.verses:
        verse.lines = [{"type": "line", "style": "p", "fragments": [{"type": "text", "text": f"legacy {verse.verse}"}]}]
    return row
