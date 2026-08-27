"""
Bible repository port.
"""

from typing import Protocol
from uuid import UUID

from portal.domain.bible.entities import BibleBook, BibleChapter, BibleSearchPage, BibleVersion


class BibleRepositoryPort(Protocol):
    """Persistence port for Scripture reader reads."""

    async def fetch_active_versions(self, language: str | None = None) -> list[BibleVersion]:
        """List active bible versions, optionally filtered by language tag prefix."""

    async def version_is_active(self, bible_version_id: UUID) -> bool:
        """Return True when the version exists and is active."""

    async def fetch_books(self, bible_version_id: UUID) -> list[BibleBook]:
        """List books for a version ordered by sequence."""

    async def fetch_chapter(self, book_id: UUID, chapter: int) -> BibleChapter | None:
        """Load chapter metadata and verses; None when book or version missing."""

    async def search_verses(
        self,
        q: str,
        bible_version_id: UUID | None,
        book_id: UUID | None,
        limit: int,
        offset: int,
    ) -> BibleSearchPage:
        """Search verse content with optional filters."""
