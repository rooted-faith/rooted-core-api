"""
Bible application service.
"""

from uuid import UUID

from portal.application.bible.commands import ListVersionsQuery, SearchVersesCommand
from portal.application.bible.results import (
    BibleBookListResult,
    BibleBookResult,
    BibleChapterResult,
    BibleSearchPageResult,
    BibleVersionListResult,
)
from portal.domain.bible.ports import BibleRepositoryPort
from portal.exceptions.responses import NotFoundException
from portal.libs.tracing.distributed_trace import distributed_trace


class BibleService:
    """Scripture reader use cases."""

    def __init__(self, bible_repository: BibleRepositoryPort):
        self._repository = bible_repository

    @distributed_trace()
    async def list_versions(self, query: ListVersionsQuery) -> BibleVersionListResult:
        versions = await self._repository.fetch_active_versions(language=query.language)
        return BibleVersionListResult(versions=versions)

    @distributed_trace()
    async def list_books(self, bible_version_id: UUID) -> BibleBookListResult:
        if not await self._repository.version_is_active(bible_version_id):
            raise NotFoundException(detail=f"Bible version {bible_version_id} not found or inactive")
        books: list[BibleBookResult] = await self._repository.fetch_books(bible_version_id)
        old_testament = [book for book in books if book.canon == "old_testament"]
        new_testament = [book for book in books if book.canon == "new_testament"]
        return BibleBookListResult(old_testament=old_testament, new_testament=new_testament)

    @distributed_trace()
    async def get_chapter(self, book_id: UUID, chapter: int) -> BibleChapterResult:
        row = await self._repository.fetch_chapter(book_id=book_id, chapter=chapter)
        if row is None:
            raise NotFoundException(detail=f"Book {book_id} not found or version is inactive")
        return row

    @distributed_trace()
    async def search_verses(self, command: SearchVersesCommand) -> BibleSearchPageResult:
        return await self._repository.search_verses(
            q=command.q,
            bible_version_id=command.bible_version_id,
            book_id=command.book_id,
            limit=command.limit,
            offset=command.offset,
        )
