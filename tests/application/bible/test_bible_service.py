"""
Tests for BibleService.
"""

from uuid import uuid4

import pytest

from portal.application.bible.bible_service import BibleService
from portal.application.bible.commands import ListVersionsQuery, SearchVersesCommand
from portal.domain.bible.entities import (
    BibleBook,
    BibleSearchHit,
    BibleSearchPage,
    BibleVersion,
)
from portal.exceptions.responses import NotFoundException


class StubBibleRepository:
    def __init__(
        self,
        versions=None,
        books=None,
        chapter=None,
        version_active=True,
        search_page=None,
    ):
        self._versions = versions or []
        self._books = books or []
        self._chapter = chapter
        self._version_active = version_active
        self._search_page = search_page or BibleSearchPage(results=[], total=0, limit=20, offset=0)

    async def fetch_active_versions(self, language=None):
        if language:
            return [v for v in self._versions if v.language_tag.startswith(language)]
        return self._versions

    async def version_is_active(self, bible_version_id):
        return self._version_active

    async def fetch_books(self, bible_version_id):
        return self._books

    async def fetch_chapter(self, book_id, chapter):
        return self._chapter

    async def search_verses(self, q, bible_version_id, book_id, limit, offset):
        return self._search_page


@pytest.mark.asyncio
async def test_list_versions_returns_repository_rows():
    version_id = uuid4()
    version = BibleVersion(
        id=version_id,
        youversion_bible_id="1392",
        abbreviation="CUV",
        title="Chinese Union Version",
        localized_title="和合本",
        language_tag="zh-Hant-TW",
        is_active=True,
    )
    service = BibleService(StubBibleRepository(versions=[version]))
    result = await service.list_versions(ListVersionsQuery())
    assert len(result.versions) == 1
    assert result.versions[0].id == version_id


@pytest.mark.asyncio
async def test_list_books_raises_when_version_inactive():
    service = BibleService(StubBibleRepository(version_active=False))
    with pytest.raises(NotFoundException):
        await service.list_books(bible_version_id=uuid4())


@pytest.mark.asyncio
async def test_list_books_splits_testaments():
    books = [
        BibleBook(
            id=uuid4(),
            book_code="GEN",
            title="Genesis",
            canon="old_testament",
            sequence=1,
            chapter_count=50,
        ),
        BibleBook(
            id=uuid4(),
            book_code="MAT",
            title="Matthew",
            canon="new_testament",
            sequence=40,
            chapter_count=28,
        ),
    ]
    service = BibleService(StubBibleRepository(books=books))
    result = await service.list_books(bible_version_id=uuid4())
    assert len(result.old_testament) == 1
    assert len(result.new_testament) == 1


@pytest.mark.asyncio
async def test_get_chapter_raises_when_missing():
    service = BibleService(StubBibleRepository(chapter=None))
    with pytest.raises(NotFoundException):
        await service.get_chapter(book_id=uuid4(), chapter=1)


@pytest.mark.asyncio
async def test_search_verses_delegates_to_repository():
    hit = BibleSearchHit(
        bible_version_id=uuid4(),
        youversion_bible_id="1392",
        bible_title="和合本",
        book_id=uuid4(),
        book_code="GEN",
        book_name="Genesis",
        chapter=1,
        verse=1,
        content="In the beginning",
    )
    page = BibleSearchPage(results=[hit], total=1, limit=10, offset=0)
    service = BibleService(StubBibleRepository(search_page=page))
    result = await service.search_verses(SearchVersesCommand(q="beginning", limit=10, offset=0))
    assert result.total == 1
    assert result.results[0].content == "In the beginning"
