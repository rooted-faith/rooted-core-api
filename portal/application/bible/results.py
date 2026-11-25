"""
Bible application results — aliases of domain read models.
"""

from enum import StrEnum

from pydantic import BaseModel, Field

from portal.domain.bible.entities import BibleBook, BibleChapter, BiblePassage, BibleSearchHit, BibleSearchPage, BibleVerse, BibleVersion

BibleVersionResult = BibleVersion
BibleBookResult = BibleBook
BibleVerseResult = BibleVerse
BibleChapterResult = BibleChapter
BibleSearchHitResult = BibleSearchHit
BibleSearchPageResult = BibleSearchPage
BiblePassageResult = BiblePassage


class BibleVersionListResult(BaseModel):
    versions: list[BibleVersionResult] = Field(default_factory=list)


class BibleBookListResult(BaseModel):
    old_testament: list[BibleBookResult] = Field(default_factory=list)
    new_testament: list[BibleBookResult] = Field(default_factory=list)


class ChapterRefillOutcome(StrEnum):
    UPGRADED = "upgraded"
    ALREADY_UPGRADED = "already_upgraded"
    UNFILLED = "unfilled"


__all__ = [
    "ChapterRefillOutcome",
    "BibleVersionResult",
    "BibleVersionListResult",
    "BibleBookResult",
    "BibleBookListResult",
    "BibleVerseResult",
    "BibleChapterResult",
    "BibleSearchHitResult",
    "BibleSearchPageResult",
    "BiblePassageResult",
]
