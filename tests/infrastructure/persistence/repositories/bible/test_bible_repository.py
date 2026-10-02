"""Tests for BibleRepository."""

import json
from uuid import uuid4

import pytest

from portal.infrastructure.persistence.repositories.bible.bible_repository import BibleRepository, _to_verse


class FailingSession:
    def __getattr__(self, name: str):
        raise AssertionError(f"search must not access the database through {name}")


@pytest.mark.asyncio
async def test_search_verses_returns_an_empty_page_without_read_time_fill() -> None:
    repository = BibleRepository(session=FailingSession())

    page = await repository.search_verses(q="beginning", bible_version_id=None, book_id=None, limit=20, offset=0)

    assert page.results == []
    assert page.total == 0
    assert page.limit == 20
    assert page.offset == 0


class RecordingUpdate:
    def __init__(self, recorded: list[dict]) -> None:
        self._recorded = recorded

    def values(self, **values):
        self._recorded.append(values)
        return self

    def where(self, *_args):
        return self

    async def execute(self) -> None:
        return None


class RecordingSession:
    def __init__(self) -> None:
        self.recorded: list[dict] = []

    def update(self, _model):
        return RecordingUpdate(self.recorded)


@pytest.mark.asyncio
async def test_write_chapter_fill_encodes_lines_as_json_text_for_asyncpg() -> None:
    session = RecordingSession()
    repository = BibleRepository(session=session)
    lines = [{"type": "heading", "style": "s1", "fragments": [{"text": "The Beginning"}]}]

    await repository.write_chapter_fill(book_id=uuid4(), chapter=1, fills=[{"verse": 1, "verse_end": None, "lines": lines, "search_text": "In the beginning"}])

    assert json.loads(session.recorded[0]["lines"]) == lines


def test_to_verse_decodes_lines_returned_as_json_text_by_asyncpg() -> None:
    lines = [{"type": "heading", "style": "s1", "fragments": [{"text": "The Beginning"}]}]

    verse = _to_verse({"passage_id": "GEN.1.1", "verse": 1, "verse_end": None, "lines": json.dumps(lines)})

    assert verse.lines == lines
