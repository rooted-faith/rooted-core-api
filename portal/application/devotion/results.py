from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field

from portal.domain.devotion.constants import DevotionStatus


class EncounterResult(BaseModel):
    date: date
    current_streak: int
    longest_streak: int
    welcome_back: bool
    message: str = "今日已與主相遇"


class RhythmResult(BaseModel):
    current_streak: int
    longest_streak: int
    completed_dates: list[date] = Field(default_factory=list)


class DevotionTranslationResult(BaseModel):
    locale_id: UUID
    locale_code: str
    reflect: list[str] = Field(default_factory=list)
    apply: str
    pray: str


class DevotionListItemResult(BaseModel):
    id: UUID
    passage_start: str
    passage_end: str
    status: DevotionStatus


class DevotionDetailResult(DevotionListItemResult):
    translations: list[DevotionTranslationResult] = Field(default_factory=list)


class DevotionPageResult(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int
    items: list[DevotionListItemResult] = Field(default_factory=list)


class DailyLessonScheduleResult(BaseModel):
    date: date
    devotion_id: UUID | None = None


class DailyLessonScheduleRangeResult(BaseModel):
    items: list[DailyLessonScheduleResult] = Field(default_factory=list)
    scheduled_through: date | None = None
