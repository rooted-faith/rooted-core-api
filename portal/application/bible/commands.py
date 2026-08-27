"""
Bible application commands and queries.
"""

from uuid import UUID

from pydantic import BaseModel, Field


class ListVersionsQuery(BaseModel):
    """Filter for bible versions."""

    language: str | None = Field(default=None)


class SearchVersesCommand(BaseModel):
    """Verse full-text search."""

    q: str = Field(...)
    bible_version_id: UUID | None = Field(default=None)
    book_id: UUID | None = Field(default=None)
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
