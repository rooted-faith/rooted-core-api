from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field

from portal.domain.bible.entities import BibleVerse
from portal.domain.common.mixins import UUIDModel
from portal.domain.devotion.constants import DevotionStatus


class Passage(BaseModel):
    start: str
    end: str
    ref: str
    verses: list[BibleVerse] = Field(default_factory=list)


class ScheduledDailyLesson(BaseModel):
    """Daily lesson address and authored text, without Scripture bodies."""

    date: date
    passage_start: str
    passage_end: str
    book_id: UUID | None
    reflect: list[str] | None = None
    apply: str | None = None
    pray: str | None = None


class AnonymousDailyLesson(BaseModel):
    date: date
    passage: Passage
    locked: list[str] = Field(default_factory=lambda: ["reflect", "apply", "pray", "note"])


class LessonNote(BaseModel):
    date: date
    body: str | None = None
    reflects: list[str | None] = Field(default_factory=list)


class DailyLesson(BaseModel):
    date: date
    passage: Passage
    reflect: list[str] = Field(default_factory=list)
    apply: str
    pray: str
    note: LessonNote | None = None
    locked: list[str] = Field(default_factory=list)


class EncounterStreak(BaseModel):
    user_id: UUID
    longest_streak: int
    current_streak_length: int
    last_encounter_date: date | None


class DevotionTranslation(BaseModel):
    locale_id: UUID
    locale_code: str
    reflect: list[str] = Field(default_factory=list)
    apply: str
    pray: str


class Devotion(UUIDModel):
    passage_start: str
    passage_end: str
    status: DevotionStatus
    translations: list[DevotionTranslation] = Field(default_factory=list)


class DailyLessonSchedule(BaseModel):
    date: date
    devotion_id: UUID
