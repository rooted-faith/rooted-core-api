"""
Tests for BibleService.
"""

from uuid import uuid4

import pytest

from portal.application.bible.bible_service import BibleService
from portal.application.bible.commands import ListVersionsQuery, ReadPassageQuery, SearchVersesCommand
from portal.domain.bible.constants import BibleErrorCode
from portal.domain.bible.entities import BibleBook, BibleChapter, BibleSearchHit, BibleSearchPage, BibleVerse, BibleVersion
from portal.exceptions.responses import NotFoundException


class StubYouVersion:
    async def get_bible_metadata(self, bible_id: str):
        raise NotImplementedError

    async def get_bible_index(self, bible_id: str):
        raise NotImplementedError

    async def get_chapter_passage(self, bible_id: str, chapter_usfm: str):
        raise NotImplementedError


class StubBibleRepository:
    def __init__(self, versions=None, books=None, chapter=None, chapters=None, version_active=True, search_page=None, book_ids_by_code=None):
        self._versions = versions or []
        self._books = books or []
        self._chapter = chapter
        self._chapters = chapters or {}
        self._version_active = version_active
        self._search_page = search_page or BibleSearchPage(results=[], total=0, limit=20, offset=0)
        self._book_ids_by_code = book_ids_by_code or {}

    async def fetch_active_versions(self, language=None):
        if language:
            return [v for v in self._versions if v.language_tag.startswith(language)]
        return self._versions

    async def version_is_active(self, bible_version_id):
        return self._version_active

    async def fetch_books(self, bible_version_id):
        return self._books

    async def fetch_chapter(self, book_id, chapter):
        if chapter in self._chapters:
            return self._chapters[chapter]
        return self._chapter

    async def find_book_id(self, bible_version_id, book_code):
        return self._book_ids_by_code.get(book_code)

    async def write_chapter_fill(self, book_id, chapter, fills):
        raise NotImplementedError

    async def search_verses(self, q, bible_version_id, book_id, limit, offset):
        return self._search_page


def _service(repository: StubBibleRepository) -> BibleService:
    return BibleService(repository, StubYouVersion())


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
    service = _service(StubBibleRepository(versions=[version]))
    result = await service.list_versions(ListVersionsQuery())
    assert len(result.versions) == 1
    assert result.versions[0].id == version_id


@pytest.mark.asyncio
async def test_list_books_raises_when_version_inactive():
    service = _service(StubBibleRepository(version_active=False))
    with pytest.raises(NotFoundException):
        await service.list_books(bible_version_id=uuid4())


@pytest.mark.asyncio
async def test_list_books_splits_testaments():
    books = [
        BibleBook(id=uuid4(), book_code="GEN", title="Genesis", canon="old_testament", sequence=1, chapter_count=50),
        BibleBook(id=uuid4(), book_code="MAT", title="Matthew", canon="new_testament", sequence=40, chapter_count=28),
    ]
    service = _service(StubBibleRepository(books=books))
    result = await service.list_books(bible_version_id=uuid4())
    assert len(result.old_testament) == 1
    assert len(result.new_testament) == 1


@pytest.mark.asyncio
async def test_get_chapter_raises_when_missing():
    service = _service(StubBibleRepository(chapter=None))
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
    service = _service(StubBibleRepository(search_page=page))
    result = await service.search_verses(SearchVersesCommand(q="beginning", limit=10, offset=0))
    assert result.total == 1
    assert result.results[0].content == "In the beginning"


def _chapter(book_id, chapter: int, verses: list[BibleVerse]) -> BibleChapter:
    return BibleChapter(
        bible_version_id=uuid4(),
        youversion_bible_id="1392",
        bible_title="和合本",
        book_id=book_id,
        book_code="GEN",
        book_name="Genesis",
        chapter=chapter,
        verses=verses,
    )


