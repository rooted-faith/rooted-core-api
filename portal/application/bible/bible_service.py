"""
Bible application service.
"""

from typing import Any, NamedTuple
from uuid import UUID

from portal.application.bible.chapter_fill_gate import ChapterFillGate
from portal.application.bible.commands import ListVersionsQuery, ReadPassageQuery, SearchVersesCommand
from portal.application.bible.parse_chapter_html import ChapterHtmlParseError, parse_chapter_html
from portal.application.bible.results import (
    BibleBookListResult,
    BibleBookResult,
    BibleChapterResult,
    BiblePassageResult,
    BibleSearchPageResult,
    BibleVersionListResult,
)
from portal.domain.bible.constants import BibleErrorCode
from portal.domain.bible.entities import BibleChapter, BibleVerse
from portal.domain.bible.ports import BibleRepositoryPort, YouVersionPort
from portal.exceptions.responses import ApiBaseException, NotFoundException
from portal.libs.tracing.distributed_trace import distributed_trace

_DEFAULT_CHAPTER_FILL_GATE = ChapterFillGate()
_MAX_PASSAGE_CHAPTER_SPAN = 150  # Psalms, the longest book, has 150 chapters


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
    async def read_passage(self, query: ReadPassageQuery) -> BiblePassageResult:
        if not await self._repository.version_is_active(query.bible_version_id):
            raise NotFoundException(detail=f"Bible version {query.bible_version_id} not found or inactive", error_code=BibleErrorCode.VERSION_NOT_FOUND)

        start_ref = _parse_passage_ref(query.passage_start)
        end_ref = _parse_passage_ref(query.passage_end)
        if start_ref is None or end_ref is None or start_ref.book_code != end_ref.book_code:
            raise NotFoundException(detail="Passage reference could not be resolved", error_code=BibleErrorCode.PASSAGE_NOT_FOUND)
        if end_ref.chapter - start_ref.chapter > _MAX_PASSAGE_CHAPTER_SPAN:
            raise NotFoundException(detail="Passage reference could not be resolved", error_code=BibleErrorCode.PASSAGE_NOT_FOUND)

        book_id = await self._repository.find_book_id(query.bible_version_id, start_ref.book_code)
        if book_id is None:
            raise NotFoundException(detail="Passage reference could not be resolved", error_code=BibleErrorCode.PASSAGE_NOT_FOUND)

        chosen: list[tuple[int, BibleVerse]] = []
        book_name: str | None = None
        for chapter in range(start_ref.chapter, end_ref.chapter + 1):
            filled = await self.get_chapter(book_id, chapter)
            book_name = filled.book_name
            chosen.extend(
                (chapter, verse)
                for verse in filled.verses
                if _verse_is_cited(verse, chapter, start_ref.chapter, start_ref.verse, end_ref.chapter, end_ref.verse)
            )

        if not chosen or book_name is None:
            raise NotFoundException(detail="Passage reference could not be resolved", error_code=BibleErrorCode.PASSAGE_NOT_FOUND)

        first_chapter, first_verse = chosen[0]
        last_chapter, last_verse = chosen[-1]
        ref = f"{book_name} {first_chapter}:{first_verse.verse}"
        if (last_chapter, last_verse.verse) != (first_chapter, first_verse.verse):
            ref += f"–{last_chapter}:{last_verse.verse}"

        return BiblePassageResult(start=query.passage_start, end=query.passage_end, ref=ref, verses=[verse for _, verse in chosen])

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


class _PassageRef(NamedTuple):
    book_code: str
    chapter: int
    verse: int


def _parse_passage_ref(passage_ref: str) -> _PassageRef | None:
    parts = passage_ref.split(".")
    if len(parts) != 3:
        return None
    book_code, chapter_str, verse_str = parts
    if not book_code or not chapter_str.isdigit() or not verse_str.isdigit():
        return None
    return _PassageRef(book_code=book_code, chapter=int(chapter_str), verse=int(verse_str))


def _verse_is_cited(verse: BibleVerse, chapter: int, start_chapter: int, start_verse: int, end_chapter: int, end_verse: int) -> bool:
    cited_start = start_verse if chapter == start_chapter else 1
    cited_end = end_verse if chapter == end_chapter else None
    verse_finish = verse.verse_end if verse.verse_end is not None else verse.verse
    if verse_finish < cited_start:
        return False
    return cited_end is None or verse.verse <= cited_end
