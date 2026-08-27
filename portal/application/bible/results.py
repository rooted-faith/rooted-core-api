"""
Bible application results — aliases of domain read models.
"""

from pydantic import BaseModel, Field

from portal.domain.bible.entities import (
    BibleBook,
    BibleChapter,
    BibleSearchHit,
    BibleSearchPage,
    BibleVerse,
    BibleVersion,
)

BibleVersionResult = BibleVersion
BibleBookResult = BibleBook
BibleVerseResult = BibleVerse
BibleChapterResult = BibleChapter
BibleSearchHitResult = BibleSearchHit
BibleSearchPageResult = BibleSearchPage


class BibleVersionListResult(BaseModel):
    versions: list[BibleVersionResult] = Field(default_factory=list)


class BibleBookListResult(BaseModel):
    old_testament: list[BibleBookResult] = Field(default_factory=list)
    new_testament: list[BibleBookResult] = Field(default_factory=list)


__all__ = [
    "BibleVersionResult",
    "BibleVersionListResult",
    "BibleBookResult",
    "BibleBookListResult",
    "BibleVerseResult",
    "BibleChapterResult",
    "BibleSearchHitResult",
    "BibleSearchPageResult",
]
