from uuid import UUID, uuid4

import pytest

from portal.application.bible.commands import ListVersionsQuery, SearchVersesCommand
from portal.application.bible.results import BibleBookListResult, BibleSearchPageResult, BibleVersionListResult
from portal.domain.bible.entities import BibleBook, BibleSearchHit, BibleVersion
from portal.routers.apis.v1.bible import get_bible_books, get_bible_versions, search_bible_verses

VERSION = BibleVersion(
    id=uuid4(),
    youversion_bible_id="1392",
    abbreviation="CCBT",
    title="Chinese Contemporary Bible Traditional",
    localized_title="當代譯本",
    language_tag="zh-Hant-TW",
    is_active=True,
)
GENESIS = BibleBook(id=uuid4(), book_code="GEN", title="Genesis", canon="old_testament", sequence=1, chapter_count=50)
MATTHEW = BibleBook(id=uuid4(), book_code="MAT", title="Matthew", canon="new_testament", sequence=40, chapter_count=28)
HIT = BibleSearchHit(
    bible_version_id=VERSION.id,
    youversion_bible_id="1392",
    bible_title="當代譯本",
    book_id=uuid4(),
    book_code="JHN",
    book_name="John",
    chapter=3,
    verse=16,
    content="For God so loved the world",
)


class StubBibleService:
    def __init__(self) -> None:
        self.captured_versions_query: ListVersionsQuery | None = None
        self.captured_books_version_id: UUID | None = None
        self.captured_search: SearchVersesCommand | None = None

    async def list_versions(self, query: ListVersionsQuery) -> BibleVersionListResult:
        self.captured_versions_query = query
        return BibleVersionListResult(versions=[VERSION])

    async def list_books(self, bible_version_id: UUID) -> BibleBookListResult:
        self.captured_books_version_id = bible_version_id
        return BibleBookListResult(old_testament=[GENESIS], new_testament=[MATTHEW])

    async def search_verses(self, command: SearchVersesCommand) -> BibleSearchPageResult:
        self.captured_search = command
        return BibleSearchPageResult(results=[HIT], total=1, limit=command.limit, offset=command.offset)


@pytest.mark.asyncio
async def test_get_bible_versions_passes_language_filter_and_returns_versions() -> None:
    service = StubBibleService()

    response = await get_bible_versions(language="zh-TW", bible_service=service)
    payload = response.model_dump(mode="json", by_alias=True)

    assert service.captured_versions_query == ListVersionsQuery(language="zh-TW")
    assert [version["id"] for version in payload["versions"]] == [str(VERSION.id)]
    assert payload["versions"][0]["localizedTitle"] == "當代譯本"


@pytest.mark.asyncio
async def test_get_bible_books_returns_both_testaments() -> None:
    service = StubBibleService()

    response = await get_bible_books(bible_version_id=VERSION.id, bible_service=service)
    payload = response.model_dump(mode="json", by_alias=True)

    assert service.captured_books_version_id == VERSION.id
    assert [book["bookCode"] for book in payload["oldTestament"]] == ["GEN"]
    assert [book["bookCode"] for book in payload["newTestament"]] == ["MAT"]
    assert payload["oldTestament"][0]["id"] == str(GENESIS.id)


@pytest.mark.asyncio
async def test_search_bible_verses_returns_results() -> None:
    service = StubBibleService()

    response = await search_bible_verses(q="loved", bible_version_id=None, book_id=None, limit=20, offset=0, bible_service=service)
    payload = response.model_dump(mode="json", by_alias=True)

    assert service.captured_search == SearchVersesCommand(q="loved", bible_version_id=None, book_id=None, limit=20, offset=0)
    assert payload["total"] == 1
    assert payload["results"][0]["bookCode"] == "JHN"
    assert payload["results"][0]["bibleVersionId"] == str(VERSION.id)
