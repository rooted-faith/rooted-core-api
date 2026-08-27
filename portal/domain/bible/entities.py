"""
Bible domain read models (snake_case).
"""

from uuid import UUID

from pydantic import BaseModel, Field

from portal.domain.common.mixins import UUIDBaseModel


class BibleVersion(UUIDBaseModel):
    """Bible translation metadata."""

    youversion_bible_id: str = Field(...)
    abbreviation: str = Field(...)
    title: str = Field(...)
    localized_title: str = Field(...)
    localized_abbreviation: str | None = Field(default=None)
    language_tag: str = Field(...)
    is_active: bool = Field(...)


class BibleBook(UUIDBaseModel):
    """Book metadata within a version."""

    book_code: str = Field(...)
    title: str = Field(...)
    full_title: str | None = Field(default=None)
    abbreviation: str | None = Field(default=None)
    canon: str = Field(...)
    sequence: float = Field(...)
    chapter_count: int = Field(...)


class BibleVerse(BaseModel):
    """Single verse line."""

    verse: int = Field(...)
    content: str = Field(...)


class BibleChapter(BaseModel):
    """Chapter with verses."""

    bible_version_id: UUID = Field(...)
    youversion_bible_id: str = Field(...)
    bible_title: str = Field(...)
    book_id: UUID = Field(...)
    book_code: str = Field(...)
    book_name: str = Field(...)
    chapter: int = Field(...)
    verses: list[BibleVerse] = Field(default_factory=list)


class BibleSearchHit(BaseModel):
    """Single search hit."""

    bible_version_id: UUID = Field(...)
    youversion_bible_id: str = Field(...)
    bible_title: str = Field(...)
    book_id: UUID = Field(...)
    book_code: str = Field(...)
    book_name: str = Field(...)
    chapter: int = Field(...)
    verse: int = Field(...)
    content: str = Field(...)
    highlight: str | None = Field(default=None)


class BibleSearchPage(BaseModel):
    """Paginated search results."""

    results: list[BibleSearchHit] = Field(default_factory=list)
    total: int = Field(default=0)
    limit: int = Field(...)
    offset: int = Field(...)
