"""
Bible application service.
"""

from typing import Any
from uuid import UUID

from portal.application.bible.chapter_fill_gate import ChapterFillGate
from portal.application.bible.commands import ListVersionsQuery, SearchVersesCommand
from portal.application.bible.parse_chapter_html import ChapterHtmlParseError, parse_chapter_html
from portal.application.bible.results import BibleBookListResult, BibleBookResult, BibleChapterResult, BibleSearchPageResult, BibleVersionListResult
from portal.domain.bible.entities import BibleChapter
from portal.domain.bible.ports import BibleRepositoryPort, YouVersionPort
from portal.exceptions.responses import ApiBaseException, NotFoundException
from portal.libs.tracing.distributed_trace import distributed_trace

_DEFAULT_CHAPTER_FILL_GATE = ChapterFillGate()


class BibleService:
    """Scripture reader use cases."""

    def __init__(self, bible_repository: BibleRepositoryPort, youversion: YouVersionPort, chapter_fill_gate: ChapterFillGate | None = None):
        self._repository = bible_repository
        self._youversion = youversion
        self._chapter_fill_gate = chapter_fill_gate or _DEFAULT_CHAPTER_FILL_GATE

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
        if _chapter_needs_fill(row):
            fills = await self._fetch_chapter_fills(row)
            await self._repository.write_chapter_fill(book_id=row.book_id, chapter=row.chapter, fills=fills)
            row = await self._repository.fetch_chapter(book_id=book_id, chapter=chapter)
            if row is None or _chapter_needs_fill(row):
                raise ApiBaseException(status_code=502, detail="Failed to fill Scripture chapter")
        return row

    @distributed_trace()
    async def search_verses(self, command: SearchVersesCommand) -> BibleSearchPageResult:
        return await self._repository.search_verses(
            q=command.q, bible_version_id=command.bible_version_id, book_id=command.book_id, limit=command.limit, offset=command.offset
        )

    async def _fetch_chapter_fills(self, chapter: BibleChapter) -> list[dict[str, Any]]:
        key = (chapter.youversion_bible_id, chapter.book_code, chapter.chapter)
        shell_verses = {verse.verse for verse in chapter.verses}

        async def _run() -> list[dict[str, Any]]:
            chapter_usfm = f"{chapter.book_code}.{chapter.chapter}"
            try:
                passage = await self._youversion.get_chapter_passage(chapter.youversion_bible_id, chapter_usfm)
            except Exception as exc:
                raise ApiBaseException(status_code=502, detail="YouVersion chapter fetch failed", debug_detail=str(exc)) from exc

            content = passage.get("content") if isinstance(passage, dict) else None
            if not isinstance(content, str) or not content.strip():
                raise ApiBaseException(status_code=502, detail="YouVersion chapter content missing")

            try:
                fills = parse_chapter_html(content)
            except ChapterHtmlParseError as exc:
                raise ApiBaseException(status_code=502, detail="YouVersion chapter HTML unmappable", debug_detail=str(exc)) from exc

            fill_verses = {item["verse"] for item in fills}
            if fill_verses != shell_verses:
                raise ApiBaseException(
                    status_code=502,
                    detail="YouVersion chapter HTML unmappable",
                    debug_detail=f"verse set mismatch shells={sorted(shell_verses)} fills={sorted(fill_verses)}",
                )
            return fills

        return await self._chapter_fill_gate.run(key, _run)


def _chapter_needs_fill(chapter: BibleChapter) -> bool:
    return any(verse.lines is None for verse in chapter.verses)