@pytest.mark.asyncio
async def test_read_passage_raises_when_version_inactive():
    service = _service(StubBibleRepository(version_active=False))
    with pytest.raises(NotFoundException) as exc_info:
        await service.read_passage(ReadPassageQuery(bible_version_id=uuid4(), passage_start="GEN.1.1", passage_end="GEN.1.1"))
    assert exc_info.value.error_code == BibleErrorCode.VERSION_NOT_FOUND


@pytest.mark.asyncio
async def test_read_passage_raises_when_reference_malformed():
    service = _service(StubBibleRepository())
    with pytest.raises(NotFoundException) as exc_info:
        await service.read_passage(ReadPassageQuery(bible_version_id=uuid4(), passage_start="not-a-ref", passage_end="GEN.1.1"))
    assert exc_info.value.error_code == BibleErrorCode.PASSAGE_NOT_FOUND


@pytest.mark.asyncio
async def test_read_passage_raises_when_range_crosses_books():
    service = _service(StubBibleRepository())
    with pytest.raises(NotFoundException) as exc_info:
        await service.read_passage(ReadPassageQuery(bible_version_id=uuid4(), passage_start="GEN.50.26", passage_end="EXO.1.1"))
    assert exc_info.value.error_code == BibleErrorCode.PASSAGE_NOT_FOUND


@pytest.mark.asyncio
async def test_read_passage_raises_when_book_missing_in_version():
    service = _service(StubBibleRepository(book_ids_by_code={}))
    with pytest.raises(NotFoundException) as exc_info:
        await service.read_passage(ReadPassageQuery(bible_version_id=uuid4(), passage_start="GEN.1.1", passage_end="GEN.1.1"))
    assert exc_info.value.error_code == BibleErrorCode.PASSAGE_NOT_FOUND


@pytest.mark.asyncio
async def test_read_passage_returns_cited_verses_across_chapters():
    book_id = uuid4()
    chapter_1 = _chapter(
        book_id, 1, [BibleVerse(passage_id="GEN.1.31", verse=31, lines=[{"type": "line", "fragments": [{"type": "text", "text": "It was very good"}]}])]
    )
    chapter_2 = _chapter(
        book_id, 2, [BibleVerse(passage_id="GEN.2.1", verse=1, lines=[{"type": "line", "fragments": [{"type": "text", "text": "The heavens were finished"}]}])]
    )
    repository = StubBibleRepository(chapters={1: chapter_1, 2: chapter_2}, book_ids_by_code={"GEN": book_id})
    service = _service(repository)

    result = await service.read_passage(ReadPassageQuery(bible_version_id=uuid4(), passage_start="GEN.1.31", passage_end="GEN.2.1"))

    assert result.start == "GEN.1.31"
    assert result.end == "GEN.2.1"
    assert result.ref == "Genesis 1:31–2:1"
    assert [verse.passage_id for verse in result.verses] == ["GEN.1.31", "GEN.2.1"]


@pytest.mark.asyncio
async def test_read_passage_raises_without_fetching_chapters_when_span_is_absurd():
    repository = StubBibleRepository(book_ids_by_code={"GEN": uuid4()})
    service = _service(repository)

    with pytest.raises(NotFoundException) as exc_info:
        await service.read_passage(ReadPassageQuery(bible_version_id=uuid4(), passage_start="GEN.1.1", passage_end="GEN.999999999.1"))
    assert exc_info.value.error_code == BibleErrorCode.PASSAGE_NOT_FOUND


@pytest.mark.asyncio
async def test_read_passage_raises_when_verse_range_unresolved():
    book_id = uuid4()
    chapter_1 = _chapter(book_id, 1, [BibleVerse(passage_id="GEN.1.1", verse=1, lines=[{"type": "line", "fragments": []}])])
    repository = StubBibleRepository(chapters={1: chapter_1}, book_ids_by_code={"GEN": book_id})
    service = _service(repository)

    with pytest.raises(NotFoundException) as exc_info:
        await service.read_passage(ReadPassageQuery(bible_version_id=uuid4(), passage_start="GEN.1.99", passage_end="GEN.1.99"))
    assert exc_info.value.error_code == BibleErrorCode.PASSAGE_NOT_FOUND
