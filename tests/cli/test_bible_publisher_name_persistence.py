"""PostgreSQL persistence checks for publisher_name import and metadata-only backfill."""

import json
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio

from portal.cli import backfill_bible_publisher_names as backfill_module
from portal.cli import import_bible
from portal.models import BibleBook, BibleVerse, BibleVersion
from tests.infrastructure.persistence.db import open_session_or_skip

LINES = [{"type": "line", "style": "p", "continues": False, "fragments": [{"text": "In the beginning"}]}]
SEARCH_TEXT = "In the beginning"


@pytest_asyncio.fixture
async def db_session():
    session = await open_session_or_skip()
    await session.execute("SELECT 1")
    try:
        yield session
    finally:
        await session.rollback()
        await session.close()


def _write_source(tmp_path: Path, bible_id: str, *, publisher_name: str | None, omit_key: bool = False) -> None:
    meta_dir = tmp_path / bible_id / "meta"
    meta_dir.mkdir(parents=True)
    payload = {
        "id": bible_id,
        "abbreviation": "TST",
        "title": "Test Bible",
        "localized_title": "Test Bible",
        "language_tag": "en",
        "copyright": "Test Copyright",
        "publisher_url": "https://example.test/publisher",
    }
    if not omit_key:
        payload["publisher_name"] = publisher_name
    (meta_dir / "bible.json").write_text(json.dumps(payload), encoding="utf-8")
    (meta_dir / "index.json").write_text(
        json.dumps({"books": [{"id": "GEN", "title": "Genesis", "chapters": [{"id": "1", "verses": [{"id": "1", "passage_id": "GEN.1.1"}]}]}]}),
        encoding="utf-8",
    )


def _bind_session(monkeypatch, module, session) -> None:
    session.commit = AsyncMock()
    session.close = AsyncMock()

    class BoundContainer:
        def db_session(self):
            return session

    monkeypatch.setattr(module, "Container", BoundContainer)


async def _seed_version_with_scripture(session, *, youversion_bible_id: str, publisher_name: str | None = None) -> tuple:
    version_id = uuid4()
    book_id = uuid4()
    await (
        session.insert(BibleVersion)
        .values(
            id=version_id,
            youversion_bible_id=youversion_bible_id,
            abbreviation="TST",
            title="Test Bible",
            localized_title="Test Bible",
            language_tag="en",
            copyright="Test Copyright",
            publisher_url="https://example.test/publisher",
            publisher_name=publisher_name,
            is_active=True,
        )
        .execute()
    )
    await (
        session.insert(BibleBook)
        .values(id=book_id, bible_version_id=version_id, book_code="GEN", title="Genesis", canon="old_testament", sequence=1.0, chapter_count=1)
        .execute()
    )
    await (
        session.insert(BibleVerse)
        .values(book_id=book_id, chapter=1, verse=1, verse_end=None, passage_id="GEN.1.1", lines=LINES, search_text=SEARCH_TEXT)
        .execute()
    )
    return version_id, book_id


async def _read_version_snapshot(session, version_id):
    return await session.fetchrow(
        """
        SELECT id, youversion_bible_id, abbreviation, title, copyright, publisher_url, publisher_name, is_active
        FROM bible.versions
        WHERE id = $1
        """,
        version_id,
    )


async def _read_verse_snapshot(session, book_id):
    return await session.fetchrow(
        """
        SELECT book_id, chapter, verse, verse_end, passage_id, lines, search_text
        FROM bible.verses
        WHERE book_id = $1 AND passage_id = 'GEN.1.1'
        """,
        book_id,
    )


@pytest.mark.asyncio
async def test_import_persists_publisher_name_and_leaves_empty_as_null(db_session, tmp_path, monkeypatch) -> None:
    present_id = f"pub-present-{uuid4().hex[:8]}"
    empty_id = f"pub-empty-{uuid4().hex[:8]}"
    _write_source(tmp_path, present_id, publisher_name="Biblica, Inc.")
    _write_source(tmp_path, empty_id, publisher_name="  ")
    _bind_session(monkeypatch, import_bible, db_session)

    await import_bible.import_bible_data(bible_id=present_id, data_dir=str(tmp_path))
    await import_bible.import_bible_data(bible_id=empty_id, data_dir=str(tmp_path))

    present = await db_session.fetchrow("SELECT publisher_name, copyright, publisher_url FROM bible.versions WHERE youversion_bible_id = $1", present_id)
    empty = await db_session.fetchrow("SELECT publisher_name FROM bible.versions WHERE youversion_bible_id = $1", empty_id)
    assert present["publisher_name"] == "Biblica, Inc."
    assert present["copyright"] == "Test Copyright"
    assert present["publisher_url"] == "https://example.test/publisher"
    assert empty["publisher_name"] is None


@pytest.mark.asyncio
async def test_backfill_persists_names_without_changing_scripture_or_other_metadata(db_session, tmp_path, monkeypatch) -> None:
    named_id = f"pub-named-{uuid4().hex[:8]}"
    blank_id = f"pub-blank-{uuid4().hex[:8]}"
    kept_id = f"pub-kept-{uuid4().hex[:8]}"

    named_version_id, named_book_id = await _seed_version_with_scripture(db_session, youversion_bible_id=named_id)
    blank_version_id, blank_book_id = await _seed_version_with_scripture(db_session, youversion_bible_id=blank_id)
    kept_version_id, kept_book_id = await _seed_version_with_scripture(db_session, youversion_bible_id=kept_id, publisher_name="Already Kept")

    before_named = await _read_version_snapshot(db_session, named_version_id)
    before_blank = await _read_version_snapshot(db_session, blank_version_id)
    before_kept = await _read_version_snapshot(db_session, kept_version_id)
    before_named_verse = await _read_verse_snapshot(db_session, named_book_id)
    before_blank_verse = await _read_verse_snapshot(db_session, blank_book_id)
    before_kept_verse = await _read_verse_snapshot(db_session, kept_book_id)

    _write_source(tmp_path, named_id, publisher_name="Biblica, Inc.")
    _write_source(tmp_path, blank_id, publisher_name=None, omit_key=True)
    _write_source(tmp_path, kept_id, publisher_name="   ")
    _bind_session(monkeypatch, backfill_module, db_session)

    await backfill_module.backfill_bible_publisher_names(data_dir=str(tmp_path))
    await backfill_module.backfill_bible_publisher_names(data_dir=str(tmp_path))

    after_named = await _read_version_snapshot(db_session, named_version_id)
    after_blank = await _read_version_snapshot(db_session, blank_version_id)
    after_kept = await _read_version_snapshot(db_session, kept_version_id)

    assert after_named["publisher_name"] == "Biblica, Inc."
    assert after_blank["publisher_name"] is None
    assert after_kept["publisher_name"] == "Already Kept"

    for before, after in ((before_named, after_named), (before_blank, after_blank), (before_kept, after_kept)):
        assert after["id"] == before["id"]
        assert after["youversion_bible_id"] == before["youversion_bible_id"]
        assert after["abbreviation"] == before["abbreviation"]
        assert after["title"] == before["title"]
        assert after["copyright"] == before["copyright"]
        assert after["publisher_url"] == before["publisher_url"]
        assert after["is_active"] == before["is_active"]

    assert await _read_verse_snapshot(db_session, named_book_id) == before_named_verse
    assert await _read_verse_snapshot(db_session, blank_book_id) == before_blank_verse
    assert await _read_verse_snapshot(db_session, kept_book_id) == before_kept_verse
    assert before_named_verse["lines"] == LINES
    assert before_named_verse["search_text"] == SEARCH_TEXT
