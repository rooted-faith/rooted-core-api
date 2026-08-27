"""
Bible repository — SQLAlchemy-backed Scripture reads.
"""

from uuid import UUID

from portal.domain.bible.entities import (
    BibleBook,
    BibleChapter,
    BibleSearchHit,
    BibleSearchPage,
    BibleVerse,
    BibleVersion,
)
from portal.libs.database import Session
from portal.models import BibleBook as BibleBookModel
from portal.models import BibleVerse as BibleVerseModel
from portal.models import BibleVersion as BibleVersionModel


class BibleRepository:
    """Implements BibleRepositoryPort via structural typing."""

    def __init__(self, session: Session):
        self._session = session

    async def fetch_active_versions(self, language: str | None = None) -> list[BibleVersion]:
        query = self._session.select(
            BibleVersionModel.id,
            BibleVersionModel.youversion_bible_id,
            BibleVersionModel.abbreviation,
            BibleVersionModel.title,
            BibleVersionModel.localized_title,
            BibleVersionModel.localized_abbreviation,
            BibleVersionModel.language_tag,
            BibleVersionModel.is_active,
        ).where(BibleVersionModel.is_active.is_(True))

        if language:
            query = query.where(BibleVersionModel.language_tag.ilike(f"{language}%"))

        rows: list[BibleVersion] = await query.order_by(
            BibleVersionModel.language_tag,
            BibleVersionModel.youversion_bible_id,
        ).fetch(as_model=BibleVersion)
        return rows or []

    async def version_is_active(self, bible_version_id: UUID) -> bool:
        version_id = await (
            self._session.select(BibleVersionModel.id)
            .where(BibleVersionModel.id == bible_version_id)
            .where(BibleVersionModel.is_active == True)  # noqa: E712
            .fetchval()
        )
        return version_id is not None

    async def fetch_books(self, bible_version_id: UUID) -> list[BibleBook]:
        rows: list[BibleBook] = await (
            self._session.select(
                BibleBookModel.id,
                BibleBookModel.book_code,
                BibleBookModel.title,
                BibleBookModel.full_title,
                BibleBookModel.abbreviation,
                BibleBookModel.canon,
                BibleBookModel.sequence,
                BibleBookModel.chapter_count,
            )
            .where(BibleBookModel.bible_version_id == bible_version_id)
            .order_by(BibleBookModel.sequence)
            .fetch(as_model=BibleBook)
        )
        return rows or []

    async def fetch_chapter(self, book_id: UUID, chapter: int) -> BibleChapter | None:
        book_with_version = await (
            self._session.select(
                BibleBookModel.id,
                BibleBookModel.book_code,
                BibleBookModel.title,
                BibleVersionModel.id.label("bible_version_id"),
                BibleVersionModel.youversion_bible_id,
                BibleVersionModel.localized_title.label("bible_title"),
            )
            .join(BibleVersionModel, BibleBookModel.bible_version_id == BibleVersionModel.id)
            .where(BibleBookModel.id == book_id)
            .where(BibleVersionModel.is_active == True)  # noqa: E712
            .fetchrow()
        )
        if not book_with_version:
            return None

        verses: list[BibleVerse] = await (
            self._session.select(
                BibleVerseModel.verse,
                BibleVerseModel.content,
            )
            .where(BibleVerseModel.book_id == book_id)
            .where(BibleVerseModel.chapter == chapter)
            .order_by(BibleVerseModel.verse)
            .fetch(as_model=BibleVerse)
        )

        return BibleChapter(
            bible_version_id=book_with_version["bible_version_id"],
            youversion_bible_id=book_with_version["youversion_bible_id"],
            bible_title=book_with_version["bible_title"],
            book_id=book_with_version["id"],
            book_code=book_with_version["book_code"],
            book_name=book_with_version["title"],
            chapter=chapter,
            verses=verses or [],
        )

    async def search_verses(
        self,
        q: str,
        bible_version_id: UUID | None,
        book_id: UUID | None,
        limit: int,
        offset: int,
    ) -> BibleSearchPage:
        query = (
            self._session.select(
                BibleVersionModel.id.label("bible_version_id"),
                BibleVersionModel.youversion_bible_id,
                BibleVersionModel.localized_title.label("bible_title"),
                BibleVerseModel.book_id,
                BibleBookModel.book_code,
                BibleBookModel.title.label("book_name"),
                BibleVerseModel.chapter,
                BibleVerseModel.verse,
                BibleVerseModel.content,
            )
            .join(BibleBookModel, BibleVerseModel.book_id == BibleBookModel.id)
            .join(BibleVersionModel, BibleBookModel.bible_version_id == BibleVersionModel.id)
            .where(BibleVersionModel.is_active == True)  # noqa: E712
            .where(BibleVerseModel.content.ilike(f"%{q}%"))
        )

        if bible_version_id:
            query = query.where(BibleVersionModel.id == bible_version_id)
        if book_id:
            query = query.where(BibleVerseModel.book_id == book_id)

        total = await query.count()
        results: list[BibleSearchHit] = await (
            query.order_by(
                BibleVersionModel.youversion_bible_id,
                BibleBookModel.sequence,
                BibleVerseModel.chapter,
                BibleVerseModel.verse,
            )
            .limit(limit)
            .offset(offset)
            .fetch(as_model=BibleSearchHit)
        )

        return BibleSearchPage(results=results or [], total=total, limit=limit, offset=offset)
